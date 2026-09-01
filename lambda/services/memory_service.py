"""
services/memory_service.py
============================

Persistance de la mémoire conversationnelle dans DynamoDB.

Deux couches :

  1. `MemoryService` : accès bas niveau à la table DynamoDB. Chaque tour
     (user / assistant / tool) est stocké comme un item
     (session_id, timestamp, role, content, ttl).

  2. `DynamoDBChatMessageHistory` : mémoire "court terme" (fenêtre
     glissante des N derniers échanges), qui implémente l'interface
     standard `BaseChatMessageHistory` de LangChain.

     >>> C'est le remplaçant moderne de `ConversationBufferWindowMemory`
     >>> (dépréciée dans les versions récentes de LangChain). On obtient
     >>> le même comportement de fenêtre glissante, mais avec une classe
     >>> non dépréciée, et surtout compatible nativement avec
     >>> `RunnableWithMessageHistory` si vous souhaitez, ailleurs dans le
     >>> projet, brancher une simple chaîne (Runnable) sans passer par
     >>> LangGraph (voir `create_runnable_with_history` tout en bas).

     Dans CE projet, le graphe LangGraph n'utilise pas directement cette
     classe comme "chat_history" interne : `agent_service.py` charge les
     messages via `get_chat_history(...)` puis les injecte tels quels
     dans l'état initial du graphe (`AgentState.messages`). La classe sert
     donc de couche de chargement/formatage propre autour de DynamoDB,
     tout en respectant le contrat LangChain standard.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from config import table
from utils import generate_timestamp, get_expiration_time

# NOTE : les embeddings NE sont PLUS stockés ici. DynamoDB ne sait pas
# faire de recherche vectorielle (k-NN) — les y stocker ne servait qu'à
# gonfler la taille des items pour rien. Les embeddings vivent désormais
# uniquement dans OpenSearch (index "conversation-memory", cf.
# `vector_store.py`), qui est l'outil fait pour ça. Ce module reste
# responsable du texte brut (historique court terme / fenêtre glissante).


class MemoryService:
    """Accès bas niveau (CRUD) à la table DynamoDB des conversations."""

    def __init__(self, dynamodb_table):
        self.table = dynamodb_table

    def save_conversation_turn(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> Dict[str, Any]:
        """Sauvegarde un message (user, assistant ou tool) dans DynamoDB (texte brut, sans embedding)."""
        item = {
            "session_id": session_id,
            "timestamp": generate_timestamp(),
            "role": role,
            "content": content,
            "ttl": get_expiration_time(),
        }

        try:
            self.table.put_item(Item=item)
            return item
        except ClientError as error:
            print(f" Erreur DynamoDB lors de l'écriture : {error}")
            raise

    def save_user_message(self, session_id: str, message: str) -> Dict[str, Any]:
        """Sauvegarde un message utilisateur."""
        return self.save_conversation_turn(session_id, "user", message)

    def save_assistant_response(self, session_id: str, response: str) -> Dict[str, Any]:
        """Sauvegarde une réponse assistant."""
        return self.save_conversation_turn(session_id, "assistant", response)

    def log_tool_call(self, tool_name: str, tool_args: Dict, output: str, duration: float) -> None:
        """
        Journalise un appel d'outil dans une session technique dédiée
        (`__tool_logs__`), séparée des vraies conversations utilisateur.
        Utile pour l'observabilité (CloudWatch + requêtable dans DynamoDB).
        Appelé depuis `graph/nodes.py::call_tools`.
        """
        self.save_conversation_turn(
            session_id="__tool_logs__",
            role="tool",
            content=json.dumps(
                {
                    "tool": tool_name,
                    "args": tool_args,
                    "output": output[:500],  # on tronque pour ne pas gonfler l'item DynamoDB
                    "duration": duration,
                },
                default=str,
            ),
        )

    def get_conversation_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Retourne tout l'historique d'une session, du plus ancien au plus récent."""
        try:
            response = self.table.query(
                KeyConditionExpression=Key("session_id").eq(session_id),
                ScanIndexForward=True,  # tri ascendant : le plus ancien en premier
            )
            return response.get("Items", [])
        except ClientError as error:
            print(f" Erreur DynamoDB lors de la lecture : {error}")
            raise

    def get_recent_history(self, session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Retourne les `limit` derniers échanges (user+assistant), triés du
        plus ancien au plus récent (prêt à être converti en messages
        LangChain dans l'ordre chronologique attendu).
        """
        try:
            response = self.table.query(
                KeyConditionExpression=Key("session_id").eq(session_id),
                ScanIndexForward=False,  # le plus récent d'abord...
                Limit=limit * 2,  # *2 car un "échange" = 1 message user + 1 message assistant
            )
            history = response.get("Items", [])
            history.reverse()  # ...puis on remet dans l'ordre chronologique
            return history
        except ClientError as error:
            print(f" Erreur DynamoDB lors de la lecture : {error}")
            raise

    def batch_save_turn(
        self,
        session_id: str,
        user_message: str,
        assistant_response: str,
    ) -> tuple:
        """
        Sauvegarde un tour complet (message utilisateur + réponse assistant)
        dans DynamoDB, en texte brut uniquement.

        Pour indexer aussi les embeddings de ce tour dans la mémoire
        sémantique long terme, utiliser séparément
        `vector_store.save_document(...)` (voir `agent_service.py` /
        `server.py`) avec le `timestamp` renvoyé ici, pour que les deux
        stores restent alignés sur le même horodatage.
        """
        user_item = self.save_user_message(session_id, user_message)
        assistant_item = self.save_assistant_response(session_id, assistant_response)
        return user_item, assistant_item

    def format_history_response(self, session_id: str, history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Formate l'historique brut pour la réponse API (GET /agent/sessions/{id}/history)."""
        return {"session_id": session_id, "history": history}


# Instance singleton réutilisée dans tout le projet.
memory_service = MemoryService(table)


@dataclass
class DynamoDBChatMessageHistory(BaseChatMessageHistory):
    """
    Historique de conversation "fenêtré" (les N derniers échanges),
    persisté dans DynamoDB.

    Implémente l'interface standard `BaseChatMessageHistory` de LangChain
    (méthodes `messages`, `add_messages`, `clear`) : c'est ce contrat qui
    la rend compatible avec `RunnableWithMessageHistory`, et qui en fait
    le remplaçant "non déprécié" de `ConversationBufferWindowMemory`.
    """

    session_id: str
    window_size: int = 10
    messages: List[BaseMessage] = field(default_factory=list, init=False)
    _raw_items: List[Dict[str, Any]] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        """Charge automatiquement l'historique existant depuis DynamoDB à la création."""
        self._load_from_dynamodb()

    def _load_from_dynamodb(self) -> None:
        """Récupère les derniers échanges de la session et les convertit en messages LangChain."""
        self._raw_items = memory_service.get_recent_history(self.session_id, limit=self.window_size)
        self.messages = [
            HumanMessage(content=item["content"])
            if item["role"] == "user"
            else AIMessage(content=item["content"])
            for item in self._raw_items
        ]

    def add_messages(self, messages: List[BaseMessage]) -> None:
        """
        Ajoute des messages à l'historique en mémoire (méthode requise par
        `BaseChatMessageHistory`) et applique la fenêtre glissante.

        Note : dans ce projet, la persistance réelle d'un nouveau tour se
        fait via `memory_service.batch_save_turn(...)` (DynamoDB), appelée
        depuis `agent_service.py`. Cette méthode gère uniquement l'état en
        mémoire de l'objet le temps d'une exécution.
        """
        self.messages.extend(messages)
        max_messages = self.window_size * 2  # *2 : chaque échange = 1 message user + 1 assistant
        if len(self.messages) > max_messages:
            self.messages = self.messages[-max_messages:]

    def clear(self) -> None:
        """Efface l'historique en mémoire de cet objet (ne supprime pas les items DynamoDB)."""
        self.messages = []
        self._raw_items = []

    @property
    def oldest_timestamp(self) -> Optional[str]:
        """Timestamp du plus ancien message chargé (utile pour filtrer la recherche sémantique)."""
        return self._raw_items[0]["timestamp"] if self._raw_items else None


def get_chat_history(session_id: str, window_size: int = 10) -> DynamoDBChatMessageHistory:
    """Factory : charge l'historique court terme (fenêtré) d'une session depuis DynamoDB."""
    return DynamoDBChatMessageHistory(session_id=session_id, window_size=window_size)


def create_runnable_with_history(runnable, session_id: str, window_size: int = 10):
    """
    Exemple d'utilisation *facultative* de `RunnableWithMessageHistory`,
    pour brancher une simple chaîne LangChain (hors LangGraph) sur cette
    même mémoire DynamoDB fenêtrée. Non utilisé par la boucle ReAct
    principale (qui passe par `AgentState.messages` + le checkpointer du
    graphe), mais gardé ici à titre d'exemple réutilisable ailleurs dans
    le projet (ex: un futur endpoint "résumé rapide" sans outils).
    """
    from langchain_core.runnables.history import RunnableWithMessageHistory

    history = get_chat_history(session_id, window_size)

    def _get_session_history(_session_id: str) -> BaseChatMessageHistory:
        return history

    return RunnableWithMessageHistory(
        runnable=runnable,
        get_session_history=_get_session_history,
        input_messages_key="input",
        history_messages_key="history",
    )
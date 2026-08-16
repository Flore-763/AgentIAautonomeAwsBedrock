"""
graph/state.py
==============

Définition de l'état (State) partagé par tous les nœuds du graphe LangGraph.

Dans LangGraph, le State est un dictionnaire typé (TypedDict) qui circule
d'un nœud à l'autre. Chaque nœud reçoit l'état courant, en lit ce dont il a
besoin, puis retourne un *dictionnaire partiel* contenant uniquement les clés
qu'il souhaite mettre à jour. LangGraph fusionne ensuite ce dictionnaire
partiel avec l'état existant.

Point important pour la liste `messages` : par défaut, LangGraph *remplace*
la valeur d'une clé par la nouvelle valeur retournée par un nœud. Pour une
liste de messages, ce n'est pas ce qu'on veut : on veut *ajouter* les
nouveaux messages à la liste existante, pas l'écraser. C'est le rôle du
"reducer" `add_messages` (via `Annotated[list, add_messages]`) : il indique
à LangGraph "quand un nœud retourne des messages, ajoute-les à la liste
plutôt que de la remplacer".

C'est ce mécanisme qui remplace, dans l'ancienne version, la mutation
manuelle `state["messages"].append(...)` faite directement dans les nœuds
(fragile : ça reposait sur le fait que Python passe les listes par
référence, ce qui casse dès qu'on utilise un vrai checkpointer qui
sérialise/désérialise l'état entre deux nœuds).
"""

from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """État complet de l'agent ReAct, tel qu'il circule dans le graphe."""

    # Identité de l'utilisateur (nécessaire pour les outils comme document_search)
    user_sub: str

    # --- Identité de la conversation (= thread_id du checkpointer) ---
    session_id: str  # namespacé, set de thread_id
    raw_session_id: str  # session_id brut , pour les outils comme document_search
    # --- Fil de discussion complet : System / Human / AI / Tool messages ---
    # `Annotated[List[BaseMessage], add_messages]` = à chaque fois qu'un
    # nœud retourne {"messages": [...]}, LangGraph AJOUTE ces messages à la
    # liste existante au lieu de la remplacer.
    messages: Annotated[List[BaseMessage], add_messages]

    # --- Contexte injecté dans le prompt système (souvenirs long terme) ---
    context: Optional[str]

    # --- Contrôle de la boucle ReAct (garde-fou n°1 : anti-boucle infinie) ---
    iterations: int
    max_iterations: int

    # --- Historique des appels d'outils, pour la détection de boucles ---
    # (garde-fou n°2 : même outil + mêmes paramètres répétés)
    tool_call_history: List[Dict[str, Any]]

    # --- Résultat final de l'exécution du graphe ---
    final_answer: Optional[str]
    error: Optional[str]

    # --- Un fichier vient-il d'être joint à CE tour ? ---
    # Renseigné depuis `recent_attachments` (payload du frontend), permet
    # à `document_search` de savoir qu'il doit être patient (budget de
    # retry plus long) car un document tout juste indexé peut mettre du
    # temps à devenir cherchable côté OpenSearch Serverless — voir
    # tools/document_search.py.
    has_recent_upload: bool

    # Noms des fichiers joints à ce tour précis (sous-ensemble de
    # `has_recent_upload`). Permet à `document_search` de ne pas
    # s'arrêter dès qu'IL TROUVE DES RÉSULTATS si ceux-ci proviennent en
    # fait d'un fichier plus ancien déjà indexé dans la même session,
    # et de continuer à réessayer jusqu'à trouver un extrait du fichier
    # qui vient réellement d'être joint.
    recent_upload_filenames: List[str]
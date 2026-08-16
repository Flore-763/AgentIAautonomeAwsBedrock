"""
graph/nodes.py
==============

Les "nœuds" du graphe LangGraph. Chaque nœud est une simple fonction
Python de la forme (state) -> dict (mise à jour partielle de l'état).

Changement majeur par rapport à l'ancienne version (langgraph_agent.py) :
le pattern ReAct (Reasoning + Acting) est ici implémenté avec le
*tool calling natif* de Claude via l'API Bedrock Converse, et non plus en
demandant au LLM d'écrire du texte au format "Thought / Action / Action
Input" puis en le reparsant avec des regex.

Pourquoi c'est plus robuste :
  - Claude renvoie les appels d'outils dans un champ structuré
    (`AIMessage.tool_calls`), déjà parsé par Bedrock/Anthropic.
  - Il n'y a plus de risque de mauvais format JSON, de regex qui ne matche
    pas, ou de paramètres mal extraits (cf. Bug 2 du cahier des charges :
    "l'agent invente les résultats d'un outil... ou formate mal les
    paramètres, provoquant une erreur d'exécution").
  - L'API Converse de Bedrock exige une correspondance stricte entre
    chaque `tool_use` et son `tool_result` : en générant nous-mêmes des
    `ToolMessage(tool_call_id=...)` correctement liés au `tool_call_id`
    fourni par Claude, on évite les erreurs `ValidationException`
    ("Requete invalide envoyee a Bedrock") qui peuvent survenir quand la
    séquence de messages ne respecte pas ce contrat.
"""

import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Literal

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from graph.react_logger import log_react_step
from graph.state import AgentState
from services.bedrock_service import get_llm_with_tools
from services.memory_service import memory_service
from services.prompt_service import build_system_prompt
from tools import get_tools
from tools.document_search import search_user_documents

# Les outils sont chargés une seule fois par conteneur Lambda (warm start).
_TOOLS = get_tools()
_TOOLS_BY_NAME = {
    tool.name: tool
    for tool in _TOOLS
}

# Nombre de répétitions identiques (même outil + mêmes arguments) à partir
# duquel on considère que l'agent est "en boucle" et on force l'arrêt.
LOOP_THRESHOLD = 3


def call_model(state: AgentState) -> Dict:
    """
    Nœud "cerveau" (Reasoning) : appelle Claude (via Bedrock) avec
    l'historique complet de la conversation + les outils disponibles.

    Le LLM décide lui-même, selon le contexte, s'il doit :
      - répondre directement (AIMessage sans tool_calls) -> fin de la boucle,
      - ou appeler un/plusieurs outils (AIMessage.tool_calls rempli)
        -> on route alors vers le nœud `call_tools`.
    """
    iteration = state["iterations"] + 1
    print(f"🔄 Itération ReAct n°{iteration} (max={state['max_iterations']})")

    llm_with_tools = get_llm_with_tools(_TOOLS)

    # Le system prompt est reconstruit à chaque appel : il porte les
    # instructions générales + le contexte (souvenirs long terme), qui peut
    # varier d'une requête à l'autre.
    system_message = SystemMessage(content=build_system_prompt(state.get("context")))

    # On envoie : [system] + tout l'historique déjà accumulé dans le state
    # (messages précédents de la session + tour courant + éventuels
    # ToolMessage des itérations précédentes de cette même exécution).
    messages_to_send = [system_message] + state["messages"]
    #

    # ici je fais llm_with_tools.stream au lieu de .invoke qui est un appal bloquant.
    start_time = time.time()
    full_ai_message = None
    for chunk in llm_with_tools.stream(messages_to_send):
        full_ai_message = chunk if full_ai_message is None else full_ai_message + chunk
    duration = time.time() - start_time

    requested_tool_calls = [tc["name"] for tc in (full_ai_message.tool_calls or [])]

    log_react_step(
        step="call_model",
        session_id=state["session_id"],
        iteration=iteration,
        duration=duration,
        tool_calls_requested=requested_tool_calls or None,
        answer_preview=(_extract_text(full_ai_message.content) if not requested_tool_calls else None),
    )

    return {
        "messages": [full_ai_message],   # ✅ un vrai message, pas un générateur
        "iterations": iteration,
    }


def call_tools(state: AgentState) -> Dict:
    """
    Nœud "action" (Acting) : exécute tous les outils demandés par le
    dernier AIMessage produit par `call_model`.

    Pour chaque appel d'outil (`tool_call`) :
      1. on retrouve l'outil correspondant par son nom,
      2. on l'exécute avec les arguments fournis par le LLM
         (déjà validés/typés par le schéma de l'outil),
      3. on journalise l'appel (CloudWatch + DynamoDB) pour l'audit/debug,
      4. on construit un `ToolMessage` lié au `tool_call_id` d'origine
         (obligatoire pour que Claude relie sa demande à son résultat).

    Toute exception levée par un outil est interceptée : on renvoie un
    `ToolMessage` d'erreur explicite plutôt que de faire planter tout le
    graphe. L'agent "voit" ainsi l'erreur et peut corriger son action au
    tour suivant (cf. Bug 2 du cahier des charges).
    """
    last_message = state["messages"][-1]
    tool_messages: List[ToolMessage] = []
    new_history_entries = []

    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_call_id = tool_call["id"]

        start_time = time.time()
        tool = _TOOLS_BY_NAME.get(tool_name)

        if tool is None:
            result = (
                f"Erreur : outil '{tool_name}' inconnu. "
                f"Outils disponibles : {list(_TOOLS_BY_NAME)}"
            )
        else:
            try:

                if tool_name == "document_search":

                    query = tool_args.get(
                        "query",
                        "",
                    )

                    result = search_user_documents(
                        query=query,
                        user_sub=state["user_sub"],
                        session_id=state["raw_session_id"],
                        has_recent_upload=state.get("has_recent_upload", False),
                        recent_upload_filenames=state.get("recent_upload_filenames", []),
                    )

                else:

                    result = tool.invoke(
                        tool_args
                    )

            except Exception as exc:

                result = (
                    f"Erreur lors de l'exécution "
                    f"de l'outil '{tool_name}': {exc}"
                )

        duration = time.time() - start_time
        print(f" Outil '{tool_name}' exécuté en {duration:.2f}s -> {str(result)[:200]}")

        tool_messages.append(ToolMessage(content=str(result), tool_call_id=tool_call_id))

        new_history_entries.append(
            {
                "tool": tool_name,
                "args": tool_args,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        # Trace CloudWatch structurée : une ligne par outil exécuté, avec sa
        # propre durée (utile quand plusieurs outils sont appelés en //
        # dans la même itération).
        log_react_step(
            step="call_tools",
            session_id=state["session_id"],
            iteration=state["iterations"],
            duration=duration,
            tool_name=tool_name,
            tool_args=tool_args,
            result_preview=str(result),
        )

        # Journalisation best-effort : un souci de logging ne doit jamais
        # faire planter la boucle de l'agent.
        try:
            memory_service.log_tool_call(tool_name, tool_args, str(result), duration)
        except Exception as log_error:  # pragma: no cover
            print(f"⚠️ Impossible de journaliser l'appel d'outil : {log_error}")

    return {
        "messages": tool_messages,
        "tool_call_history": state["tool_call_history"] + new_history_entries,
    }

def _extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
            if not isinstance(block, dict) or block.get("type") == "text"
        )
    return ""



def finalize(state: AgentState) -> Dict:
    """
    Nœud terminal "succès" : le dernier AIMessage du LLM est la réponse
    finale (aucun outil supplémentaire n'a été demandé).
    """
    last_message = state["messages"][-1]
    final_answer = _extract_text(last_message.content) or "Désolé, je n'ai pas pu générer de réponse."

    print(f"✅ Réponse finale générée après {state['iterations']} itération(s).")
    log_react_step(
        step="finalize",
        session_id=state["session_id"],
        iteration=state["iterations"],
        answer_preview=final_answer,
    )
    return {"final_answer": final_answer}


def handle_max_iterations(state: AgentState) -> Dict:
    """
    Nœud terminal "garde-fou n°1" : le nombre maximum d'itérations a été
    atteint. Protège contre un agent qui boucle indéfiniment entre
    `call_model` et `call_tools` sans jamais conclure (et donc contre une
    explosion de la facture Bedrock / un timeout API Gateway, cf. Bug 3).
    """
    message = (
        f"⚠️ L'agent a atteint le nombre maximum d'itérations "
        f"({state['max_iterations']}) sans conclure. "
        "Voici les dernières informations obtenues avant l'arrêt."
    )
    print(message)
    log_react_step(
        step="max_iterations",
        session_id=state["session_id"],
        iteration=state["iterations"],
        error="max_iterations_reached",
    )
    return {"final_answer": message, "error": "max_iterations_reached"}


def handle_loop_detected(state: AgentState) -> Dict:
    """
    Nœud terminal "garde-fou n°2" : le même outil a été appelé avec
    exactement les mêmes arguments plusieurs fois de suite. On arrête pour
    éviter une boucle infinie.
    """
    message = (
        " L'agent semble bloqué dans une boucle (la même action a été "
        "répétée plusieurs fois). Réponse partielle basée sur les "
        "informations déjà obtenues."
    )
    print(message)
    last_calls = state["tool_call_history"][-LOOP_THRESHOLD:]
    log_react_step(
        step="loop_detected",
        session_id=state["session_id"],
        iteration=state["iterations"],
        error="loop_detected",
        repeated_tool=last_calls[0]["tool"] if last_calls else None,
        repeated_args=last_calls[0]["args"] if last_calls else None,
        repeat_count=LOOP_THRESHOLD,
    )
    return {"final_answer": message, "error": "loop_detected"}


def route_after_model(state: AgentState) -> Literal["call_tools", "finalize", "max_iterations"]:
    """
    Arête conditionnelle exécutée juste après `call_model`.

    Ordre de priorité :
      1. Nombre max d'itérations atteint -> on s'arrête (garde-fou n°1).
      2. Le LLM n'a demandé aucun outil (`tool_calls` vide) -> il a donné
         sa réponse finale -> on va à `finalize`.
      3. Sinon -> le LLM veut utiliser un ou plusieurs outils -> `call_tools`.
    """
    if state["iterations"] >= state["max_iterations"]:
        return "max_iterations"

    last_message = state["messages"][-1]
    tool_calls = getattr(last_message, "tool_calls", None)

    if not tool_calls:
        return "finalize"

    return "call_tools"


def route_after_tools(state: AgentState) -> Literal["call_model", "loop_detected"]:
    """
    Arête conditionnelle exécutée juste après `call_tools`.

    Détection de boucle (garde-fou n°2) : si les `LOOP_THRESHOLD` derniers
    appels d'outils sont rigoureusement identiques (même nom d'outil +
    mêmes arguments), on considère que l'agent est bloqué et on arrête
    plutôt que de le laisser répéter indéfiniment la même action.
    """
    history = state["tool_call_history"]

    if len(history) >= LOOP_THRESHOLD:
        last_calls = history[-LOOP_THRESHOLD:]
        signatures = {
            json.dumps({"tool": call["tool"], "args": call["args"]}, sort_keys=True)
            for call in last_calls
        }
        if len(signatures) == 1:
            print(
                f"🔁 Boucle détectée : '{last_calls[0]['tool']}' répété "
                f"{LOOP_THRESHOLD} fois avec les mêmes arguments."
            )
            return "loop_detected"

    return "call_model"
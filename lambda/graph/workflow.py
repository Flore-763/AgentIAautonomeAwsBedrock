"""
graph/workflow.py
==================

Construction et compilation du graphe LangGraph représentant la boucle
ReAct de l'agent.

Schéma du graphe :

                         ┌──────────────┐
               ┌────────►│  call_model  │
               │         └──────┬───────┘
               │                │  route_after_model
               │       ┌────────┼─────────────┐
               │       ▼        ▼                  ▼
               │  call_tools  finalize   stop_max_iterations
               │       │                       │
               │       │ route_after_tools     │
               │  ┌────┴──────┐                │
               │  ▼           ▼                │
               └─ call_model  loop_detected     │
                                │               │
                                ▼               ▼
                     [END]◄──── (finalize / stop_max_iterations / loop_detected)

- `call_model`  : le LLM réfléchit et décide (répondre ou utiliser un outil).
- `call_tools`  : exécute concrètement les outils demandés par le LLM.
- `finalize`, `stop_max_iterations`, `loop_detected` : les 3 nœuds terminaux
  possibles (succès, garde-fou n°1, garde-fou n°2).

Note : le nœud du garde-fou n°1 est nommé `stop_max_iterations` et non
`max_iterations`, car ce dernier nom est déjà pris par une clé de l'état
(`AgentState.max_iterations`, voir `state.py`) — LangGraph interdit qu'un
nœud et une clé d'état partagent le même nom.

Un `checkpointer` (`MemorySaver`) est branché sur le graphe. Il permet à
LangGraph de sauvegarder l'état complet après chaque nœud, identifié par un
`thread_id` (ici égal à `session_id`). Cela fournit nativement :
  - la reprise d'exécution sur un même thread_id,
  - l'inspection / le "time travel" de l'état à des fins de debug.

⚠️ `MemorySaver` garde tout en RAM : cela ne survit PAS entre deux
invocations Lambda distinctes (chaque invocation peut démarrer sur un
nouveau micro-environnement). C'est pourquoi la mémoire *durable* de la
conversation (au-delà d'une seule exécution du graphe) reste gérée
explicitement par `services/memory_service.py` (DynamoDB), qui réinjecte
l'historique au début de chaque requête (voir `services/agent_service.py`).

Si ce projet est un jour déployé en dehors de Lambda (ECS, EC2 long-lived),
`MemorySaver` peut être remplacé par un checkpointer persistant (par ex.
`langgraph-checkpoint-postgres` ou un checkpointer DynamoDB maison) pour
bénéficier nativement de la persistance sans passer par `memory_service`.
"""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from graph.nodes import (
    call_model,
    call_tools,
    finalize,
    handle_loop_detected,
    handle_max_iterations,
    route_after_model,
    route_after_tools,
)
from graph.state import AgentState

# Créé une seule fois par conteneur Lambda (warm start). Sert de filet de
# sécurité local ; la vraie persistance inter-requêtes passe par DynamoDB
# (services/memory_service.py), voir la note ci-dessus.
_checkpointer = MemorySaver()

# Le graphe compilé est également mis en cache par conteneur, pour éviter
# de reconstruire tout le graphe à chaque invocation Lambda "warm".
_compiled_graph = None


def build_graph():
    """Construit et compile le graphe LangGraph de l'agent ReAct."""

    workflow = StateGraph(AgentState)

    # --- Déclaration des nœuds ---
    workflow.add_node("call_model", call_model)
    workflow.add_node("call_tools", call_tools)
    workflow.add_node("finalize", finalize)
    # ⚠️ Le nom d'un nœud ne doit JAMAIS être identique à une clé de l'état
    # (`AgentState`) : LangGraph lève `ValueError: '<node>' is already being
    # used as a state key`. Le nœud est donc nommé "stop_max_iterations" et
    # non "max_iterations" (qui est déjà une clé de AgentState, voir state.py).
    workflow.add_node("stop_max_iterations", handle_max_iterations)
    workflow.add_node("loop_detected", handle_loop_detected)

    # --- Point d'entrée : on commence toujours par laisser le LLM réfléchir ---
    workflow.set_entry_point("call_model")

    # --- Arête conditionnelle après réflexion du LLM ---
    workflow.add_conditional_edges(
        "call_model",
        route_after_model,
        {
            "call_tools": "call_tools",
            "finalize": "finalize",
            "max_iterations": "stop_max_iterations",
        },
    )

    # --- Arête conditionnelle après exécution des outils ---
    workflow.add_conditional_edges(
        "call_tools",
        route_after_tools,
        {
            "call_model": "call_model",
            "loop_detected": "loop_detected",
        },
    )

    # --- Arêtes terminales : les 3 issues possibles terminent le graphe ---
    workflow.add_edge("finalize", END)
    workflow.add_edge("stop_max_iterations", END)
    workflow.add_edge("loop_detected", END)

    return workflow.compile(checkpointer=_checkpointer)


def get_graph():
    """Retourne le graphe compilé (singleton par conteneur Lambda)."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph

"""
graph/react_logger.py
======================

Journalisation structurée des étapes de la boucle ReAct.

Pourquoi un module dédié plutôt que des `print()` texte libre :
CloudWatch Logs capte automatiquement tout ce qui est écrit sur stdout par
une Lambda — inutile d'utiliser le SDK CloudWatch. Mais pour pouvoir
*interroger* ces logs (CloudWatch Logs Insights, filtres métriques, etc.),
il faut qu'ils soient dans un format structuré (JSON), avec des champs
cohérents d'une étape à l'autre : `step`, `session_id`, `iteration`,
`timestamp`, `duration_ms`.

Exemple de requête CloudWatch Logs Insights rendue possible par ce format :

    fields @timestamp, step, iteration, duration_ms
    | filter type = "react_trace" and session_id = "abc-123"
    | sort @timestamp asc

Chaque nœud du graphe (`call_model`, `call_tools`, `finalize`,
`handle_loop_detected`, `handle_max_iterations`) appelle `log_react_step`
au moins une fois, avec la durée de son propre traitement.
"""

import json
from datetime import datetime, timezone
from typing import Any, Optional


def log_react_step(
    step: str,
    session_id: str,
    iteration: int,
    duration: Optional[float] = None,
    **extra: Any,
) -> None:
    """
    Émet une ligne de log JSON structurée pour une étape ReAct.

    Args:
        step: nom du nœud ("call_model", "call_tools", "finalize",
            "loop_detected", "max_iterations").
        session_id: identifiant de la conversation (= thread_id LangGraph).
        iteration: numéro d'itération ReAct en cours.
        duration: durée de l'étape en secondes (None si non pertinent,
            ex: étape instantanée).
        **extra: champs additionnels propres à l'étape (ex: `tool_name`,
            `tool_calls_requested`, `answer_preview`, `error`...).
    """
    entry = {
        "type": "react_trace",
        "step": step,
        "session_id": session_id,
        "iteration": iteration,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if duration is not None:
        entry["duration_ms"] = round(duration * 1000, 2)

    # On tronque tout champ texte trop long pour ne pas gonfler les logs.
    for key, value in extra.items():
        if isinstance(value, str) and len(value) > 300:
            value = value[:300] + "…"
        entry[key] = value

    # Un print() JSON sur une seule ligne : CloudWatch l'indexe tel quel.
    print(json.dumps(entry, default=str))
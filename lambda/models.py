"""
models.py
===========

Structures de données (dataclasses) utilisées pour documenter/valider les
échanges HTTP de l'API. Non utilisées directement par LangGraph (qui a son
propre état typé dans `graph/state.py`), elles servent surtout de
documentation vivante du contrat d'API et peuvent être réutilisées pour de
la validation ou de la génération de documentation (ex: OpenAPI).
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ChatRequest:
    """Corps attendu pour POST /agent/chat."""
    message: str
    session_id: Optional[str] = None
    max_iterations: Optional[int] = None


@dataclass
class ChatResponse:
    """Corps de la réponse de POST /agent/chat."""
    session_id: str
    message: str
    response: str
    timestamp: str
    iterations: int
    actions: List[dict]
    error: Optional[str] = None


@dataclass
class ChatHistoryItem:
    """Un item d'historique de conversation, tel que stocké/renvoyé par DynamoDB."""
    session_id: str
    timestamp: str
    role: str  # "user", "assistant" ou "tool"
    content: str
    ttl: int
    embedding: Optional[List[float]] = None

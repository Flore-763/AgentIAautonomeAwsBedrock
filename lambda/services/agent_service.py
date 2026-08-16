"""
services/agent_service.py
==========================
Version simplifiée : conserve uniquement la fonction process_chat_message
pour les appels non-streaming.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from decimal import Decimal

from langchain_core.messages import HumanMessage
from graph.workflow import get_graph
from services.bedrock_service import invoke_titan_embedding
from services.memory_service import get_chat_history, memory_service
from services.prompt_service import format_memories_block
from vector_store import vector_store

DEFAULT_MAX_ITERATIONS = 10
HARD_MAX_ITERATIONS = 20
DEFAULT_WINDOW_SIZE = 10

def process_chat_message(
    message: str,
    session_id: Optional[str] = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    user_sub= None,
    window_size: int = DEFAULT_WINDOW_SIZE,
) -> Dict[str, Any]:
    """Traite un message utilisateur (non-streaming)."""
    
    session_id = session_id or str(uuid.uuid4())
    max_iterations = min(max_iterations, HARD_MAX_ITERATIONS)
    
    # 1. Mémoire court terme
    chat_history = get_chat_history(session_id, window_size=window_size)
    
    # 2. Mémoire long terme
    message_embedding = invoke_titan_embedding(message)
    semantic_memories = vector_store.semantic_search(
        embedding=message_embedding,
        session_id=session_id,
        before_timestamp=chat_history.oldest_timestamp,
        k=3,
    )
    context = format_memories_block(semantic_memories)
    
    # 3. Exécution du graphe
    graph = get_graph()
    initial_state = {
        "session_id": session_id,
        "messages": chat_history.messages + [HumanMessage(content=message)],
        "context": context,
        "iterations": 0,
        "max_iterations": max_iterations,
        "tool_call_history": [],
        "final_answer": None,
        "error": None,
    }
    config = {"configurable": {"thread_id": session_id}}
    
    final_state = graph.invoke(initial_state, config=config)
    final_answer = final_state.get("final_answer") or "Désolé, je n'ai pas pu générer de réponse."
    
    # 4. Sauvegarde
    response_embedding = invoke_titan_embedding(final_answer)
    memory_service.batch_save_turn(
        session_id=session_id,
        user_message=message,
        assistant_response=final_answer,
        user_embedding=message_embedding,
        response_embedding=response_embedding,
    )
    
    return {
        "session_id": session_id,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "response": final_answer,
        "iterations": final_state.get("iterations", 0),
        "actions": final_state.get("tool_call_history", []),
        "error": final_state.get("error"),
    }
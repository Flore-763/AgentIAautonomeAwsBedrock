"""
tests/test_server_stream.py
=============================

`process_chat_stream` (server.py) est le vrai point d'entrée en
production (streaming SSE). On mocke toutes ses dépendances externes
(mémoire, embeddings, recherche sémantique, documents, et surtout le
graphe LangGraph lui-même via `get_graph`) pour ne tester QUE
l'assemblage des événements SSE — en particulier la régression corrigée
ici : les garde-fous `handle_max_iterations` / `handle_loop_detected`
(F1 du CDC) doivent produire un événement "token" visible côté client,
pas seulement mettre à jour une variable interne.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, AIMessageChunk

import server as server_module
from server import process_chat_stream, sse_error, sse_event


def _parse_events(sse_lines):
    """Convertit une liste de lignes 'data: {...}\\n\\n' en liste de dicts."""
    events = []
    for line in sse_lines:
        payload = line[len("data: "):].strip()
        events.append(json.loads(payload))
    return events


class TestFormatageSSE:
    def test_sse_event_formate_une_ligne_data_valide(self):
        line = sse_event("token", "Bonjour")
        assert line == 'data: {"type": "token", "data": "Bonjour"}\n\n'

    def test_sse_error_utilise_le_type_error(self):
        line = sse_error("Oups")
        payload = json.loads(line[len("data: "):].strip())
        assert payload == {"type": "error", "data": {"message": "Oups"}}


class TestContentTypeUtf8:
    """
    Régression : sans `charset=utf-8` explicite dans le Content-Type,
    un client HTTP doit deviner l'encodage du corps de la réponse et
    retombe souvent sur Latin-1 — corrompant tous les accents/emojis
    (constaté dans un vrai rapport d'évaluation : "é" -> "Ã©").
    """

    def _fake_handler(self):
        handler = MagicMock()
        handler.wfile = MagicMock()
        # On appelle les VRAIES méthodes non-réseau de AgentHandler sur ce
        # mock, pour vérifier les en-têtes envoyés sans monter un vrai
        # serveur HTTP.
        handler._send_json_response = server_module.AgentHandler._send_json_response.__get__(handler)
        return handler

    def test_reponse_json_annonce_le_charset_utf8(self):
        handler = self._fake_handler()
        handler._send_json_response(200, {"ok": True})
        content_type_calls = [c for c in handler.send_header.call_args_list if c.args[0] == "Content-Type"]
        assert content_type_calls[0].args[1] == "application/json; charset=utf-8"

    def test_stream_chat_annonce_le_charset_utf8(self):
        # On vérifie directement le code source plutôt que d'exécuter tout
        # `_handle_stream_chat` (trop de dépendances HTTP réelles à monter
        # pour un test unitaire) : ce test échoue si quelqu'un retire le
        # charset par erreur dans un futur refactor.
        source = Path(server_module.__file__).read_text(encoding="utf-8")
        assert "text/event-stream; charset=utf-8" in source


def _common_mocks():
    """
    Contexte commun mocké pour tous les tests de `process_chat_stream` :
    historique vide, pas de mémoire long terme, pas de documents.
    Chaque test ne fournit que ce qui lui est spécifique (le comportement
    du graphe).
    """
    fake_history = MagicMock()
    fake_history.messages = []
    fake_history.oldest_timestamp = None
    return {
        "get_chat_history": patch.object(server_module, "get_chat_history", return_value=fake_history),
        "invoke_titan_embedding": patch.object(server_module, "invoke_titan_embedding", return_value=[0.1]),
        "semantic_search": patch.object(server_module.vector_store, "semantic_search", return_value=[]),
        "list_session_documents": patch.object(server_module, "list_session_documents", return_value=[]),
    }


class TestGardeFousVisiblesCotesClient:
    """
    Reproduit la régression : avant le correctif, un `graph.stream` qui
    finit par router vers `handle_max_iterations` ou `handle_loop_detected`
    ne produisait AUCUN événement "token" -> l'utilisateur voyait une
    réponse vide (cf. UI.py, qui n'affiche QUE les événements "token").
    """

    def _run_with_fake_graph_updates(self, chunks):
        """`chunks` : liste de (mode, chunk) tels que renvoyés par graph.stream()."""
        fake_graph = MagicMock()
        fake_graph.stream.return_value = iter(chunks)

        mocks = _common_mocks()
        with mocks["get_chat_history"], mocks["invoke_titan_embedding"], \
             mocks["semantic_search"], mocks["list_session_documents"], \
             patch.object(server_module, "get_graph", return_value=fake_graph):
            events = list(
                process_chat_stream(message="Bonjour", user_sub="user-1", session_id="sess-1")
            )
        return _parse_events(events)

    def test_max_iterations_produit_un_token_visible(self):
        guard_message = "⚠️ Nombre maximum d'itérations atteint."
        chunks = [
            ("updates", {"handle_max_iterations": {"final_answer": guard_message, "error": "max_iterations_reached"}}),
        ]
        events = self._run_with_fake_graph_updates(chunks)

        token_events = [e for e in events if e["type"] == "token"]
        assert any(e["data"] == guard_message for e in token_events)

    def test_loop_detected_produit_un_token_visible(self):
        guard_message = "🔁 Boucle détectée, arrêt de l'agent."
        chunks = [
            ("updates", {"handle_loop_detected": {"final_answer": guard_message, "error": "loop_detected"}}),
        ]
        events = self._run_with_fake_graph_updates(chunks)

        token_events = [e for e in events if e["type"] == "token"]
        assert any(e["data"] == guard_message for e in token_events)

    def test_chemin_normal_nest_pas_double(self):
        # Chemin de succès normal : le texte est déjà streamé via les
        # AIMessageChunk ("messages" mode) PUIS `finalize` s'exécute
        # ("updates" mode). Le correctif ne doit RIEN ajouter de plus
        # dans ce cas (pas de double-emission).
        chunk = AIMessageChunk(content="Réponse finale.")
        chunks = [
            ("messages", (chunk, {})),
            ("updates", {"finalize": {"final_answer": "Réponse finale."}}),
        ]
        events = self._run_with_fake_graph_updates(chunks)

        token_events = [e for e in events if e["type"] == "token"]
        assert [e["data"] for e in token_events] == ["Réponse finale."]

    def test_step_events_toujours_emis_pour_chaque_noeud(self):
        chunks = [
            ("updates", {"call_tools": {"messages": []}}),
            ("updates", {"handle_loop_detected": {"final_answer": "Boucle.", "error": "loop_detected"}}),
        ]
        events = self._run_with_fake_graph_updates(chunks)

        step_nodes = [e["data"]["node"] for e in events if e["type"] == "step"]
        assert step_nodes == ["call_tools", "handle_loop_detected"]

    def test_session_event_emis_en_premier(self):
        events = self._run_with_fake_graph_updates([])
        assert events[0]["type"] == "session"
        assert events[0]["data"]["session_id"] == "sess-1"

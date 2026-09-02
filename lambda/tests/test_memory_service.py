"""
tests/test_memory_service.py
==============================

Aucun appel DynamoDB réel : `MemoryService` est instancié avec une table
factice (`MagicMock`), comme le recommande le CDC ("tests unitaires...
mock"). Ça permet de vérifier la logique (clés utilisées, format des
items, gestion d'erreur, fenêtre glissante) indépendamment d'AWS.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from langchain_core.messages import AIMessage, HumanMessage

from services.memory_service import DynamoDBChatMessageHistory, MemoryService


@pytest.fixture
def fake_table():
    return MagicMock()


@pytest.fixture
def memory(fake_table):
    return MemoryService(fake_table)


class TestSauvegarde:
    def test_save_conversation_turn_ecrit_les_bons_champs(self, memory, fake_table):
        item = memory.save_conversation_turn("sess-1", "user", "Bonjour")

        fake_table.put_item.assert_called_once()
        written_item = fake_table.put_item.call_args.kwargs["Item"]
        assert written_item["session_id"] == "sess-1"
        assert written_item["role"] == "user"
        assert written_item["content"] == "Bonjour"
        assert "timestamp" in written_item
        assert "ttl" in written_item
        assert item == written_item

    def test_aucun_champ_embedding_nest_ecrit(self, memory, fake_table):
        # Régression : les embeddings ne doivent plus jamais transiter par
        # DynamoDB (ils vivent uniquement dans OpenSearch désormais).
        memory.save_conversation_turn("sess-1", "assistant", "Réponse")
        written_item = fake_table.put_item.call_args.kwargs["Item"]
        assert "embedding" not in written_item

    def test_save_user_message_utilise_le_role_user(self, memory, fake_table):
        memory.save_user_message("sess-1", "Question")
        assert fake_table.put_item.call_args.kwargs["Item"]["role"] == "user"

    def test_save_assistant_response_utilise_le_role_assistant(self, memory, fake_table):
        memory.save_assistant_response("sess-1", "Réponse")
        assert fake_table.put_item.call_args.kwargs["Item"]["role"] == "assistant"

    def test_batch_save_turn_sauvegarde_les_deux_messages(self, memory, fake_table):
        user_item, assistant_item = memory.batch_save_turn("sess-1", "Question", "Réponse")

        assert fake_table.put_item.call_count == 2
        assert user_item["role"] == "user" and user_item["content"] == "Question"
        assert assistant_item["role"] == "assistant" and assistant_item["content"] == "Réponse"

    def test_erreur_dynamodb_est_propagee(self, memory, fake_table):
        fake_table.put_item.side_effect = ClientError(
            {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "throttled"}},
            "PutItem",
        )
        with pytest.raises(ClientError):
            memory.save_user_message("sess-1", "Question")


class TestJournalisationDesOutils:
    def test_log_tool_call_utilise_une_session_technique_dediee(self, memory, fake_table):
        memory.log_tool_call("calculator", {"expression": "1+1"}, "2", 0.123)

        written_item = fake_table.put_item.call_args.kwargs["Item"]
        assert written_item["session_id"] == "__tool_logs__"
        assert written_item["role"] == "tool"

        payload = json.loads(written_item["content"])
        assert payload["tool"] == "calculator"
        assert payload["args"] == {"expression": "1+1"}
        assert payload["output"] == "2"
        assert payload["duration"] == 0.123

    def test_log_tool_call_tronque_les_sorties_trop_longues(self, memory, fake_table):
        long_output = "x" * 1000
        memory.log_tool_call("recherche_documentaire", {}, long_output, 1.0)

        payload = json.loads(fake_table.put_item.call_args.kwargs["Item"]["content"])
        assert len(payload["output"]) == 500


class TestLecture:
    def test_get_conversation_history_trie_du_plus_ancien_au_plus_recent(self, memory, fake_table):
        fake_table.query.return_value = {"Items": [{"role": "user", "content": "a"}]}
        result = memory.get_conversation_history("sess-1")

        assert result == [{"role": "user", "content": "a"}]
        assert fake_table.query.call_args.kwargs["ScanIndexForward"] is True

    def test_get_recent_history_remet_dans_lordre_chronologique(self, memory, fake_table):
        # DynamoDB renvoie du plus récent au plus ancien (ScanIndexForward=False) ;
        # get_recent_history doit inverser pour obtenir l'ordre chronologique.
        fake_table.query.return_value = {
            "Items": [
                {"role": "assistant", "content": "3e message", "timestamp": "t3"},
                {"role": "user", "content": "2e message", "timestamp": "t2"},
                {"role": "assistant", "content": "1er message", "timestamp": "t1"},
            ]
        }
        result = memory.get_recent_history("sess-1", limit=5)

        assert [item["content"] for item in result] == ["1er message", "2e message", "3e message"]
        assert fake_table.query.call_args.kwargs["Limit"] == 10  # limit * 2

    def test_erreur_lecture_est_propagee(self, memory, fake_table):
        fake_table.query.side_effect = ClientError(
            {"Error": {"Code": "InternalServerError", "Message": "boom"}}, "Query"
        )
        with pytest.raises(ClientError):
            memory.get_conversation_history("sess-1")


class TestFenetreGlissanteChatHistory:
    """
    `DynamoDBChatMessageHistory` : le remplaçant non-déprécié de
    `ConversationBufferWindowMemory` (cf. docstring du module). On mocke
    `memory_service.get_recent_history` pour ne pas dépendre de DynamoDB.
    """

    @patch("services.memory_service.memory_service.get_recent_history")
    def test_charge_et_convertit_lhistorique_au_demarrage(self, mock_get_recent):
        mock_get_recent.return_value = [
            {"role": "user", "content": "Bonjour", "timestamp": "t1"},
            {"role": "assistant", "content": "Salut !", "timestamp": "t2"},
        ]

        history = DynamoDBChatMessageHistory(session_id="sess-1", window_size=5)

        assert len(history.messages) == 2
        assert isinstance(history.messages[0], HumanMessage)
        assert isinstance(history.messages[1], AIMessage)
        mock_get_recent.assert_called_once_with("sess-1", limit=5)

    @patch("services.memory_service.memory_service.get_recent_history", return_value=[])
    def test_oldest_timestamp_none_si_historique_vide(self, mock_get_recent):
        history = DynamoDBChatMessageHistory(session_id="sess-1")
        assert history.oldest_timestamp is None

    @patch(
        "services.memory_service.memory_service.get_recent_history",
        return_value=[{"role": "user", "content": "Bonjour", "timestamp": "2026-01-01T00:00:00"}],
    )
    def test_oldest_timestamp_retourne_le_plus_ancien(self, mock_get_recent):
        history = DynamoDBChatMessageHistory(session_id="sess-1")
        assert history.oldest_timestamp == "2026-01-01T00:00:00"

    @patch("services.memory_service.memory_service.get_recent_history", return_value=[])
    def test_add_messages_applique_la_fenetre_glissante(self, mock_get_recent):
        history = DynamoDBChatMessageHistory(session_id="sess-1", window_size=2)
        # 3 échanges (6 messages) alors que la fenêtre n'en garde que 2 (4 messages).
        for i in range(3):
            history.add_messages([HumanMessage(content=f"Q{i}"), AIMessage(content=f"R{i}")])

        assert len(history.messages) == 4
        assert history.messages[0].content == "Q1"  # le plus ancien échange a été éjecté

    @patch("services.memory_service.memory_service.get_recent_history", return_value=[])
    def test_clear_vide_lhistorique_en_memoire(self, mock_get_recent):
        history = DynamoDBChatMessageHistory(session_id="sess-1")
        history.add_messages([HumanMessage(content="Q")])
        history.clear()
        assert history.messages == []
        assert history.oldest_timestamp is None

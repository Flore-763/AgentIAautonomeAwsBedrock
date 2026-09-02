"""
tests/test_rate_limit_service.py
==================================

`check_and_increment` est testé avec `_table` remplacée par un mock : ni
vrai DynamoDB, ni vraie horloge système imprévisible (on ne teste jamais
le TIMING réel, seulement la logique : clé de fenêtre, comparaison au
seuil, fail-open).
"""

import time
from unittest.mock import patch

from botocore.exceptions import ClientError

from services import rate_limit_service


class TestFailOpen:
    """
    "Fail-open volontaire" (cf. docstring du module) : un souci
    d'infrastructure ne doit JAMAIS bloquer l'agent.
    """

    def test_table_non_configuree_autorise_toujours(self):
        with patch.object(rate_limit_service, "_table", None):
            allowed, count = rate_limit_service.check_and_increment("api-key-1")
        assert allowed is True
        assert count == 0

    def test_api_key_vide_autorise_toujours(self):
        with patch.object(rate_limit_service, "_table") as mock_table:
            allowed, count = rate_limit_service.check_and_increment("")
        assert allowed is True
        assert count == 0
        mock_table.update_item.assert_not_called()

    def test_erreur_dynamodb_autorise_par_defaut(self):
        with patch.object(rate_limit_service, "_table") as mock_table:
            mock_table.update_item.side_effect = ClientError(
                {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "throttled"}},
                "UpdateItem",
            )
            allowed, count = rate_limit_service.check_and_increment("api-key-1")
        assert allowed is True
        assert count == 0


class TestLimiteNominale:
    def test_sous_la_limite_est_autorise(self):
        with patch.object(rate_limit_service, "_table") as mock_table:
            mock_table.update_item.return_value = {"Attributes": {"request_count": 42}}
            allowed, count = rate_limit_service.check_and_increment("api-key-1")
        assert allowed is True
        assert count == 42

    def test_exactement_la_limite_est_autorise(self):
        with patch.object(rate_limit_service, "_table") as mock_table:
            mock_table.update_item.return_value = {"Attributes": {"request_count": 100}}
            allowed, count = rate_limit_service.check_and_increment("api-key-1")
        assert allowed is True
        assert count == 100

    def test_au_dela_de_la_limite_est_refuse(self):
        with patch.object(rate_limit_service, "_table") as mock_table:
            mock_table.update_item.return_value = {"Attributes": {"request_count": 101}}
            allowed, count = rate_limit_service.check_and_increment("api-key-1")
        assert allowed is False
        assert count == 101

    def test_la_limite_configuree_est_bien_100(self):
        # Verrouille la valeur exacte attendue par le CDC (F4 : "100 requêtes/minute").
        assert rate_limit_service.REQUESTS_PER_MINUTE == 100


class TestCleDeFenetre:
    def test_utilise_une_cle_par_api_key_et_fenetre(self):
        with patch.object(rate_limit_service, "_table") as mock_table, \
             patch.object(rate_limit_service, "_current_window", return_value=12345):
            mock_table.update_item.return_value = {"Attributes": {"request_count": 1}}
            rate_limit_service.check_and_increment("api-key-abc")

        call_kwargs = mock_table.update_item.call_args.kwargs
        assert call_kwargs["Key"] == {"rate_limit_key": "api-key-abc#12345"}

    def test_increment_est_atomique_via_add(self):
        with patch.object(rate_limit_service, "_table") as mock_table:
            mock_table.update_item.return_value = {"Attributes": {"request_count": 1}}
            rate_limit_service.check_and_increment("api-key-1")

        call_kwargs = mock_table.update_item.call_args.kwargs
        assert "ADD request_count :one" in call_kwargs["UpdateExpression"]
        assert call_kwargs["ExpressionAttributeValues"][":one"] == 1

    def test_deux_cles_differentes_ne_partagent_pas_le_compteur(self):
        with patch.object(rate_limit_service, "_table") as mock_table:
            mock_table.update_item.return_value = {"Attributes": {"request_count": 1}}
            rate_limit_service.check_and_increment("api-key-A")
            rate_limit_service.check_and_increment("api-key-B")

        keys_used = [c.kwargs["Key"]["rate_limit_key"] for c in mock_table.update_item.call_args_list]
        assert keys_used[0] != keys_used[1]
        assert "api-key-A" in keys_used[0]
        assert "api-key-B" in keys_used[1]

    def test_ttl_est_dans_le_futur_avec_la_marge_attendue(self):
        with patch.object(rate_limit_service, "_table") as mock_table:
            mock_table.update_item.return_value = {"Attributes": {"request_count": 1}}
            before = int(time.time())
            rate_limit_service.check_and_increment("api-key-1")
            after = int(time.time())

        ttl = mock_table.update_item.call_args.kwargs["ExpressionAttributeValues"][":ttl"]
        expected_min = before + rate_limit_service.WINDOW_SECONDS + rate_limit_service.TTL_MARGIN_SECONDS
        expected_max = after + rate_limit_service.WINDOW_SECONDS + rate_limit_service.TTL_MARGIN_SECONDS
        assert expected_min <= ttl <= expected_max

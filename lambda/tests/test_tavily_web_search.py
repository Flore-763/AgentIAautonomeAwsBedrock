"""
tests/test_tavily_web_search.py
=================================

Deux dépendances externes à mocker :
  1. Secrets Manager (`_get_tavily_api_key`, via `_secrets_client`) —
     jamais de vrai appel Secrets Manager.
  2. `requests.post` vers l'API Tavily.

Chaque test réinitialise le cache mémoire du module
(`_tavily_api_key_cache`) pour ne pas dépendre de l'ordre d'exécution
des tests (le cache "warm start" est justement fait pour survivre entre
appels, ce qui casserait l'isolation des tests s'il n'était pas remis
à zéro).
"""

import importlib
from unittest.mock import MagicMock, patch

import pytest
import requests
from botocore.exceptions import ClientError

# NOTE : on ne fait PAS `import tools.tavily_web_search as tavily_module`.
# `tools/__init__.py` fait `from .tavily_web_search import tavily_web_search`,
# ce qui écrase l'attribut `tavily_web_search` du package `tools` (le
# SOUS-MODULE) par l'OUTIL lui-même (même nom). `importlib.import_module`
# contourne ce piège en allant chercher le vrai module dans `sys.modules`.
tavily_module = importlib.import_module("tools.tavily_web_search")
tavily_web_search = tavily_module.tavily_web_search


@pytest.fixture(autouse=True)
def _reset_key_cache():
    """Isole chaque test : pas de fuite du cache mémoire entre les tests."""
    tavily_module._tavily_api_key_cache = None
    yield
    tavily_module._tavily_api_key_cache = None


def _mock_post_response(json_data, status_ok=True):
    mock = MagicMock()
    mock.json.return_value = json_data
    mock.raise_for_status.return_value = None if status_ok else None
    if not status_ok:
        mock.raise_for_status.side_effect = requests.exceptions.HTTPError("boom")
    return mock


class TestRecuperationDeLaCle:
    def test_repli_sur_env_local_si_present(self, monkeypatch):
        # Repli dev local : si TAVILY_API_KEY est positionnée à la main,
        # on ne doit PAS appeler Secrets Manager.
        monkeypatch.setenv("TAVILY_API_KEY", "cle-locale-de-test")
        with patch.object(tavily_module, "_secrets_client") as mock_secrets:
            key = tavily_module._get_tavily_api_key()
            assert key == "cle-locale-de-test"
            mock_secrets.get_secret_value.assert_not_called()
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    def test_va_chercher_dans_secrets_manager(self, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        with patch.object(tavily_module, "_secrets_client") as mock_secrets:
            mock_secrets.get_secret_value.return_value = {"SecretString": "cle-secrets-manager"}
            key = tavily_module._get_tavily_api_key()
            assert key == "cle-secrets-manager"
            mock_secrets.get_secret_value.assert_called_once()

    def test_met_en_cache_apres_le_premier_appel(self, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        with patch.object(tavily_module, "_secrets_client") as mock_secrets:
            mock_secrets.get_secret_value.return_value = {"SecretString": "cle-secrets-manager"}
            tavily_module._get_tavily_api_key()
            tavily_module._get_tavily_api_key()
            # Un seul appel réseau malgré 2 lectures : c'est le cache "warm start".
            assert mock_secrets.get_secret_value.call_count == 1

    def test_erreur_secrets_manager_renvoie_none(self, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        with patch.object(tavily_module, "_secrets_client") as mock_secrets:
            mock_secrets.get_secret_value.side_effect = ClientError(
                {"Error": {"Code": "ResourceNotFoundException", "Message": "no"}},
                "GetSecretValue",
            )
            assert tavily_module._get_tavily_api_key() is None


class TestRechercheWeb:
    def test_pas_de_cle_renvoie_message_explicite(self, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        with patch.object(tavily_module, "_secrets_client") as mock_secrets:
            mock_secrets.get_secret_value.side_effect = ClientError(
                {"Error": {"Code": "ResourceNotFoundException", "Message": "no"}},
                "GetSecretValue",
            )
            result = tavily_web_search.invoke({"query": "météo à Casablanca"})
        assert "Erreur Tavily" in result
        assert "cle" in result.lower() or "clé" in result.lower()

    def test_reponse_avec_synthese_et_sources(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "cle-test")
        payload = {
            "answer": "Le ciel est dégagé.",
            "results": [
                {"title": "Météo Casablanca", "url": "https://exemple.com/meteo", "content": "..."}
            ],
        }
        with patch("tools.tavily_web_search.requests.post", return_value=_mock_post_response(payload)) as mock_post:
            result = tavily_web_search.invoke({"query": "météo à Casablanca"})

        assert "Le ciel est dégagé." in result
        assert "Météo Casablanca" in result
        assert "https://exemple.com/meteo" in result
        # Vérifie que la clé récupérée est bien celle envoyée à Tavily.
        assert mock_post.call_args.kwargs["json"]["api_key"] == "cle-test"
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    def test_aucun_resultat_pertinent(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "cle-test")
        with patch("tools.tavily_web_search.requests.post", return_value=_mock_post_response({"answer": None, "results": []})):
            result = tavily_web_search.invoke({"query": "xyzzy inexistant"})
        assert "Aucun resultat" in result
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    def test_erreur_reseau(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "cle-test")
        with patch(
            "tools.tavily_web_search.requests.post",
            side_effect=requests.exceptions.ConnectionError("DNS failure"),
        ):
            result = tavily_web_search.invoke({"query": "test"})
        assert "Erreur reseau" in result
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    def test_reponse_json_invalide(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "cle-test")
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = ValueError("bad json")
        with patch("tools.tavily_web_search.requests.post", return_value=mock_response):
            result = tavily_web_search.invoke({"query": "test"})
        assert "Erreur Tavily" in result
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    def test_tronque_les_extraits_trop_longs(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "cle-test")
        long_content = "x" * 1000
        payload = {"answer": None, "results": [{"title": "T", "url": "https://x.com", "content": long_content}]}
        with patch("tools.tavily_web_search.requests.post", return_value=_mock_post_response(payload)):
            result = tavily_web_search.invoke({"query": "test"})
        assert "..." in result
        assert len(result) < len(long_content) + 200
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)


class TestOutilLangChain:
    def test_nom_de_loutil(self):
        assert tavily_web_search.name == "tavily_web_search"

    def test_description_non_vide(self):
        assert tavily_web_search.description

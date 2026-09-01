"""
tests/test_weather.py
=======================

L'outil météo fait 2 appels HTTP réels (géocodage + prévisions) vers
Open-Meteo. On mocke systématiquement `requests.get` — jamais d'appel
réseau réel dans ces tests.
"""

from unittest.mock import MagicMock, patch

import requests

from tools.weather import get_weather


def _mock_response(json_data, status_ok=True):
    mock = MagicMock()
    mock.json.return_value = json_data
    if status_ok:
        mock.raise_for_status.return_value = None
    else:
        mock.raise_for_status.side_effect = requests.exceptions.HTTPError("boom")
    return mock


GEO_OK = {
    "results": [
        {"name": "Casablanca", "country": "Maroc", "latitude": 33.59, "longitude": -7.62}
    ]
}
FORECAST_OK = {
    "current": {"temperature_2m": 24.3, "weather_code": 1, "wind_speed_10m": 12.0}
}


class TestMeteoSucces:
    @patch("tools.weather.requests.get")
    def test_retourne_la_meteo_formatee(self, mock_get):
        mock_get.side_effect = [_mock_response(GEO_OK), _mock_response(FORECAST_OK)]

        result = get_weather.invoke({"city": "Casablanca"})

        assert "Casablanca" in result
        assert "Maroc" in result
        assert "24.3" in result
        assert "12.0" in result
        assert "plutôt dégagé" in result  # code météo 1
        assert mock_get.call_count == 2

    @patch("tools.weather.requests.get")
    def test_utilise_bien_les_coordonnees_geocodees_pour_les_previsions(self, mock_get):
        mock_get.side_effect = [_mock_response(GEO_OK), _mock_response(FORECAST_OK)]

        get_weather.invoke({"city": "Casablanca"})

        forecast_call = mock_get.call_args_list[1]
        assert forecast_call.kwargs["params"]["latitude"] == 33.59
        assert forecast_call.kwargs["params"]["longitude"] == -7.62

    @patch("tools.weather.requests.get")
    def test_code_meteo_inconnu_ne_fait_pas_planter(self, mock_get):
        forecast_unknown_code = {
            "current": {"temperature_2m": 10.0, "weather_code": 9999, "wind_speed_10m": 5.0}
        }
        mock_get.side_effect = [_mock_response(GEO_OK), _mock_response(forecast_unknown_code)]

        result = get_weather.invoke({"city": "Casablanca"})
        assert "conditions inconnues" in result


class TestMeteoErreurs:
    @patch("tools.weather.requests.get")
    def test_ville_introuvable(self, mock_get):
        mock_get.return_value = _mock_response({"results": []})

        result = get_weather.invoke({"city": "Villeimaginaire123"})

        assert "introuvable" in result
        # Le géocodage a échoué : pas d'appel de prévisions inutile.
        assert mock_get.call_count == 1

    @patch("tools.weather.requests.get")
    def test_erreur_reseau_geocodage(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError("DNS failure")

        result = get_weather.invoke({"city": "Casablanca"})

        assert "Erreur réseau" in result
        assert "Casablanca" in result

    @patch("tools.weather.requests.get")
    def test_erreur_http_sur_les_previsions(self, mock_get):
        mock_get.side_effect = [
            _mock_response(GEO_OK),
            _mock_response({}, status_ok=False),
        ]

        result = get_weather.invoke({"city": "Casablanca"})
        assert "Erreur réseau" in result

    @patch("tools.weather.requests.get")
    def test_timeout(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("trop long")

        result = get_weather.invoke({"city": "Casablanca"})
        assert "Erreur réseau" in result


class TestOutilLangChain:
    def test_nom_de_loutil(self):
        assert get_weather.name == "get_weather"

    def test_description_non_vide(self):
        assert get_weather.description

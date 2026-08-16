"""
tools/weather.py
==================

Outil météo : récupère la météo ACTUELLE et RÉELLE d'une ville via l'API
publique Open-Meteo (https://open-meteo.com), gratuite et sans clé d'API.

⚠️ Dans l'ancienne version (langgraph_agent.py), cet outil se contentait
de tirer une météo au hasard (`random.choice`). Cela satisfaisait la
mécanique de démonstration du pattern ReAct, mais pas l'US 3.1 du cahier
des charges ("je veux que l'agent puisse récupérer des données en temps
réel via une API externe"). Ici, l'appel est réel.

Deux requêtes HTTP sont nécessaires :
  1. Géocodage : convertir le nom de la ville en coordonnées (lat/lon).
  2. Prévisions : récupérer les conditions actuelles pour ces coordonnées.

En cas d'indisponibilité réseau (timeout, DNS, Lambda dans un VPC privé
sans NAT Gateway, etc.), l'outil renvoie un message d'erreur texte plutôt
que de lever une exception qui ferait planter tout le graphe : c'est le
LLM qui décide quoi faire de cette information (informer l'utilisateur,
proposer de réessayer, etc.) — voir `graph/nodes.py::call_tools` qui capture
de toute façon les exceptions résiduelles.
"""

import requests
from langchain_core.tools import tool

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT_SECONDS = 5

# Codes météo WMO (norme utilisée par Open-Meteo) -> description en français.
_WEATHER_CODES = {
    0: "ciel dégagé", 1: "plutôt dégagé", 2: "partiellement nuageux", 3: "couvert",
    45: "brouillard", 48: "brouillard givrant",
    51: "bruine légère", 53: "bruine modérée", 55: "bruine dense",
    56: "bruine verglaçante légère", 57: "bruine verglaçante dense",
    61: "pluie légère", 63: "pluie modérée", 65: "forte pluie",
    66: "pluie verglaçante légère", 67: "pluie verglaçante forte",
    71: "neige légère", 73: "neige modérée", 75: "forte neige", 77: "grains de neige",
    80: "averses légères", 81: "averses modérées", 82: "averses violentes",
    85: "averses de neige légères", 86: "averses de neige fortes",
    95: "orage", 96: "orage avec grêle légère", 99: "orage avec forte grêle",
}


@tool
def get_weather(city: str) -> str:
    """
    Récupère la météo actuelle réelle pour une ville donnée.

    À utiliser quand l'utilisateur demande la météo, la température ou les
    conditions climatiques d'un lieu précis.

    Args:
        city: Le nom de la ville (ex: "Ouagadougou", "Casablanca", "Paris").

    Returns:
        Une description textuelle de la météo actuelle (température,
        condition, vent), ou un message d'erreur si la ville est
        introuvable ou si le service est indisponible.
    """
    try:
        geo_response = requests.get(
            GEOCODING_URL,
            params={"name": city, "count": 1, "language": "fr"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        geo_response.raise_for_status()
        results = geo_response.json().get("results")

        if not results:
            return f"Ville '{city}' introuvable dans la base de géocodage."

        location = results[0]
        latitude, longitude = location["latitude"], location["longitude"]
        resolved_name = location.get("name", city)
        country = location.get("country", "")

        forecast_response = requests.get(
            FORECAST_URL,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": "temperature_2m,weather_code,wind_speed_10m",
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        forecast_response.raise_for_status()
        current = forecast_response.json().get("current", {})

        temperature = current.get("temperature_2m")
        wind_speed = current.get("wind_speed_10m")
        weather_code = current.get("weather_code")
        condition = _WEATHER_CODES.get(weather_code, "conditions inconnues")

        return (
            f"Météo actuelle à {resolved_name}, {country} : {temperature}°C, "
            f"{condition}, vent à {wind_speed} km/h."
        )

    except requests.exceptions.RequestException as error:
        return f"Erreur réseau lors de la récupération de la météo pour '{city}' : {error}"

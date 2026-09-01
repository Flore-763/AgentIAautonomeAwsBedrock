"""
tools/tavily_web_search.py
==========================

Outil de recherche web via Tavily.

La clé API n'est PLUS lue depuis une variable d'environnement en clair
(`TAVILY_API_KEY`) : elle vient de Secrets Manager, récupérée une seule
fois par "warm start" du conteneur Lambda et mise en cache en mémoire
(même principe que le cache JWKS de `services/auth_service.py`). Ça
évite d'avoir à refournir la clé à chaque `cdk deploy` (elle est stockée
une bonne fois pour toutes dans Secrets Manager, cf. `aws_ai_agent_stack.py`).
"""

import os
from typing import Any, Dict, List

import boto3
import requests
from botocore.exceptions import ClientError
from langchain_core.tools import tool

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
REQUEST_TIMEOUT_SECONDS = 10
DEFAULT_MAX_RESULTS = 5

TAVILY_SECRET_NAME = os.getenv("TAVILY_SECRET_NAME")
_AWS_REGION = os.getenv("BEDROCK_REGION", "us-west-2")

_secrets_client = boto3.client("secretsmanager", region_name=_AWS_REGION)

# Cache mémoire du conteneur Lambda : récupéré une seule fois par
# "warm start", pas à chaque appel de l'outil.
_tavily_api_key_cache: str | None = None


def _get_tavily_api_key() -> str | None:
    """Récupère la clé Tavily depuis Secrets Manager (avec cache warm-start)."""
    global _tavily_api_key_cache
    if _tavily_api_key_cache is not None:
        return _tavily_api_key_cache

    # Repli pratique pour le dev local / tests hors AWS (docker-compose,
    # `python server.py` en local avec un .env, etc.) : si quelqu'un
    # définit encore TAVILY_API_KEY à la main, on l'honore sans forcer
    # un appel Secrets Manager.
    local_override = os.getenv("TAVILY_API_KEY")
    if local_override:
        _tavily_api_key_cache = local_override
        return _tavily_api_key_cache

    if not TAVILY_SECRET_NAME:
        return None

    try:
        response = _secrets_client.get_secret_value(SecretId=TAVILY_SECRET_NAME)
        _tavily_api_key_cache = response["SecretString"]
        return _tavily_api_key_cache
    except ClientError as error:
        print(f"Erreur Secrets Manager lors de la récupération de la clé Tavily : {error}")
        return None


def _format_results(results: List[Dict[str, Any]]) -> str:
    """Formate les resultats Tavily pour qu'ils soient faciles a exploiter par le LLM."""
    formatted = []

    for index, result in enumerate(results, 1):
        title = result.get("title") or "Titre indisponible"
        url = result.get("url") or "URL indisponible"
        content = result.get("content") or result.get("snippet") or ""
        score = result.get("score")

        if len(content) > 700:
            content = content[:700] + "..."

        score_text = f" | score: {score:.2f}" if isinstance(score, (int, float)) else ""
        formatted.append(f"[{index}] {title}{score_text}\nURL: {url}\nExtrait: {content}")

    return "\n\n---\n\n".join(formatted)


@tool
def tavily_web_search(query: str) -> str:
    """
    Recherche sur le web des informations recentes, changeantes ou absentes
    des connaissances du modele et des autres outils disponibles.

    A utiliser pour l'actualite, les evenements recents, les prix, les
    versions de logiciels/API, les entreprises, les produits, les
    reglementations, ou toute information qui necessite une verification a
    jour.

    Ne pas utiliser pour les questions generales, les calculs simples, la
    reformulation, la traduction, ou les informations deja presentes dans le
    contexte.

    Args:
        query: Requete web concise et precise, idealement avec les mots-cles,
            le lieu, la date ou le nom exact de l'entite recherchee.

    Returns:
        Resultats web synthetises avec titres, URLs et extraits, ou un message
        d'erreur explicite si la recherche est impossible.
    """
    api_key = _get_tavily_api_key()
    if not api_key:
        return (
            "Erreur Tavily : impossible de recuperer la cle API (secret "
            f"Secrets Manager '{TAVILY_SECRET_NAME}'). Verifie que le secret "
            "existe et que le Lambda a la permission de le lire."
        )

    try:
        response = requests.post(
            TAVILY_SEARCH_URL,
            json={
                "api_key": api_key,
                "query": query,
                "search_depth": "advanced",
                "max_results": DEFAULT_MAX_RESULTS,
                "include_answer": True,
                "include_raw_content": False,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()

        answer = payload.get("answer")
        results = payload.get("results") or []

        if not answer and not results:
            return f"Aucun resultat web pertinent trouve pour : {query}"

        sections = []
        if answer:
            sections.append(f"Synthese Tavily:\n{answer}")
        if results:
            sections.append("Sources:\n" + _format_results(results))

        return "\n\n".join(sections)

    except requests.exceptions.RequestException as error:
        return f"Erreur reseau lors de la recherche web Tavily pour '{query}' : {error}"
    except ValueError as error:
        return f"Erreur Tavily : reponse JSON invalide pour '{query}' ({error})"

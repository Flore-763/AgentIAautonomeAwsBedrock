"""
tools/tavily_web_search.py
==========================

Outil de recherche web via Tavily.
"""

import os
from typing import Any, Dict, List

import requests
from langchain_core.tools import tool

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
REQUEST_TIMEOUT_SECONDS = 10
DEFAULT_MAX_RESULTS = 5


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
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return (
            "Erreur Tavily : variable d'environnement TAVILY_API_KEY absente. "
            "Configure cette cle pour activer la recherche web."
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

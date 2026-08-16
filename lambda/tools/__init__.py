"""
tools/__init__.py
====================

Point d'entrée unique pour récupérer la liste des outils disponibles pour
l'agent (utilisés par `graph/nodes.py` via `bind_tools`).

Pour ajouter un nouvel outil :
  1. Créer un fichier `tools/mon_outil.py`.
  2. Écrire une fonction décorée par `@tool` (langchain_core.tools.tool).
     Le nom de la fonction devient le nom de l'outil, et la docstring
     devient la description envoyée au LLM (c'est elle qui l'aide à
     décider QUAND utiliser l'outil) : soignez-la !
  3. L'importer et l'ajouter à la liste retournée par `get_tools()`
     ci-dessous.
"""

from typing import List

from langchain_core.tools import BaseTool

from tools.calculator import calculator
from tools.search import recherche_documentaire
from tools.tavily_web_search import tavily_web_search
from tools.weather import get_weather
from tools.document_search import document_search

## Claude ne doit pas avoir à inventer user_sub et session_id
def get_tools() -> List[BaseTool]:
    """
    Retourne les outils disponibles pour l'agent.

    Les informations sensibles au contexte utilisateur
    (user_sub, session_id) ne sont PAS demandées au LLM.
    Elles seront injectées côté backend lors de l'exécution
    de document_search.
    """

    return [
        get_weather,
        recherche_documentaire,
        tavily_web_search,
        calculator,
        document_search,
    ]
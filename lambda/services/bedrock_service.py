"""
services/bedrock_service.py
=============================

Point d'accès unique à AWS Bedrock :

  - `get_llm()`            : instance LangChain (`ChatBedrockConverse`) pour
                              le chat, sans outils bindés.
  - `get_llm_with_tools()` : la même instance, avec les outils "bindés" via
                              le function calling natif de l'API Bedrock
                              Converse.
  - `invoke_titan_embedding()` : appel bas niveau (boto3) au modèle
                              d'embedding Titan, utilisé pour la mémoire
                              sémantique (recherche dans OpenSearch).

Les anciennes fonctions `invoke_sonnet` / `invoke_haiku` / `invoke_nova`
(appels bruts `invoke_model`, sans LangChain) sont conservées en bas de
fichier pour compatibilité avec d'éventuels scripts existants, mais ne sont
PLUS utilisées par la boucle ReAct : celle-ci passe exclusivement par
`ChatBedrockConverse.bind_tools(...)`, qui gère nativement le format
d'appel d'outils attendu par Claude — bien plus fiable que l'ancien
parsing regex du texte "Action / Action Input".
"""

import json
import os
from typing import List

from botocore.exceptions import ClientError
from langchain_aws import ChatBedrockConverse
from langchain_core.tools import BaseTool

from config import bedrock_runtime

BEDROCK_REGION = os.getenv("BEDROCK_REGION", "us-west-2")
CHAT_MODEL_ID = os.getenv("CHAT_MODEL_ID", "global.anthropic.claude-sonnet-4-6")
EMBEDDING_MODEL_ID = os.getenv("EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0")

# Instance de base, créée une seule fois par conteneur Lambda (warm start).
_llm = ChatBedrockConverse(
    model=CHAT_MODEL_ID,
    region_name=BEDROCK_REGION,
    max_tokens=64000,
    temperature=0.7,
)


def get_llm() -> ChatBedrockConverse:
    """Retourne le modèle de chat Bedrock, sans outils bindés (ex : reformulation simple)."""
    return _llm


def get_llm_with_tools(tools: List[BaseTool]):
    """
    Retourne le modèle de chat avec les outils "bindés" via le function
    calling natif de l'API Bedrock Converse.

    `bind_tools(...)` retourne un NOUVEAU Runnable (il ne modifie pas
    `_llm` en place) : chaque outil est envoyé à Claude sous forme de
    schéma JSON, généré automatiquement par LangChain à partir de la
    signature Python et de la docstring de la fonction décorée `@tool`.
    En retour, Claude peut répondre avec un `AIMessage.tool_calls`
    structuré (nom de l'outil + arguments déjà typés), là où l'ancienne
    version devait extraire cette information d'un bloc de texte libre.
    """
    return _llm.bind_tools(tools)


def invoke_titan_embedding(input_text: str) -> List[float]:
    """Calcule l'embedding (vecteur) d'un texte via Amazon Titan (appel bas niveau, boto3)."""
    try:
        response = bedrock_runtime.invoke_model(
            modelId=EMBEDDING_MODEL_ID,
            body=json.dumps({"inputText": input_text}),
        )
        return json.loads(response["body"].read())["embedding"]
    except ClientError as error:
        print(" ERREUR BEDROCK (embedding) :", error.response)
        raise


# ------------------------------------------------------------------------
# Appels bas niveau conservés pour compatibilité (scripts ponctuels, tests
# manuels en dehors du graphe). La boucle ReAct principale n'utilise plus
# ces fonctions : elle passe par `get_llm_with_tools()` ci-dessus.
# ------------------------------------------------------------------------

def invoke_sonnet(prompt: str) -> str:
    """Appel direct (sans LangChain, sans outils) à Claude Sonnet via Bedrock."""
    response = bedrock_runtime.invoke_model(
        modelId="global.anthropic.claude-sonnet-4-6",
        body=json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 64000,
                "temperature": 0.7,
                "messages": [{"role": "user", "content": prompt}],
            }
        ),
        contentType="application/json",
        accept="application/json",
    )
    response_body = json.loads(response["body"].read())
    return response_body["content"][0]["text"]


def invoke_haiku(prompt: str) -> str:
    """Appel direct (sans LangChain) à Claude Haiku via Bedrock — utile pour des tâches rapides/peu coûteuses."""
    response = bedrock_runtime.invoke_model(
        modelId="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        body=json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 550,
                "temperature": 0.7,
                "messages": [{"role": "user", "content": prompt}],
            }
        ),
        contentType="application/json",
        accept="application/json",
    )
    response_body = json.loads(response["body"].read())
    return response_body["content"][0]["text"]

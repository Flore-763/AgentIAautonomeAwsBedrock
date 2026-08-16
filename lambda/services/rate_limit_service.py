"""
services/rate_limit_service.py
================================

Rate limiting "100 requêtes / minute par clé API", appliqué côté Lambda
(et non uniquement via le throttling natif d'API Gateway, qui se
configure en requêtes/seconde et ne permet pas d'exprimer nativement une
limite en req/min).

Principe : fenêtre fixe d'une minute.
  - On calcule une fenêtre `window = timestamp_unix // 60` (change toutes
    les 60s).
  - La clé DynamoDB est `{api_key_id}#{window}`.
  - Chaque requête fait un `UpdateItem` atomique (`ADD request_count :one`)
    -> pas de race condition même avec des requêtes concurrentes.
  - Un attribut `ttl` (now + 120s) permet à DynamoDB de purger
    automatiquement les anciennes fenêtres (pas de nettoyage manuel).
  - Si le compteur retourné dépasse la limite -> requête refusée (429).

Ce compteur ne remplace pas API Gateway (qui garde `api_key_required=True`
+ un UsagePlan) : API Gateway authentifie/valide la clé, ce module impose
la limite métier précise de 100/min.
"""

import os
import time
from typing import Tuple

import boto3
from botocore.exceptions import ClientError

RATE_LIMIT_TABLE_NAME = os.getenv("RATE_LIMIT_TABLE_NAME")
REQUESTS_PER_MINUTE = 100
WINDOW_SECONDS = 60
# Marge après la fin de la fenêtre avant expiration DynamoDB (TTL), pour
# laisser le temps aux requêtes en fin de fenêtre de s'écrire.
TTL_MARGIN_SECONDS = 60

_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table(RATE_LIMIT_TABLE_NAME) if RATE_LIMIT_TABLE_NAME else None


def _current_window() -> int:
    """Numéro de la fenêtre de 60s en cours (change chaque minute)."""
    return int(time.time() // WINDOW_SECONDS)


def check_and_increment(api_key_id: str) -> Tuple[bool, int]:
    """
    Incrémente le compteur de requêtes pour `api_key_id` sur la fenêtre en
    cours, et indique si la limite est dépassée.

    Returns:
        (allowed, current_count) :
          - allowed=True  -> la requête peut être traitée.
          - allowed=False -> la limite de 100/min est dépassée, la requête
            doit être rejetée (429 Too Many Requests).

    Fail-open volontaire : si la table de rate limiting n'est pas
    configurée (variable d'env absente, ex. environnement de test local)
    ou si DynamoDB est indisponible, on n'empêche pas l'agent de
    répondre — un problème d'infra de rate limiting ne doit pas rendre
    l'API indisponible.
    """
    if _table is None or not api_key_id:
        return True, 0

    window = _current_window()
    item_key = f"{api_key_id}#{window}"
    expires_at = int(time.time()) + WINDOW_SECONDS + TTL_MARGIN_SECONDS

    try:
        response = _table.update_item(
            Key={"rate_limit_key": item_key},
            UpdateExpression="ADD request_count :one SET #ttl = :ttl",
            ExpressionAttributeNames={"#ttl": "ttl"},  # ← AJOUTER CECI

            ExpressionAttributeValues={":one": 1, ":ttl": expires_at},
            ReturnValues="UPDATED_NEW",
        )
        current_count = int(response["Attributes"]["request_count"])
    except ClientError as error:
        print(f" Rate limiting indisponible (fail-open) : {error}")
        return True, 0

    return current_count <= REQUESTS_PER_MINUTE, current_count
"""
utils.py
==========

Fonctions utilitaires transverses (temps, sérialisation JSON/DynamoDB).
"""

import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal


def get_expiration_time() -> int:
    """Retourne un timestamp Unix correspondant à une expiration dans 30 jours (TTL DynamoDB)."""
    return int(time.time() + (30 * 24 * 60 * 60))


def decimal_default(obj):
    """
    Sérialiseur JSON pour les objets `Decimal` renvoyés par DynamoDB
    (boto3 convertit les nombres en `Decimal`, non sérialisables nativement
    par `json.dumps`). À passer en `default=` à `json.dumps`.
    """
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    raise TypeError(f"Type {type(obj)} non sérialisable en JSON.")


def to_decimal_list(vector):
    """
    Convertit une liste de floats (ex: embedding Titan) en liste de
    `Decimal`, seul type numérique accepté par `boto3.resource("dynamodb")`
    pour les attributs numériques.
    """
    return [Decimal(str(x)) for x in vector]


def generate_timestamp() -> str:
    """Retourne un timestamp ISO 8601 (UTC), utilisé comme clé de tri DynamoDB."""
    return datetime.now(timezone.utc).isoformat()


def generate_uuid() -> str:
    """Génère un identifiant unique (ex: nouveau session_id)."""
    return str(uuid.uuid4())

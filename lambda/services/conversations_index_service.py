"""
services/conversations_index_service.py
==========================================

Index des conversations PAR utilisateur, dans la table DynamoDB
`ConversationsIndexTable` (partition key = user_sub, sort key = session_id).

Remplace le fichier local `conversations_index.json` de l'ancienne UI, qui
ne fonctionnait pas en multi-user (fichier local = partagé/perdu entre
utilisateurs et entre instances).

Utilisé pour peupler le sidebar : "toutes les conversations de CET
utilisateur", jamais celles des autres, grâce au Query filtré par
user_sub (qui vient du token Cognito vérifié, pas d'une donnée que le
client pourrait falsifier).
"""

import os
import time

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

CONVERSATIONS_INDEX_TABLE_NAME = os.getenv("CONVERSATIONS_INDEX_TABLE_NAME")

_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table(CONVERSATIONS_INDEX_TABLE_NAME) if CONVERSATIONS_INDEX_TABLE_NAME else None


def register_conversation(user_sub: str, session_id: str, title: str) -> None:
    """
    Enregistre ou met à jour  une conversation dans l'index
    de l'utilisateur. Appelé après chaque tour de conversation réussi.

    `condition_expression` sur `attribute_not_exists(created_at)` évite
    d'écraser le titre (fixé au premier message) sur les tours suivants ;
    on met juste à jour `updated_at` dans ce cas via un update séparé.
    """
    # Si session_id contient déjà un préfixe, on l'extrait
    if "#" in session_id:
        session_id = session_id.split("#")[-1]
        print(f" register_conversation: extraction session_id={session_id}")

        
    if _table is None or not user_sub or not session_id:
        return

    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    try:
        # Tentative de création (1er message de la conversation)
        _table.put_item(
            Item={
                "user_sub": str(user_sub),
                "session_id": str(session_id),
                "title": title[:35],  # évite un titre à rallonge dans le sidebar
                "created_at": now_iso,
                "updated_at": now_iso,
            },
            ConditionExpression="attribute_not_exists(session_id)",
        )
    except ClientError as error:
        if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
            # La conversation existe déjà -> on rafraîchit juste updated_at,
            # sans toucher au titre déjà fixé au 1er message.
            _table.update_item(
                Key={"user_sub": user_sub, "session_id": session_id},
                UpdateExpression="SET updated_at = :now",
                ExpressionAttributeValues={":now": now_iso},
            )
        else:
            print(f"Erreur lors de l'indexation de la conversation : {error}")


def list_conversations(user_sub: str) -> list[dict]:
    """
    Retourne la liste des conversations de l'utilisateur, la plus
    récemment mise à jour en premier.
    """
    if _table is None or not user_sub:
        return []

    response = _table.query(
        KeyConditionExpression=Key("user_sub").eq(user_sub),
    )
    items = response.get("Items", [])
    items.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    return items
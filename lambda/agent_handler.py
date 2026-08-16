"""
agent_handler.py
==================

Point d'entrée AWS Lambda. Ce fichier ne contient QUE de la logique HTTP :
parsing de la requête API Gateway, mapping des erreurs Bedrock/DynamoDB
vers des codes HTTP, et formatage JSON de la réponse.

Toute la logique métier (mémoire, graphe LangGraph, outils) vit dans
`services/agent_service.py` : ce découpage permet de tester
`process_chat_message(...)` indépendamment d'API Gateway/Lambda (par
exemple depuis un simple script Python ou un test unitaire).
"""

import json
import traceback

from botocore.exceptions import (
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)

from services.agent_service import process_chat_message
from services.memory_service import memory_service
from utils import decimal_default


def http_response(status_code: int, body: dict) -> dict:
    """Construit une réponse API Gateway standard."""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=decimal_default),
    }


def error_response(status_code: int, error_message: str) -> dict:
    """Construit une réponse d'erreur API Gateway standard."""
    return http_response(status_code, {"error": error_message})


def parse_body(event: dict) -> dict:
    """Parse le corps JSON de la requête API Gateway."""
    try:
        return json.loads(event.get("body") or "{}")
    except json.JSONDecodeError as error:
        raise ValueError(f"Corps de requête JSON invalide : {error}") from error


def handle_chat(body: dict) -> dict:
    """Traite POST /agent/chat."""
    session_id = body.get("session_id")
    message = body.get("message")

    if not isinstance(message, str) or not message.strip():
        return error_response(400, "Vous n'avez pas saisi de message.")

    try:
        result = process_chat_message(
            message=message.strip(),
            session_id=session_id,
            max_iterations=body.get("max_iterations", 10),
        )
        return http_response(200, result)

    except ReadTimeoutError:
        return error_response(504, "Le modèle a mis trop de temps à répondre.")
    except ConnectTimeoutError:
        return error_response(504, "La connexion à Bedrock a expiré.")
    except EndpointConnectionError:
        return error_response(503, "Impossible de joindre Amazon Bedrock.")
    except ClientError as error:
        return handle_bedrock_error(error)
    except Exception as error:  # garde-fou générique : on ne veut jamais laisser Lambda planter sans réponse propre
        traceback.print_exc()
        return error_response(500, str(error))


def handle_history(path_parameters: dict) -> dict:
    """Traite GET /agent/sessions/{id}/history."""
    session_id = (path_parameters or {}).get("id")

    if not session_id:
        return error_response(400, "session_id manquant.")

    try:
        history = memory_service.get_conversation_history(session_id)
        return http_response(200, memory_service.format_history_response(session_id, history))
    except ClientError as error:
        print(f"❌ Erreur DynamoDB : {error}")
        return error_response(500, "Erreur lors de la récupération de l'historique.")


def handle_bedrock_error(error: ClientError) -> dict:
    """Traduit une erreur Bedrock (ClientError) en réponse HTTP adaptée."""
    error_code = error.response["Error"]["Code"]
    error_mapping = {
        "ThrottlingException": (429, "Trop de requêtes. Réessayez dans quelques secondes."),
        "AccessDeniedException": (403, "Accès refusé à Amazon Bedrock."),
        "ValidationException": (400, "Requête invalide envoyée à Bedrock."),
        "ResourceNotFoundException": (404, "Le modèle Bedrock demandé est introuvable."),
    }
    status_code, message = error_mapping.get(error_code, (500, str(error)))
    return error_response(status_code, message)


def lambda_handler(event, context):
    """Point d'entrée principal du Lambda (routage HTTP minimal)."""
    print("Lambda démarré...")

    http_method = event.get("httpMethod")
    path = event.get("path")
    print(f"Méthode : {http_method}, Path : {path}")

    if http_method == "POST" and path == "/agent/chat":
        try:
            return handle_chat(parse_body(event))
        except ValueError as error:
            return error_response(400, str(error))

    if http_method == "GET":
        return handle_history(event.get("pathParameters") or {})

    return error_response(404, "Route inconnue.")

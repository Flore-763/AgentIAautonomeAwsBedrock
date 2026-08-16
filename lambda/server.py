"""
server.py
=========
Serveur HTTP minimaliste pour AWS Lambda Web Adapter.
Remplace web_app.py (FastAPI) par un serveur HTTP natif Python.
Gère le streaming SSE correctement.
"""

import json
import uuid
import cgi
import io
import os
import boto3
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from decimal import Decimal
import traceback
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs

from langchain_core.messages import HumanMessage, AIMessageChunk
from graph.workflow import get_graph
from services.api_key_service import is_valid_api_key
from services.auth_service import verify_id_token
from services.bedrock_service import invoke_titan_embedding
from services.conversations_index_service import list_conversations, register_conversation
from services.memory_service import get_chat_history, memory_service
from services.prompt_service import format_memories_block
from services.document_service import extract_document
from services.document_index_service import index_document,list_session_documents
from services.rate_limit_service import check_and_increment
from vector_store import vector_store
import os
# Constantes
DEFAULT_MAX_ITERATIONS = 10
HARD_MAX_ITERATIONS = 20
DEFAULT_WINDOW_SIZE = 5


S3_BUCKET_NAME = os.environ.get(
    "KNOWLEDGE_BUCKET_NAME"
)

s3_client = boto3.client("s3")

def _decimal_to_native(obj):
    if isinstance(obj, list):
        return [_decimal_to_native(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _decimal_to_native(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    return obj

def _extract_text(content) -> str:
    """Normalise le contenu du modèle en string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text = ""
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text += block.get("text", "")
            elif isinstance(block, str):
                text += block
        return text
    return ""

def sse_event(event_type: str, data) -> str:
    """Formate une ligne SSE valide."""
    payload = json.dumps({"type": event_type, "data": data}, ensure_ascii=False)
    return f"data: {payload}\n\n"

def sse_error(error_message: str) -> str:
    """Formate une erreur SSE."""
    return sse_event("error", {"message": error_message})

def process_chat_stream(message: str, user_sub:str,session_id: str = None, max_iterations: int = DEFAULT_MAX_ITERATIONS, recent_attachments: list | None = None):
    """
    Générateur qui produit des événements SSE pour le streaming.

    `user_sub` (identifiant Cognito stable de l'utilisateur, déjà vérifié
    par `_authenticate_and_throttle`) sert à NAMESPACER le session_id
    utilisé pour toute la mémoire (DynamoDB + vecteurs OpenSearch) :
    la clé de stockage réelle est `{user_sub}#{session_id}`.

    Le `session_id` "brut" (sans le préfixe) est celui envoyé au client
    et réutilisé par lui sur les tours suivants — le client ne voit
    jamais le namespacing. C'est ce qui garantit l'isolation des données :
    même si un utilisateur B devine/récupère le session_id brut d'un
    utilisateur A, sa propre requête est namespacée avec SON user_sub à
    lui, donc elle pointe vers une clé de stockage totalement différente
    (et donc vide) — il ne peut physiquement pas lire l'historique de A.
    """
    # session_id = session_id or str(uuid.uuid4())
    # storage_session_id= f"{user_sub}#{session_id}"
    if session_id and "#" in session_id:
        # Extraire la partie après le dernier #
        raw_session_id = session_id.split("#")[-1]
        print(f"🔍 Extraction du session_id brut: {raw_session_id} (depuis {session_id})")
        session_id = raw_session_id
    
    session_id = session_id or str(uuid.uuid4())
    storage_session_id = f"{user_sub}#{session_id}"
    
    print(f"🔍 DEBUG process_chat_stream:")
    print(f"  - user_sub: {user_sub}")
    print(f"  - session_id (brut): {session_id}")
    print(f"  - storage_session_id: {storage_session_id}")


    max_iterations = min(max_iterations, HARD_MAX_ITERATIONS)
    try:
        # 1. Mémoire court terme
        chat_history = get_chat_history(storage_session_id, window_size=DEFAULT_WINDOW_SIZE)
        
        # 2. Mémoire long terme
        message_embedding = invoke_titan_embedding(message)
        semantic_memories = vector_store.semantic_search(
            embedding=message_embedding,
            session_id=storage_session_id,
            before_timestamp=chat_history.oldest_timestamp,
            k=3,
        )
        context = format_memories_block(semantic_memories)

        uploaded_files = list_session_documents(user_sub, session_id)
        if uploaded_files:
            context += (
                "\n\n===== Documents disponibles pour cette session =====\n"
                f"L'utilisateur a chargé les fichiers suivants : {', '.join(uploaded_files)}.\n"
                "Si sa demande porte sur le contenu d'un de ces fichiers "
                "(résumé, analyse, extraction, comparaison...), utilise "
                "l'outil `document_search` pour aller chercher les passages "
                "pertinents avant de répondre — ne dis jamais qu'aucun fichier "
                "n'a été fourni."
            )

        # Fichiers joints à CE tour précis, tels que rapportés par le
        # frontend juste après leur indexation. On s'appuie dessus en
        # PLUS de `list_session_documents` (et pas à sa place) car ce
        # dernier interroge OpenSearch, dont la cohérence en lecture
        # après écriture n'est pas garantie immédiate — en particulier
        # sur un index nouvellement créé, le délai peut largement
        # dépasser les quelques secondes couvertes par les tentatives
        # de `document_search`. Cette info-ci, elle, vient directement
        # du frontend et est donc fiable à 100% pour ce tour.
        recent_indexed = [
            attachment.get("filename")
            for attachment in (recent_attachments or [])
            if attachment.get("status") == "indexed" and attachment.get("filename")
        ]
        if recent_indexed:
            context += (
                "\n\n===== Fichier(s) joint(s) à ce message =====\n"
                f"L'utilisateur vient de joindre à l'instant : {', '.join(recent_indexed)}.\n"
                "Utilise `document_search` pour analyser son/leur contenu. "
                "Cet outil patiente déjà plusieurs dizaines de secondes en "
                "interne pour laisser le temps à l'indexation de se "
                "terminer : dans l'immense majorité des cas, il finira par "
                "trouver le contenu SANS que tu aies besoin de redemander "
                "quoi que ce soit à l'utilisateur. NE DIS JAMAIS qu'aucun "
                "fichier n'a été fourni. Si, et seulement si, l'outil "
                "répond explicitement que le document est encore en cours "
                "d'indexation même après ce délai, alors — et alors "
                "seulement — informe l'utilisateur qu'un nouvel essai sera "
                "peut-être nécessaire dans un instant."
            )

        
        # 3. Exécution du graphe LangGraph
        graph = get_graph()
        initial_state = {
            "user_sub":user_sub,
            "session_id": storage_session_id,
            "raw_session_id":session_id,
            "messages": chat_history.messages + [HumanMessage(content=message)],
            "context": context,
            "iterations": 0,
            "max_iterations": max_iterations,
            "tool_call_history": [],
            "final_answer": None,
            "error": None,
            "has_recent_upload": bool(recent_indexed),
            "recent_upload_filenames": recent_indexed,
        }
        config = {"configurable": {"thread_id": storage_session_id}}
    except Exception as e:
        print(f"Erreur pendant la préparation du contexte: {e}")
        traceback.print_exc()
        yield sse_error(f"Erreur de préparation: {e}")
        return   

    
    # Événement initial : session_id BRUT (sans le préfixe user_sub)
    yield sse_event("session", {"session_id": session_id})
    
    # current_segment = ""
    full_answer = ""
  
    
    try:
        for mode, chunk in graph.stream(
            initial_state, 
            config=config,
            stream_mode=["messages", "updates"]
        ):
            if mode == "messages":
                token_chunk, _meta = chunk
                if not isinstance(token_chunk, AIMessageChunk):
                    continue
                text = _extract_text(getattr(token_chunk, "content", None))
                if text:
                    full_answer += text
                    yield sse_event("token", text)
                    
            elif mode == "updates":
                for node_name,node_data in chunk.items():
                    yield sse_event("step", {"node": node_name})
                    if node_name == "call_model":
                        print(f"🔍 Node 'call_model' atteint, full_answer actuel: {len(full_answer)} chars")
                        # full_answer = current_segment
                        # current_segment = ""
                        if "final_answer" in node_data:
                            full_answer=node_data["final_answer"]
    
    except Exception as e:
        print(f"Erreur dans graph.stream: {e}")
        yield sse_error(str(e))
        return

    print(f"✅ SAUVEGARDE: full_answer = {len(full_answer)} caractères")
    # Si final_answer n'a pas été récupéré, utiliser le dernier message
    # if not final_answer:
    #     # Récupérer le state final
    #     final_state = graph.get_state(config)
    #     if final_state and final_state.values:
    #         final_answer = final_state.values.get("final_answer", "")
    
    # Sauvegarde finale
    # full_answer = full_answer or current_segment
    if full_answer:
        try:
            response_embedding = invoke_titan_embedding(full_answer)
            memory_service.batch_save_turn(
                session_id=storage_session_id,
                user_message=message,
                assistant_response=full_answer,
                user_embedding=None,
                response_embedding=None,
            )
            print(f" batch_save_turn OK pour storage_session_id={storage_session_id}")
            #Index pour le sidebar : titre = début du 1er message de l'utilisateur
            register_conversation(user_sub=user_sub,session_id=session_id,title=message)
            print(f" register_conversation OK pour user_sub={user_sub}, session_id={session_id}")

        except Exception as e:
            print(f"Erreur lors de la sauvegarde: {e}")
    else:
        print("Pas de sauvegarde: full_answer est vide !")

    yield sse_event("done", {"final_answer": full_answer})

# --- Handlers HTTP ---

class AgentHandler(BaseHTTPRequestHandler):
    """Handler HTTP pour le serveur minimaliste."""
    
    def _send_json_response(self, status_code: int, data: dict):
        """Envoie une réponse JSON standard."""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data, default=_decimal_to_native).encode('utf-8'))
    
    def _send_error_response(self, status_code: int, error_message: str):
        """Envoie une réponse d'erreur JSON."""
        self._send_json_response(status_code, {"error": error_message})

    def _authenticate_and_throttle(self) -> bool:
        """
        Applique, dans l'ordre, les DEUX couches de sécurité décrites dans
        le cahier des charges + l'ajout multi-user :

        1. `x-api-key` : vérifie que l'appelant est bien notre app front
           (une seule clé, partagée par tous les utilisateurs légitimes,
           jamais exposée au navigateur — cf. discussion précédente).
        2. `Authorization: Bearer <id_token>` : vérifie l'IDENTITÉ de
           l'utilisateur via son token Cognito, et en extrait `user_sub`
           (stocké sur `self.user_sub` pour le reste du traitement).

        Le rate limit de 100 req/min est ensuite appliqué PAR UTILISATEUR
        (sur `user_sub`, pas sur l'api_key partagée) : chaque utilisateur a
        son propre quota, un user actif ne peut pas affamer les autres.

        Envoie directement la réponse d'erreur (401/429) si la requête
        doit être rejetée, et retourne False dans ce cas — l'appelant
        (`do_GET`/`do_POST`) doit alors `return` immédiatement sans rien
        écrire d'autre sur la connexion.
        """
        api_key = self.headers.get("x-api-key")

        if not is_valid_api_key(api_key):
            self._send_error_response(401, "Clé API manquante ou invalide (header x-api-key requis).")
            return False

        auth_header= self.headers.get("Authorization", "")
        token=auth_header.removeprefix("Bearer ").strip() if auth_header else ""
        payload= verify_id_token(token)
        if payload is None:
            self._send_error_response(401,"Session expirée ou invalide. Merci de vous reconnecter.")
            return False

        self.user_sub=payload["sub"]

        allowed, current_count = check_and_increment(self.user_sub)
        if not allowed:
            print(f" Rate limit dépassé pour l'utilisateur{self.user_sub} ({current_count}/100 req/min).")
            self._send_error_response(429, "Limite de 100 requêtes par minute dépassée. Réessayez dans quelques instants.")
            return False

        return True

    def do_GET(self):
        """Gère les requêtes GET."""
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/health":
            # Utilisé par AWS Lambda Web Adapter en interne pour le
            # readiness check (AWS_LWA_READINESS_CHECK_PATH) : jamais
            # exposé publiquement via la Function URL/API Gateway, donc
            # pas d'authentification requise ici.
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')
            return

        if not self._authenticate_and_throttle():
            return

        #GET/agent/users/me/conversations -> sidebar : uniquement les conversations de l'tilisateur courant
        #(self.user_sub vient du token vérifié, jamais d'un paramètre fourni par le client).
        if path == "/agent/users/me/conversations":
            try:
                conversations = list_conversations(self.user_sub)
                self._send_json_response(200,{"conversations":conversations})
            except Exception as e:
                self._send_error_response(500,str(e))
            return



        # GET /agent/sessions/{id}/history
        if path.startswith("/agent/sessions/"):
            parts = path.split("/")
            if len(parts) >= 5 and parts[4] == "history":
                session_id = parts[3]
                # Namespacing avec l'utilisateur courant : si ce session_id
                # appartient à un autre utilisateur, la clé de stockage
                # réelle ne correspond à rien -> historique vide renvoyé,
                # jamais celui d'un autre utilisateur.
                storage_session_id= f"{self.user_sub}#{session_id}"
                try:
                    history = memory_service.get_conversation_history(storage_session_id)
                    data = memory_service.format_history_response(session_id, history)
                    self._send_json_response(200, data)
                except Exception as e:
                    self._send_error_response(500, str(e))
                return
        
        self._send_error_response(404, "Not Found")
    
    def do_POST(self):
        """Gère les requêtes POST."""
        parsed = urlparse(self.path)
        path = parsed.path

        if not self._authenticate_and_throttle():
            return

        # =========================================================
        # UPLOAD DOCUMENTS
        # =========================================================

        if path == "/agent/documents":

            self._handle_document_upload()

            return

        # =========================================================
        # CHAT
        # =========================================================

        # Lecture du body
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        
        try:
            payload = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError:
            self._send_error_response(400, "Invalid JSON body")
            return
        
        # POST /agent/chat/stream
        if path == "/agent/chat/stream":
            self._handle_stream_chat(payload)
            return
        
        # POST /agent/chat (non-streaming)
        # if path == "/agent/chat":
        #     self._handle_chat(payload)
        #     return
        
        self._send_error_response(404, "Not Found")
    
    def _handle_chat(self, payload: dict):
        """Traite /agent/chat (non-streaming)."""
        try:
            message = payload.get("message", "").strip()
            if not message:
                self._send_error_response(400, "Message is required")
                return
            
            session_id = payload.get("session_id")
            max_iterations = payload.get("max_iterations", DEFAULT_MAX_ITERATIONS)
            
            # Cette fonction existe déjà dans agent_service.py
            from services.agent_service import process_chat_message
            result = process_chat_message(
                message=message,
                session_id=session_id,
                max_iterations=max_iterations,
            )
            
            self._send_json_response(200, result)
            
        except Exception as e:
            self._send_error_response(500, str(e))
    
    def _handle_stream_chat(self, payload: dict):
        """Traite /agent/chat/stream avec SSE."""
        try:
            message = payload.get("message", "").strip()
            if not message:
                self._send_error_response(400, "Message is required")
                return
            
            session_id = payload.get("session_id")
            max_iterations = payload.get("max_iterations", DEFAULT_MAX_ITERATIONS)
            recent_attachments = payload.get("recent_attachments") or []

            # Envoi des headers SSE
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('X-Accel-Buffering', 'no')  # Désactive le buffering nginx
            self.end_headers()
            
            # Streaming des événements
            for event in process_chat_stream(
                message=message,
                user_sub=self.user_sub,
                session_id=session_id,
                max_iterations=max_iterations,
                recent_attachments=recent_attachments,
            ):
                try:
                    self.wfile.write(event.encode('utf-8'))
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    # Client déconnecté, on arrête
                    print("Client disconnected")
                    break
                    
        except Exception as e:
            print(f"Erreur dans _handle_stream_chat: {e}")
            traceback.print_exc()
            try:
                self.wfile.write(sse_error(str(e)).encode('utf-8'))
                self.wfile.flush()
            except:
                pass


    def _handle_document_upload(self):
        """
        Reçoit un ou plusieurs fichiers via multipart/form-data,
        les stocke dans S3, extrait leur contenu et les indexe
        dans OpenSearch.
        """

        content_type = self.headers.get(
            "Content-Type",
            "",
        )

        if not content_type.startswith(
            "multipart/form-data"
        ):
            self._send_error_response(
                400,
                "Content-Type doit être multipart/form-data",
            )
            return

        try:

            content_length = int(
                self.headers.get(
                    "Content-Length",
                    0,
                )
            )

            if content_length <= 0:
                self._send_error_response(
                    400,
                    "Aucun fichier reçu.",
                )
                return

            body = self.rfile.read(
                content_length
            )

            environ = {
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": content_type,
                "CONTENT_LENGTH": str(content_length),
            }

            form = cgi.FieldStorage(
                fp=io.BytesIO(body),
                environ=environ,
                keep_blank_values=True,
            )

            session_id = (
                form.getfirst("session_id")
            )

            if not session_id:
                self._send_error_response(
                    400,
                    "session_id est obligatoire.",
                )
                return

            fields = form["files"] \
                if "files" in form \
                else []

            if not isinstance(fields, list):
                fields = [fields]

            uploaded_documents = []

            for field in fields:

                if not getattr(
                    field,
                    "filename",
                    None,
                ):
                    continue

                filename = os.path.basename(
                    field.filename
                )

                file_bytes = field.file.read()

                if not file_bytes:
                    continue

                document_id = str(
                    uuid.uuid4()
                )

                extension = os.path.splitext(
                    filename
                )[1].lower()

                allowed_extensions = {
                    ".pdf",
                    ".docx",
                    ".xlsx",
                    ".csv",
                    ".txt",
                    ".py",
                    ".md",
                    ".json",
                }

                if extension not in allowed_extensions:

                    uploaded_documents.append({
                        "filename": filename,
                        "status": "rejected",
                        "error": (
                            f"Format non supporté : "
                            f"{extension}"
                        ),
                    })

                    continue

                s3_key = (
                    f"documents/"
                    f"{self.user_sub}/"
                    f"{session_id}/"
                    f"{document_id}/"
                    f"{filename}"
                )

                # 1. Stockage S3
                s3_client.put_object(
                    Bucket=S3_BUCKET_NAME,
                    Key=s3_key,
                    Body=file_bytes,
                    ContentType=(
                        field.type
                        or "application/octet-stream"
                    ),
                    Metadata={
                        "user_sub": self.user_sub,
                        "session_id": session_id,
                        "document_id": document_id,
                    },
                )

                # 2. Extraction
                extracted_text = extract_document(
                    filename,
                    file_bytes,
                )

                # 3. Indexation vectorielle
                index_result = index_document(
                    user_sub=self.user_sub,
                    session_id=session_id,
                    document_id=document_id,
                    filename=filename,
                    content=extracted_text,
                )

                uploaded_documents.append({
                    "filename": filename,
                    "document_id": document_id,
                    "status": "indexed",
                    "s3_key": s3_key,
                    "chunks": index_result["chunks"],
                })

            if not uploaded_documents:

                self._send_error_response(
                    400,
                    "Aucun fichier valide reçu.",
                )

                return

            self._send_json_response(
                200,
                {
                    "session_id": session_id,
                    "documents": uploaded_documents,
                },
            )

        except Exception as error:

            print(
                f"Document upload error: {error}"
            )

            self._send_error_response(
                500,
                f"Erreur pendant l'upload : {error}",
        )
    
    
    def log_message(self, format, *args):
        """Réduit le bruit des logs HTTP."""
        pass

def run_server():
    """Lance le serveur HTTP."""
    port = int(os.environ.get('PORT', 8000))
    server = HTTPServer(('0.0.0.0', port), AgentHandler)
    print(f"Server running on port {port}")
    server.serve_forever()

# Point d'entrée pour le conteneur
if __name__ == "__main__":
    run_server()
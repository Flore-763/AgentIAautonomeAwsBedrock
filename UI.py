import json
import time
import uuid
import html

import boto3
import extra_streamlit_components as stx
import requests
import streamlit as st

# =====================================================================
# LOGO SMARTOVATE (encodé en base64 pour un déploiement mono-fichier,
# sans dépendance à un dossier "assets" séparé sur le serveur Streamlit)
# =====================================================================
SMARTOVATE_LOGO_B64 = (
    "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"
    "88888888888888888888888888888888888888l/888887eW+8888888888888888888888888888888888888882g888888trFG+8888888888888888888"
    "888888888888888888IS88888888Mi+8888888888888888888888888888888888888CK88888888888888888wG08888888888888888w888888888884Q"
    "88w0888888888mE+8GcGY8848888800844w4K088w88808808404CU88w888888tJi6Gwss+6KGia0kieC8WOkCCcqmqwi0oGMWCO8CK8yCCY8888858saO6"
    "Q+q4W8iUoYmS8Gc8C8sGc8W4S8KsE4K8CUs2c+G888884MI08KW+qoW8CUK2aC8W88C88S8sGs6q8o2sK8CU8GMIU88889FFcKSG8+qoW8CUqSGC8W88qiMi"
    "yG08KCc4Cmq8OCUmCy28888JX88csM88csM8s8sc8c8c88sc88s8888c88csscssc8c8888GDPv84c8SGeK+qaiUEuWE0oUcCs0q4KsOsoUA8+sUegy28888"
    "8nG988o4ogYwcgo4wIoI0w8oI8gYYgEU8o80coUwcUY0QA888888888888888888888888888888888888888888+78888897X9888888888888888888888"
    "888888888888888888IU28883xyKd888888888888888888888888888888888888888ofo892pPM888888888888888888888888888888888888888888M"
    "oC01X988888888888888888888888888888888888888888888fih/8APPPPPPPPPPPP/8QAKREBAAIABQIGAgMBAAAAAAAAAQARITFBUFFx0RAgMIHh8GHB"
    "YJGhsf/aAAgBAwEBPxDYQuX5w+IZolpajFNO3ZRuNIS7QqILLJXG5pu/352u5lBbFd+NsalV+o8DC3U7yoPvo7TYXBb5qboHaWp9tSJjsYlsY47RHRTs9j6y"
    "rzgz0kNr+7udoWRYwXDTzrGWYbNYuvaVe/0XbWHGksoR4iay2ax9e0q9xuLst1/RHq6nrY9lW455kzUleO4v2cJaO4s/mSgXcC4WsERpBXlw297DXJy+ZWsa"
    "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"
)
SMARTOVATE_LOGO_DATA_URI = f"data:image/jpeg;base64,{SMARTOVATE_LOGO_B64}"


# =====================================================================
# CONFIGURATION
# =====================================================================

API_BASE_URL = "https://oan2blqffnfhrik5chvvnggqvm0lanep.lambda-url.us-west-2.on.aws"
# API_BASE_URL = "http://localhost:8000"  # ← En local
STREAM_URL = f"{API_BASE_URL}/agent/chat/stream"
LOAD_URL=f"{API_BASE_URL}/agent/documents"
HISTORY_URL = f"{API_BASE_URL}/agent/sessions/{{session_id}}/history"
CONVERSATIONS_URL = f"{API_BASE_URL}/agent/users/me/conversations"

API_KEY = st.secrets.get("api", {}).get("key", "")

# Config Cognito : PAS des secrets à proprement parler (ce sont des
# identifiants publics, comme un client_id OAuth), mais on les garde dans
# secrets.toml par commodité pour ne pas les coder en dur dans le repo.
COGNITO_REGION = st.secrets.get("cognito", {}).get("region", "us-west-2")
COGNITO_CLIENT_ID = st.secrets.get("cognito", {}).get("client_id", "")

REFRESH_COOKIE_NAME = "agent_refresh_token"
REFRESH_COOKIE_MAX_AGE = 30 * 24 * 3600  # 30 jours, doit matcher refresh_token_validity côté CDK

cognito_client = boto3.client("cognito-idp", region_name=COGNITO_REGION)


# =====================================================================
# GESTION DU COOKIE (reconnexion silencieuse à la réouverture de la page)
# =====================================================================
# extra_streamlit_components.CookieManager est un composant JS embarqué :
# au tout premier rendu de la page, le cookie n'est pas encore remonté au
# serveur Streamlit (l'échange navigateur <-> composant prend un cycle de
# rendu). D'où le petit motif d'attente ci-dessous : on ne décide "pas de
# cookie" qu'après avoir laissé une chance au composant de répondre.

def get_cookie_manager() -> stx.CookieManager:
    if "cookie_manager" not in st.session_state:
        st.session_state.cookie_manager = stx.CookieManager(key="agent_cookie_manager")
    return st.session_state.cookie_manager


# =====================================================================
# APPELS COGNITO
# =====================================================================

def cognito_sign_up(email: str, password: str) -> tuple[bool, str]:
    """Crée le compte. Cognito envoie un code de confirmation par email."""
    try:
        cognito_client.sign_up(
            ClientId=COGNITO_CLIENT_ID,
            Username=email,
            Password=password,
            UserAttributes=[{"Name": "email", "Value": email}],
        )
        return True, "Compte créé. Vérifiez votre boîte mail pour le code de confirmation."
    except cognito_client.exceptions.UsernameExistsException:
        return False, "Un compte existe déjà avec cet email."
    except cognito_client.exceptions.InvalidPasswordException as e:
        return False, f"Mot de passe invalide : {e.response['Error']['Message']}"
    except Exception as e:
        return False, f"Erreur lors de l'inscription : {e}"


def cognito_confirm_sign_up(email: str, code: str) -> tuple[bool, str]:
    """Valide le code reçu par email pour activer le compte."""
    try:
        cognito_client.confirm_sign_up(
            ClientId=COGNITO_CLIENT_ID,
            Username=email,
            ConfirmationCode=code,
        )
        return True, "Compte confirmé ! Vous pouvez maintenant vous connecter."
    except cognito_client.exceptions.CodeMismatchException:
        return False, "Code de confirmation incorrect."
    except cognito_client.exceptions.ExpiredCodeException:
        return False, "Code expiré, redemandez-en un."
    except Exception as e:
        return False, f"Erreur lors de la confirmation : {e}"


def cognito_resend_confirmation_code(email: str) -> tuple[bool, str]:
    """
    Redemande l'envoi du code de confirmation. Utile si l'email initial
    n'est jamais arrivé (fréquent avec l'expéditeur par défaut de Cognito,
    souvent classé en spam) ou si le code a expiré.
    """
    try:
        cognito_client.resend_confirmation_code(
            ClientId=COGNITO_CLIENT_ID,
            Username=email,
        )
        return True, "Nouveau code envoyé. Pensez à vérifier vos spams."
    except cognito_client.exceptions.UserNotFoundException:
        return False, "Aucun compte trouvé avec cet email."
    except cognito_client.exceptions.InvalidParameterException:
        return False, "Ce compte est déjà confirmé."
    except Exception as e:
        return False, f"Erreur lors du renvoi du code : {e}"


def cognito_login(email: str, password: str) -> tuple[bool, str]:
    """
    Authentifie l'utilisateur et, si succès, stocke les tokens :
      - id_token/access_token en mémoire (st.session_state) : courte durée
        de vie (~1h), utilisés à chaque requête vers le Lambda.
      - refresh_token dans un COOKIE navigateur (~30 jours) : c'est LUI qui
        permet de rester connecté après fermeture/réouverture de la page,
        comme une vraie web app.
    """
    try:
        response = cognito_client.initiate_auth(
            ClientId=COGNITO_CLIENT_ID,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": email, "PASSWORD": password},
        )
        result = response["AuthenticationResult"]
        _apply_authentication_result(result, email)
        return True, "Connecté."
    except cognito_client.exceptions.UserNotConfirmedException:
        return False, "Compte non confirmé. Vérifiez votre email pour le code de confirmation."
    except cognito_client.exceptions.NotAuthorizedException:
        return False, "Email ou mot de passe incorrect."
    except cognito_client.exceptions.UserNotFoundException:
        return False, "Email ou mot de passe incorrect."
    except Exception as e:
        return False, f"Erreur lors de la connexion : {e}"


def try_restore_session_from_cookie() -> bool:
    """
    Appelé au chargement de la page. Si un refresh_token valide est
    présent dans le cookie, on échange ce refresh_token contre un nouveau
    id_token SANS redemander email/mot de passe — c'est la "reconnexion
    silencieuse" qui fait que l'utilisateur reste connecté même après
    avoir fermé puis rouvert la page.
    """
    cookie_manager = get_cookie_manager()
    try:
        refresh_token = cookie_manager.get(REFRESH_COOKIE_NAME)
    except Exception:
        return False
    if not refresh_token:
        return False

    try:
        response = cognito_client.initiate_auth(
            ClientId=COGNITO_CLIENT_ID,
            AuthFlow="REFRESH_TOKEN_AUTH",
            AuthParameters={"REFRESH_TOKEN": refresh_token},
        )
        result = response["AuthenticationResult"]
        # REFRESH_TOKEN_AUTH ne renvoie pas de nouveau refresh_token
        # (Cognito garde le même tant qu'il n'a pas expiré) : on le
        # réinjecte manuellement pour la suite.
        result["RefreshToken"] = refresh_token
        _apply_authentication_result(result, email=None)
        return True
    except cognito_client.exceptions.NotAuthorizedException:
        # Refresh token expiré/révoqué : on nettoie le cookie et on
        # retombe sur l'écran de login.
        cookie_manager.delete(REFRESH_COOKIE_NAME)
        return False
    except Exception:
        return False


def _apply_authentication_result(result: dict, email: str | None) -> None:
    """Centralise le stockage des tokens (mémoire + cookie)."""
    st.session_state.id_token = result["IdToken"]
    st.session_state.access_token = result["AccessToken"]
    st.session_state.logged_in = True
    if email:
        st.session_state.user_email = email

    if "RefreshToken" in result:
        # Écriture du cookie non-bloquante : le composant JS du
        # CookieManager peut ne pas être encore "monté" au moment précis
        # de la connexion (quirk connu de cette librairie sur son tout
        # premier appel avec une nouvelle clé). Si ça échoue, la connexion
        # reste valide pour CETTE session ; seule la reconnexion
        # automatique après fermeture de la page pourrait ne pas
        # fonctionner ce coup-ci — on prévient l'utilisateur sans le
        # bloquer.
        try:
            get_cookie_manager().set(
                REFRESH_COOKIE_NAME,
                result["RefreshToken"],
                max_age=REFRESH_COOKIE_MAX_AGE,
                key="set_refresh_cookie",
            )
        except Exception:
            st.session_state.cookie_write_pending = result["RefreshToken"]


def logout() -> None:
    try:
        get_cookie_manager().delete(REFRESH_COOKIE_NAME, key="delete_refresh_cookie")
    except Exception:
        pass
    for key in ("id_token", "access_token", "logged_in", "user_email", "session_id", "messages"):
        st.session_state.pop(key, None)


def refresh_access_token() -> bool:
    """
    Rafraîchit silencieusement l'id_token en cours de session (ex: après
    une réponse 401 en pleine conversation, sans forcer un re-login),
    tant que le refresh_token en cookie est encore valide.
    """
    return try_restore_session_from_cookie()


# =====================================================================
# HTTP HELPERS VERS LE LAMBDA
# =====================================================================

def get_headers() -> dict:
    if not API_KEY:
        st.error("🔑 Clé API applicative manquante (configuration serveur).")
        st.stop()
    return {
        "x-api-key": API_KEY,
        "Authorization": f"Bearer {st.session_state.id_token}",
        "Content-Type": "application/json",
    }


def new_conversation():
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.messages = []



def upload_documents(files):
    """
    Upload plusieurs fichiers vers le backend.
    """

    if not files:
        return []

    headers = get_headers()

    # Important :
    # requests doit construire lui-même le Content-Type
    # multipart/form-data avec sa boundary.
    headers.pop(
        "Content-Type",
        None,
    )

    multipart_files = []

    for uploaded_file in files:

        multipart_files.append(
            (
                "files",
                (
                    uploaded_file.name,
                    uploaded_file.getvalue(),
                    uploaded_file.type
                    or "application/octet-stream",
                ),
            )
        )

    data = {
        "session_id":
            st.session_state.session_id,
    }

    try:

        response = requests.post(
            LOAD_URL,
            headers=headers,
            data=data,
            files=multipart_files,
            timeout=120,
        )

        if response.status_code == 401:

            if refresh_access_token():

                return upload_documents(
                    files
                )

            st.error(
                "🔑 Votre session a expiré."
            )

            logout()
            st.rerun()

            return []

        if response.status_code != 200:

            st.error(
                f"❌ Erreur upload "
                f"{response.status_code}: "
                f"{response.text}"
            )

            return []

        result = response.json()

        return result.get(
            "documents",
            [],
        )

    except requests.RequestException as error:

        st.error(
            f"Erreur pendant l'upload : {error}"
        )

        return []

    
def stream_message(message: str, attachments: list[dict] | None = None):
    """Envoie un message et streame la réponse (SSE)."""
    payload = {
        "session_id": st.session_state.session_id,
        "message": message,
        "max_iterations": 10,
        # Fichiers joints à CE tour (nom + statut d'indexation). Sert au
        # backend à savoir de façon fiable qu'un fichier vient d'être
        # chargé, sans dépendre d'OpenSearch (qui peut mettre bien plus
        # de temps que prévu à rendre un document tout juste indexé
        # cherchable, en particulier sur un index nouvellement créé) —
        # voir services/document_index_service.py.
        "recent_attachments": [
            {
                "filename": attachment.get("filename"),
                "status": attachment.get("status"),
            }
            for attachment in (attachments or [])
        ],
    }

    try:
        with requests.post(STREAM_URL, json=payload, headers=get_headers(), stream=True, timeout=90) as response:
            if response.status_code == 401:
                # L'id_token a probablement expiré (durée de vie ~1h) :
                # on tente un rafraîchissement silencieux via le cookie
                # AVANT de renvoyer l'utilisateur au login, exactement le
                # comportement attendu d'une vraie web app.
                if refresh_access_token():
                    yield from stream_message(message, attachments=attachments)
                    return
                st.error("🔑 Votre session a expiré. Merci de vous reconnecter.")
                logout()
                st.rerun()
                return

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "60")
                st.error(f"⏳ Trop de requêtes (100/min). Réessayez dans {retry_after}s.")
                yield f"Limite de requêtes atteinte. Réessayez dans {retry_after}s."
                return

            if response.status_code != 200:
                st.error(f"❌ Erreur {response.status_code}: {response.text}")
                yield f"Erreur: {response.status_code}"
                return

            for line in response.iter_lines():
                if not line:
                    continue

                if isinstance(line, bytes):
                    try:
                        line_str = line.decode("utf-8").strip()
                    except UnicodeDecodeError:
                        continue
                else:
                    line_str = str(line).strip()

                json_str = line_str[5:].strip() if line_str.startswith("data:") else line_str
                if not json_str:
                    continue

                try:
                    event = json.loads(json_str)
                except json.JSONDecodeError:
                    continue

                if event.get("type") == "token":
                    data = event.get("data", "")
                    if data:
                        yield data
                elif event.get("type") == "session":
                    new_session_id = event.get("data", {}).get("session_id")
                    if new_session_id:
                        st.session_state.session_id = new_session_id

    except requests.RequestException as e:
        st.error(f"Erreur de connexion : {e}")
        yield "Je suis désolé, une erreur de connexion s'est produite."
    except Exception as e:
        st.error(f"Erreur inattendue : {e}")
        yield "Je suis désolé, une erreur inattendue s'est produite."


def load_conversation_history(session_id: str):
    response = requests.get(
        HISTORY_URL.format(session_id=session_id),
        headers=get_headers(),
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    history = data.get("history", [])

    messages = []
    for item in history:
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    return messages


def load_user_conversations() -> list[dict]:
    """
    Remplace l'ancien fichier local `conversations_index.json`. La liste
    vient du Lambda, filtrée côté serveur sur `user_sub` (extrait du
    token) : chaque utilisateur ne voit QUE ses propres conversations,
    quel que soit l'appareil ou le navigateur utilisé.
    """
    try:
        response = requests.get(CONVERSATIONS_URL, headers=get_headers(), timeout=30)
        response.raise_for_status()
        return response.json().get("conversations", [])
    except requests.RequestException:
        return []


def _render_attachment_chips(attachments: list[dict]) -> str:
    """
    Construit le HTML des "chips" de fichiers joints à afficher au-dessus
    du texte d'un message. Contrairement à l'ancien `st.file_uploader`
    (affiché seul, au-dessus de la zone de saisie), ces chips font partie
    du message lui-même et restent donc attachées à la question qui les
    accompagne, même une fois la conversation avancée.
    """
    if not attachments:
        return ""

    chips = []
    for attachment in attachments:
        filename = html.escape(attachment.get("filename") or "fichier")
        status = attachment.get("status")

        if status == "indexed":
            chunks = attachment.get("chunks")
            detail = f" · {chunks} chunk(s)" if chunks is not None else ""
            chips.append(
                f'<span class="attachment-chip">'
                f'<span class="chip-icon">📎</span>'
                f'<span class="chip-name">{filename}</span>'
                f'<span class="chip-detail">{detail}</span>'
                f"</span>"
            )
        else:
            error = html.escape(attachment.get("error") or "rejeté")
            chips.append(
                f'<span class="attachment-chip chip-error">'
                f'<span class="chip-icon">⚠️</span>'
                f'<span class="chip-name">{filename}</span>'
                f'<span class="chip-detail"> · {error}</span>'
                f"</span>"
            )

    return f'<div class="msg-attachments">{"".join(chips)}</div>'


def render_message(message):
    role = message["role"]
    content = html.escape(message["content"])
    attachments_html = _render_attachment_chips(message.get("attachments") or [])

    # IMPORTANT : ne jamais placer une valeur potentiellement vide seule
    # sur sa propre ligne à l'intérieur du bloc HTML. Streamlit (comme
    # CommonMark) arrête l'interprétation HTML dès qu'il rencontre une
    # ligne vide au milieu du bloc, et bascule le reste en texte/“code”
    # indenté — c'est exactement ce qui produisait le `</div>` visible
    # et l'apostrophe échappée (`&#x27;`) affichés tels quels à l'écran.
    if role == "user":
        st.markdown(
            f"""
            <div class="user-row">
                <div class="user-bubble">{attachments_html}{content}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div class="assistant-row">
                <div class="assistant-bubble">{attachments_html}{content}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# =====================================================================
# PAGE CONFIG + CSS
# =====================================================================

st.set_page_config(page_title="Agent IA Autonome", layout="wide")

# ---------------------------------------------------------------------
# MODE CLAIR / SOMBRE
# ---------------------------------------------------------------------
# Le menu natif Streamlit (☰ en haut à droite) n'expose pas toujours
# l'entrée "Settings" -> bascule clair/sombre selon l'hébergement.
# On fournit donc notre propre interrupteur (dans la sidebar, plus bas)
# et on pilote nous-mêmes toutes les couleurs de l'app à partir de
# `st.session_state.dark_mode`, plutôt que de dépendre du thème choisi
# côté navigateur/Streamlit.
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False

_SV_LIGHT = {
    "bg": "#FFFFFF",
    "surface": "#F4F5F7",
    "text": "#111827",
    "muted": "#6B7280",
    "border": "rgba(17, 24, 39, 0.14)",
}
_SV_DARK = {
    "bg": "#14141C",
    "surface": "#1E1E2A",
    "text": "#ECECF3",
    "muted": "#A2A2B5",
    "border": "rgba(255, 255, 255, 0.16)",
}
_sv_palette = _SV_DARK if st.session_state.dark_mode else _SV_LIGHT

st.markdown(f"""
<style>
/* =====================================================================
   PALETTE SMARTOVATE
   Rose/violet issus du logo pour les accents. Le reste (fonds, texte,
   bordures) est piloté par notre propre interrupteur clair/sombre
   ci-dessus (`_sv_palette`), pas par le thème Streamlit natif — pour
   que la bascule fonctionne même si le menu "Settings" est masqué.
   ===================================================================== */
:root {{
    --sv-pink: #E63E6D;
    --sv-purple: #6C4C9C;
    --sv-gradient: linear-gradient(135deg, var(--sv-pink) 0%, var(--sv-purple) 100%);
    --sv-bg: {_sv_palette["bg"]};
    --sv-surface: {_sv_palette["surface"]};
    --sv-text: {_sv_palette["text"]};
    --sv-muted: {_sv_palette["muted"]};
    --sv-border: {_sv_palette["border"]};
}}

/* ---------- Fond général de l'application ---------- */
[data-testid="stAppViewContainer"],
[data-testid="stHeader"] {{
    background-color: var(--sv-bg) !important;
}}

.stApp, .stApp p, .stApp li, .stApp label,
.stApp h1, .stApp h2, .stApp h3, .stApp h4,
[data-testid="stMarkdownContainer"], .stCaption {{
    color: var(--sv-text);
}}

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"] {{
    background-color: var(--sv-surface);
    border-right: 1px solid var(--sv-border);
}}

[data-testid="stSidebar"] * {{
    color: var(--sv-text);
}}

.sv-logo-wrap {{
    display: flex;
    justify-content: center;
    padding: 0.25rem 0 0.5rem 0;
}}

.sv-logo-wrap img {{
    width: 100%;
    max-width: 180px;
    height: auto;
}}

.sv-sidebar-subtitle {{
    text-align: center;
    font-size: 1.35rem;
    font-weight: 700;
    letter-spacing: 0.01em;
    margin: -0.1rem 0 1.1rem 0;
    background: var(--sv-gradient);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
}}

/* ---------- Bulles de chat ---------- */
.user-row {{
    display: flex;
    justify-content: flex-end;
    margin: 0.5rem 0;
}}

.user-bubble {{
    background: var(--sv-gradient);
    color: #ffffff;
    padding: 0.75rem 1rem;
    border-radius: 18px 18px 4px 18px;
    max-width: 65%;
    line-height: 1.5;
    overflow-wrap: anywhere;
}}

.assistant-row {{
    display: flex;
    justify-content: flex-start;
    margin: 0.75rem 0;
}}

.assistant-bubble {{
    background-color: var(--sv-surface);
    color: var(--sv-text);
    padding: 0.85rem 1rem;
    border-radius: 18px 18px 18px 4px;
    max-width: 95%;
    line-height: 1.6;
    overflow-wrap: anywhere;
    border: 1px solid var(--sv-border);
}}

/* ---------- Fichiers joints, rattachés au message qui les accompagne ---------- */
.msg-attachments {{
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin-bottom: 0.45rem;
}}

.attachment-chip {{
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 0.78rem;
    padding: 0.3rem 0.7rem;
    border-radius: 999px;
    max-width: 260px;
    line-height: 1.2;
}}

.attachment-chip .chip-name {{
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}}

/* dans une bulle utilisateur (fond dégradé) : chip translucide blanche */
.user-row .attachment-chip {{
    background: rgba(255, 255, 255, 0.2);
    border: 1px solid rgba(255, 255, 255, 0.45);
    color: #ffffff;
}}

/* dans une bulle assistant : chip discrète sur le fond neutre */
.assistant-row .attachment-chip {{
    background: rgba(230, 62, 109, 0.12);
    border: 1px solid rgba(108, 76, 156, 0.35);
    color: var(--sv-text);
}}

/* fichier rejeté : accent rouge discret, toujours lisible clair/sombre */
.attachment-chip.chip-error {{
    background: rgba(220, 38, 38, 0.16);
    border: 1px solid rgba(220, 38, 38, 0.45);
    color: var(--sv-text);
}}

/* ---------- Boutons ---------- */
div.stButton > button:first-child {{
    background-color: transparent;
    color: var(--sv-text);
    border-color: var(--sv-border);
    border-radius: 999px;
}}

div.stButton > button:first-child:hover {{
    border-color: var(--sv-pink);
    color: var(--sv-pink);
}}

/* ---------- Zone de saisie du chat ---------- */
/* Le champ de saisie flotte dans un conteneur séparé, fixé en bas de
   l'écran (stBottomBlockContainer / stChatFloatingInputContainer selon
   la version de Streamlit), qui a SON PROPRE fond — le styler seul ne
   suffit pas, sinon la bande derrière le champ reste blanche. */
[data-testid="stBottom"],
[data-testid="stBottomBlockContainer"],
.stChatFloatingInputContainer,
.stBottom {{
    background-color: var(--sv-bg) !important;
}}

[data-testid="stChatInput"] {{
    background-color: var(--sv-surface);
    border: 1px solid var(--sv-border);
    border-radius: 16px;
}}

[data-testid="stChatInput"] textarea {{
    color: var(--sv-text) !important;
}}

[data-testid="stChatInput"] textarea::placeholder {{
    color: var(--sv-muted) !important;
}}

[data-testid="stChatInputSubmitButton"] {{
    background: var(--sv-gradient) !important;
    border: none !important;
}}
</style>
""", unsafe_allow_html=True)

# Monte le composant CookieManager une fois, à chaque exécution du script
# (avant toute logique d'auth) : c'est ce premier rendu qui permet au
# composant JS de se synchroniser avec le navigateur. Le monter tard ou
# seulement de façon conditionnelle est la cause typique des erreurs
# 'NoneType' ... rencontrées si on l'utilise avant qu'il ait eu ce cycle.
get_cookie_manager()

# Si une écriture de cookie a échoué au tour précédent (composant pas
# encore prêt), on la retente maintenant qu'un cycle de rendu s'est
# écoulé.
if st.session_state.get("cookie_write_pending"):
    try:
        get_cookie_manager().set(
            REFRESH_COOKIE_NAME,
            st.session_state.cookie_write_pending,
            max_age=REFRESH_COOKIE_MAX_AGE,
            key="set_refresh_cookie_retry",
        )
        del st.session_state["cookie_write_pending"]
    except Exception:
        pass  # on retentera au prochain rerun


# =====================================================================
# AUTH GATE — rien en dessous de ce bloc ne s'exécute tant que
# l'utilisateur n'est pas authentifié.
# =====================================================================

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    # Tentative de reconnexion silencieuse via le cookie de refresh_token
    # AVANT d'afficher le formulaire de login (comportement "vraie web app").
    if "restore_attempted" not in st.session_state:
        cookies = get_cookie_manager().get_all()
        if cookies is None:
            st.stop()  # composant pas encore prêt, on attend son rerun auto
        st.session_state.restore_attempted = True
        if REFRESH_COOKIE_NAME in cookies and try_restore_session_from_cookie():
            st.rerun()

if not st.session_state.logged_in:
    st.title("🔐 Agent IA Autonome")

    if "auth_view" not in st.session_state:
        st.session_state.auth_view = "login"

    tab_labels = {"login": "Connexion", "signup": "Créer un compte", "confirm": "Confirmer mon compte"}
    view = st.session_state.auth_view

    login_tab, signup_tab, confirm_tab = st.tabs(list(tab_labels.values()))

    with login_tab:
        st.subheader("Se connecter")
        login_email = st.text_input("Email", key="login_email")
        login_password = st.text_input("Mot de passe", type="password", key="login_password")
        if st.button("Connexion", key="login_button", use_container_width=True):
            success, message = cognito_login(login_email, login_password)
            if success:
                st.rerun()
            else:
                st.error(message)

    with signup_tab:
        st.subheader("Créer un compte")
        signup_email = st.text_input("Email", key="signup_email")
        signup_password = st.text_input(
            "Mot de passe (8 caractères min., 1 chiffre)", type="password", key="signup_password"
        )
        if st.button("Créer mon compte", key="signup_button", use_container_width=True):
            success, message = cognito_sign_up(signup_email, signup_password)
            if success:
                st.success(message)
            else:
                st.error(message)

    with confirm_tab:
        st.subheader("Confirmer mon compte")
        st.caption("Un code vous a été envoyé par email après l'inscription (pensez à vérifier vos spams).")
        confirm_email = st.text_input("Email", key="confirm_email")
        confirm_code = st.text_input("Code de confirmation", key="confirm_code")

        col_confirm, col_resend = st.columns(2)
        with col_confirm:
            if st.button("Confirmer", key="confirm_button", use_container_width=True):
                success, message = cognito_confirm_sign_up(confirm_email, confirm_code)
                if success:
                    st.success(message)
                else:
                    st.error(message)
        with col_resend:
            if st.button("Renvoyer le code", key="resend_button", use_container_width=True):
                success, message = cognito_resend_confirmation_code(confirm_email)
                if success:
                    st.success(message)
                else:
                    st.error(message)

    st.stop()


# =====================================================================
# APPLICATION (utilisateur authentifié à partir d'ici)
# =====================================================================

if "session_id" not in st.session_state:
    new_conversation()
if "messages" not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    st.markdown(
        f"""
        <div class="sv-logo-wrap">
            <img src="{SMARTOVATE_LOGO_DATA_URI}" alt="Smartovate" />
        </div>
        <div class="sv-sidebar-subtitle">Agent IA Autonome</div>
        """,
        unsafe_allow_html=True,
    )

    st.toggle("🌙 Mode sombre", key="dark_mode")

    if st.session_state.get("user_email"):
        st.caption(f"Connecté : {st.session_state.user_email}")

    if st.button("+ Nouvelle conversation", use_container_width=True):
        new_conversation()
        st.rerun()

    st.divider()
    st.title("Anciennes discussions")
    for conversation in load_user_conversations()[:20]:
        if st.button(
            conversation.get("title", "Sans titre"),
            key=f"conversation-{conversation['session_id']}",
            use_container_width=True,
        ):
            st.session_state.session_id = conversation["session_id"]
            st.session_state.messages = load_conversation_history(conversation["session_id"])
            st.rerun()

    st.divider()
    if st.button("Se déconnecter", use_container_width=True):
        logout()
        st.rerun()

########### Zone principale ################
st.header("Hi, How can I help you today?")

for message in st.session_state.messages:
    render_message(message)


# Champ de saisie unique, comme dans les vraies interfaces de chat IA :
# le trombone d'ajout de fichier est intégré à la zone de texte
# (icône 📎 dans le champ) plutôt que d'être un widget séparé qui reste
# affiché en permanence au-dessus de l'input.
chat_submission = st.chat_input(
    "Écrivez votre message... (vous pouvez joindre un ou plusieurs fichiers)",
    accept_file="multiple",
    file_type=[
        "pdf",
        "docx",
        "xlsx",
        "csv",
        "txt",
        "py",
        "md",
        "json",
    ],
)

if chat_submission and (chat_submission.text or chat_submission.files):

    user_message = (chat_submission.text or "").strip()
    attached_files = list(chat_submission.files or [])

    attachments = []

    if attached_files:
        with st.spinner("Analyse et indexation des fichiers..."):
            documents = upload_documents(attached_files)

        for document in documents:
            attachments.append(
                {
                    "filename": document.get("filename"),
                    "status": document.get("status"),
                    "chunks": document.get("chunks"),
                    "error": document.get("error"),
                }
            )
            # Feedback immédiat et discret (toast), en plus de la chip
            # persistante qui restera épinglée au message une fois envoyé.
            if document.get("status") == "indexed":
                st.toast(
                    f"{document.get('filename')} chargé : "
                    f"{document.get('chunks')} chunk(s) indexé(s).",
                    icon="📎",
                )
            else:
                st.toast(
                    f"{document.get('filename')} : "
                    f"{document.get('error', 'rejeté')}",
                    icon="⚠️",
                )

        # Si l'utilisateur a seulement joint des fichiers sans écrire de
        # texte, on complète avec une instruction implicite plutôt que
        # d'envoyer un message vide à l'agent.
        if not user_message:
            user_message = "Voici le(s) fichier(s) joint(s)."

    st.session_state.messages.append(
        {
            "role": "user",
            "content": user_message,
            "attachments": attachments,
        }
    )

    with st.chat_message("user"):
        render_message(st.session_state.messages[-1])

    with st.chat_message("assistant"):
        placeholder = st.empty()
        assistant_response = ""
        try:
            for chunk in stream_message(user_message, attachments=attachments):
                assistant_response += chunk
                with placeholder.container():
                    render_message({"role": "assistant", "content": assistant_response})

            if not assistant_response:
                assistant_response = "Je n'ai pas reçu de réponse exploitable."
                with placeholder.container():
                    render_message({"role": "assistant", "content": assistant_response})

            st.session_state.messages.append({"role": "assistant", "content": assistant_response})

        except Exception as error:
            st.error(f"Une erreur s'est produite : {error}")
import time

from langchain_core.tools import tool

from services.bedrock_service import invoke_titan_embedding
from services.document_index_service import document_session_id
from opensearch_config import opensearch


INDEX_NAME = "document-memory"

# OpenSearch Serverless (AOSS) rafraîchit l'index inversé (term/agg) quasi
# immédiatement, mais le graphe HNSW utilisé par les requêtes `knn` peut
# mettre beaucoup plus de temps que prévu à intégrer les vecteurs tout
# juste écrits (on a observé jusqu'à ~45s en pratique, surtout sur un
# index à faible trafic). Deux budgets de retry :
#   - "normal" : le fichier n'a pas été joint à ce tour précis (question
#     sur un document déjà uploadé il y a un moment) -> peu de retries,
#     pour ne pas ralentir inutilement une réponse.
#   - "patient" : un fichier vient d'être joint À CE TOUR (voir
#     `has_recent_upload`, propagé depuis le frontend via
#     `recent_attachments` -> state -> ce paramètre) -> on attend
#     beaucoup plus longtemps, pour donner sa chance à l'agent de
#     trouver la réponse en UN SEUL tour plutôt que de renvoyer la main
#     à l'utilisateur en lui demandant de reposer sa question.
#     Budget borné pour rester sous le timeout Lambda (60s) même en
#     comptant le reste du pipeline (embeddings, appels au modèle...).
_KNN_RETRY_ATTEMPTS_NORMAL = 5
_KNN_RETRY_DELAY_NORMAL = 2.0

_KNN_RETRY_ATTEMPTS_PATIENT = 11
_KNN_RETRY_DELAY_PATIENT = 3.0  # ~30s de budget max pour cet outil


def search_user_documents(
    query: str,
    user_sub: str,
    session_id: str,
    has_recent_upload: bool = False,
    recent_upload_filenames: list | None = None,
) -> str:
    """
    Fonction interne exécutée par le backend.

    user_sub et session_id proviennent du JWT / state
    et ne sont jamais fournis par le LLM.

    `has_recent_upload` indique qu'un fichier vient d'être joint à CE
    tour de conversation (cf. commentaire ci-dessus) : dans ce cas on
    utilise un budget de retry beaucoup plus généreux, et on ne
    s'arrête pas au premier résultat trouvé s'il provient en fait d'un
    fichier plus ancien déjà indexé dans la même session (voir
    `recent_upload_filenames`).
    """

    recent_upload_filenames = set(recent_upload_filenames or [])

    retry_attempts = (
        _KNN_RETRY_ATTEMPTS_PATIENT if has_recent_upload else _KNN_RETRY_ATTEMPTS_NORMAL
    )
    retry_delay = (
        _KNN_RETRY_DELAY_PATIENT if has_recent_upload else _KNN_RETRY_DELAY_NORMAL
    )

    try:

        if not query.strip():
            return "La requête documentaire est vide."

        embedding = invoke_titan_embedding(query)

        if not embedding:
            return (
                "Impossible de calculer l'embedding "
                "de la requête."
            )

        indexed_session_id = document_session_id(
            user_sub,
            session_id,
        )
        print(f" SEARCH: user_sub={user_sub!r} session_id={session_id!r} -> indexed_session_id={indexed_session_id!r}")

        search_query = {
            "size": 5,
            "query": {
                "knn": {
                    "embedding": {
                        "vector": embedding,
                        "k": 5,
                        "filter": {
                            "bool": {
                                "must": [
                                    {
                                        "term": {
                                            "session_id": indexed_session_id
                                        }
                                    },
                                    {
                                        "term": {
                                            "record_type": "user_document"
                                        }
                                    }
                                ]
                            }
                        }
                    }
                }
            }
        }

        hits = []

        for attempt in range(1, retry_attempts + 1):

            response = opensearch.search(
                index=INDEX_NAME,
                body=search_query,
            )

            hits = response.get(
                "hits",
                {}
            ).get(
                "hits",
                []
            )

            # Si on attend spécifiquement un fichier tout juste joint,
            # des résultats provenant d'un AUTRE fichier (déjà indexé
            # plus tôt dans la même session) ne comptent pas comme un
            # succès : on continue à réessayer jusqu'à trouver ce
            # fichier précis, sinon on renverrait par erreur le contenu
            # d'un fichier différent de celui dont l'utilisateur parle.
            if hits:
                if not recent_upload_filenames:
                    break
                hit_filenames = {
                    hit.get("_source", {}).get("filename")
                    for hit in hits
                }
                if hit_filenames & recent_upload_filenames:
                    break

            print(
                f"🔎 SEARCH: 0 hit pertinent (tentative {attempt}/{retry_attempts}) "
                f"pour indexed_session_id={indexed_session_id!r} "
                "-> nouvelle tentative (latence d'indexation KNN AOSS possible)"
            )

            if attempt < retry_attempts:
                time.sleep(retry_delay)

        matched_recent_file = False
        if hits:
            hit_filenames = {
                hit.get("_source", {}).get("filename")
                for hit in hits
            }
            matched_recent_file = bool(hit_filenames & recent_upload_filenames)

        needs_fallback = (not hits) or (recent_upload_filenames and not matched_recent_file)

        if needs_fallback:
            # Dernier filet de sécurité : si le fichier est bien listé
            # (visible via l'index inversé, qui se rafraîchit plus vite
            # que le graphe KNN), on renvoie ses premiers chunks sans
            # ranking sémantique plutôt que de prétendre qu'il n'existe
            # pas de fichier du tout. Si on attend un fichier précis, le
            # fallback est restreint à CE fichier (sinon on renverrait le
            # contenu d'un fichier différent de celui dont il est
            # question).
            fallback_hits = _term_only_fallback(
                indexed_session_id,
                only_filenames=recent_upload_filenames or None,
            )

            if fallback_hits:
                print(
                    f"🔎 SEARCH: fallback term-only utilisé "
                    f"({len(fallback_hits)} chunk(s)) pour "
                    f"indexed_session_id={indexed_session_id!r}"
                )
                hits = fallback_hits
            elif hits and not recent_upload_filenames:
                # On a bien des hits (juste sans avoir pu les confirmer
                # via le fallback, p.ex. erreur réseau) : mieux vaut les
                # renvoyer que de prétendre n'avoir rien trouvé.
                pass
            else:
                filename_hint = (
                    f" ({', '.join(recent_upload_filenames)})"
                    if recent_upload_filenames
                    else ""
                )
                return (
                    "Aucun résultat trouvé dans l'index documentaire pour "
                    f"l'instant pour le fichier joint à ce message{filename_hint}. "
                    "Ce fichier est probablement toujours en cours "
                    "d'indexation (cela peut prendre jusqu'à quelques "
                    "dizaines de secondes juste après un chargement) : "
                    "ne pas affirmer qu'aucun fichier n'a été fourni, "
                    "informer plutôt l'utilisateur que le traitement est "
                    "en cours et proposer de réessayer sa question dans "
                    "un instant. Si en revanche aucun fichier n'a jamais "
                    "été chargé dans cette conversation, l'indiquer "
                    "normalement."
                )

        print(f"🔎 SEARCH: {len(hits)} hit(s) trouvé(s) pour indexed_session_id={indexed_session_id!r}")
        results = []

        for number, hit in enumerate(
            hits,
            start=1,
        ):

            source = hit.get(
                "_source",
                {}
            )

            filename = source.get(
                "filename",
                "fichier inconnu",
            )

            chunk_id = source.get(
                "chunk_id",
                "?",
            )

            content = source.get(
                "content",
                "",
            )

            score = hit.get(
                "_score",
                0,
            )

            results.append(
                f"[{number}] "
                f"Fichier: {filename} | "
                f"Chunk: {chunk_id} | "
                f"Pertinence: {score:.3f}\n"
                f"{content}"
            )

        return "\n\n---\n\n".join(results)

    except Exception as error:

        return (
            "Erreur pendant la recherche dans les "
            f"documents : {error}"
        )


def _term_only_fallback(
    indexed_session_id: str,
    size: int = 5,
    only_filenames: set | None = None,
) -> list:
    """
    Repli sans embedding : simple filtre `term` (session_id + record_type,
    et éventuellement filename), trié par chunk_id. Utilisé uniquement si
    la recherche KNN n'a rien trouvé (ou rien de pertinent) après
    plusieurs tentatives alors que le document est bien indexé (cf.
    latence du graphe HNSW sur AOSS).
    """

    must_clauses = [
        {"term": {"session_id": indexed_session_id}},
        {"term": {"record_type": "user_document"}},
    ]

    if only_filenames:
        must_clauses.append(
            {"terms": {"filename": list(only_filenames)}}
        )

    fallback_query = {
        "size": size,
        "query": {"bool": {"must": must_clauses}},
        "sort": [{"chunk_id": "asc"}],
    }

    try:
        response = opensearch.search(
            index=INDEX_NAME,
            body=fallback_query,
        )
        return response.get("hits", {}).get("hits", [])
    except Exception as error:
        print(f"⚠️ Fallback term-only en échec : {error}")
        return []


@tool
def document_search(query: str) -> str:
    """
    Recherche dans les fichiers chargés par l'utilisateur.

    Utiliser cet outil lorsque la demande nécessite
    d'analyser, comparer, résumer ou extraire des
    informations provenant des fichiers uploadés.

    Les fichiers peuvent être des PDF, DOCX, XLSX,
    CSV, TXT, Python, Markdown ou JSON.

    Le contexte utilisateur et le session_id sont
    gérés automatiquement par le backend.
    """

    # Cette fonction ne devrait normalement jamais
    # être appelée directement par le backend,
    # car call_tools() injecte le contexte sécurisé.
    return (
        "Erreur interne : document_search doit être "
        "exécuté avec le contexte utilisateur."
    )
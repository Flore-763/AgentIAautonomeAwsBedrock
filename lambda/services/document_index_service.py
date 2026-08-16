# lambda/services/document_index_service.py

import os
import time
import uuid
import traceback
from langchain_text_splitters import RecursiveCharacterTextSplitter

from services.bedrock_service import invoke_titan_embedding
from opensearch_config import opensearch


# Index dédié aux fichiers uploadés par l'utilisateur, distinct de
# "conversation-memory" (mémoire long terme / RAG entreprise).
INDEX_NAME = "document-memory"


text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1200,
    chunk_overlap=200,
    separators=[
        "\n\n",
        "\n",
        " ",
        "",
    ],
)


def document_session_id(
    user_sub: str,
    session_id: str,
) -> str:
    """
    Namespace réservé aux documents utilisateur.

    On le distingue volontairement du session_id
    utilisé par la mémoire conversationnelle.
    """
    return f"document:{user_sub}:{session_id}"


def index_document(
    user_sub: str,
    session_id: str,
    document_id: str,
    filename: str,
    content: str,
) -> dict:

    if not content or not content.strip():
        raise ValueError(
            "Le document ne contient aucun texte exploitable."
        )

    chunks = text_splitter.split_text(content)

    if not chunks:
        raise ValueError(
            "Impossible de créer des morceaux de texte."
        )

    indexed_chunks = 0

    indexed_session_id = document_session_id(
        user_sub,
        session_id,
    )

    for chunk_number, chunk in enumerate(
        chunks,
        start=1,
    ):

        embedding = invoke_titan_embedding(chunk)

        if not embedding:
            continue

        document = {
            "record_type": "user_document",
            "user_sub": user_sub,
            "session_id": indexed_session_id,
            "original_session_id": session_id,
            "document_id": document_id,
            "filename": filename,
            "chunk_id": chunk_number,
            "content": chunk,
        }

        # Le vecteur doit avoir le même champ
        # que ton index actuel.
        document["embedding"] = embedding

        opensearch.index(
            index=INDEX_NAME,
            # id=f"{document_id}-{chunk_number}-{uuid.uuid4()}",
            body=document,
        )
        print(
            f" DOCUMENT INDEXÉ | "
            f"filename={filename!r} | "
            f"chunk={chunk_number} | "
            f"session={indexed_session_id!r}"
        )
        indexed_chunks += 1

    print(
        f"✅ INDEXATION TERMINÉE | "
        f"filename={filename!r} | "
        f"chunks={indexed_chunks} | "
        f"session={indexed_session_id!r}"
    )

    # AOSS rafraîchit l'index inversé quasi immédiatement, mais le graphe
    # HNSW (recherche `knn`) peut prendre quelques secondes de plus à
    # intégrer les vecteurs tout juste écrits, en particulier juste après
    # la création de l'index. On attend ici (best-effort, borné dans le
    # temps) que le dernier chunk soit réellement cherchable en KNN avant
    # de considérer l'upload terminé, pour éviter qu'un message envoyé
    # juste après l'upload ne tombe sur "aucun résultat".
    ready = _wait_until_knn_searchable(
        indexed_session_id,
        document_id,
        query_embedding=embedding,
    )

    if not ready:
        print(
            f"⚠️ Le document {filename!r} est indexé mais pas encore "
            "confirmé comme cherchable en KNN (le graphe AOSS est "
            "peut-être encore en cours de construction). "
            "Les premières questions pourraient nécessiter un nouvel essai."
        )

    return {
        "document_id": document_id,
        "filename": filename,
        "chunks": indexed_chunks,
        "searchable": ready,
    }


def _wait_until_knn_searchable(
    indexed_session_id: str,
    document_id: str,
    query_embedding: list,
    attempts: int = 5,
    delay_seconds: float = 1.5,
) -> bool:
    """
    Poll best-effort : interroge l'index en KNN (avec le vecteur du
    dernier chunk indexé) jusqu'à ce qu'au moins un résultat pour ce
    document_id soit renvoyé, ou jusqu'à expiration du budget de temps.
    Ne lève jamais d'exception : un échec ici ne doit pas faire échouer
    l'upload, seulement dégrader la fraîcheur de la confirmation.
    """

    check_query = {
        "size": 1,
        "query": {
            "knn": {
                "embedding": {
                    "vector": query_embedding,
                    "k": 1,
                    "filter": {
                        "bool": {
                            "must": [
                                {"term": {"session_id": indexed_session_id}},
                                {"term": {"document_id": document_id}},
                            ]
                        }
                    },
                }
            }
        },
    }

    for attempt in range(1, attempts + 1):
        try:
            response = opensearch.search(index=INDEX_NAME, body=check_query)
            hits = response.get("hits", {}).get("hits", [])
            if hits:
                return True
        except Exception as error:
            print(f"⚠️ _wait_until_knn_searchable erreur (tentative {attempt}): {error}")

        if attempt < attempts:
            time.sleep(delay_seconds)

    return False


def list_session_documents(user_sub: str, session_id: str) -> list[str]:
    """Retourne les noms de fichiers déjà indexés pour cette session."""
    indexed_session_id = document_session_id(user_sub, session_id)
    print(f"📥 INDEX: user_sub={user_sub!r} session_id={session_id!r} -> indexed_session_id={indexed_session_id!r}")
    query = {
        "size": 0,
        "query": {
            "bool": {
                "filter": [
                    {"term": {"session_id": indexed_session_id}},
                    {"term": {"record_type": "user_document"}},
                ]
            }
        },
        "aggs": {
            # "filename" est mappé en "keyword" directement dans
            # create_document_index.py (pas en "text" + sous-champ
            # ".keyword"). "filename.keyword" ne correspond donc à
            # aucun champ réel et l'agrégation renvoyait toujours 0
            # bucket, quelle que soit la latence d'indexation.
            "filenames": {"terms": {"field": "filename", "size": 50}}
        },
    }
    try:
        response = opensearch.search(index=INDEX_NAME, body=query)
        buckets = response.get("aggregations", {}).get("filenames", {}).get("buckets", [])
        return [b["key"] for b in buckets]
    except Exception as e:
        print(f"list_session_documents Error: {e}")
        traceback.print_exc()
        return []
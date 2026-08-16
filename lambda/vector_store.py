"""
vector_store.py
==================

Fine couche au-dessus d'OpenSearch (Serverless / AOSS) pour la mémoire
sémantique long terme :
  - `save_document(...)`   : indexe un texte + son embedding.
  - `semantic_search(...)` : recherche par similarité vectorielle (k-NN),
                             avec filtres optionnels sur `session_id` et
                             `timestamp`.

Utilisé par :
  - `services/agent_service.py` (récupération des souvenirs pertinents),
  - `tools/search.py` (outil `recherche_documentaire`, base de connaissances),
  - `index_pdf.py` (indexation initiale des documents internes).
"""

from opensearch_config import opensearch

INDEX_NAME = "conversation-memory"


class VectorStore:
    """Wrapper simple autour du client OpenSearch pour la recherche vectorielle."""

    def __init__(self):
        self.client = opensearch

    def save_document(self, session_id, role, content, timestamp, embedding):
        """
        Indexe un document (message ou chunk de PDF) avec son embedding.

        On n'indexe que si un embedding a été calculé : sinon le champ
        `knn_vector` recevrait `None` et OpenSearch rejetterait le document.
        """
        if embedding is None:
            return

        self.client.index(
            index=INDEX_NAME,
            body={
                "session_id": session_id,
                "role": role,
                "content": content,
                "timestamp": timestamp,
                "embedding": embedding,
            },
        )

    def semantic_search(self, embedding, k=3, session_id=None, before_timestamp=None):
        """
        Recherche les `k` documents les plus proches sémantiquement de
        `embedding` (distance vectorielle k-NN), avec filtres optionnels :
          - `session_id`      : ne chercher que dans une session donnée
                                 (ou la base de connaissances `knowledge_base`).
          - `before_timestamp` : ne remonter que des souvenirs antérieurs à
                                 ce timestamp (évite la redondance avec la
                                 mémoire court terme déjà chargée).
        """
        query = {
            "size": k,
            "query": {
                "bool": {
                    "must": [{"knn": {"embedding": {"vector": embedding, "k": k}}}],
                    "filter": [],
                }
            },
        }

        if session_id:
            query["query"]["bool"]["filter"].append({"term": {"session_id": session_id}})

        if before_timestamp:
            query["query"]["bool"]["filter"].append(
                {"range": {"timestamp": {"lt": before_timestamp}}}
            )

        response = self.client.search(index=INDEX_NAME, body=query)
        return response["hits"]["hits"]


# Instance singleton réutilisée dans tout le projet.
vector_store = VectorStore()

from opensearch_config import opensearch, INDEX_NAME
from opensearchpy.exceptions import ConflictError

body={

    "settings":{

        "index":{
            "knn":True
        }

    },

    "mappings":{

        "properties":{

            "session_id":{
                "type":"keyword"
            },

            "role":{
                "type":"keyword"
            },

            "content":{
                "type":"text"
            },

            "timestamp":{
                "type":"date"
            },

            "embedding":{

                "type":"knn_vector",

                "dimension":1024,

                # OpenSearch Serverless (AOSS) exige un moteur explicite pour les
                # index vectoriels : "nmslib" (par défaut sur OpenSearch classique)
                # n'est pas supporté par AOSS. On utilise "faiss" + "hnsw", qui
                # supporte en plus le filtrage combiné avec session_id/timestamp
                # utilisé dans vector_store.semantic_search().
                "method": {
                    "name": "hnsw",
                    "engine": "faiss",
                    "space_type": "l2",
                    "parameters": {
                        "ef_construction": 128,
                        "m": 24
                    }
                }

            }

        }

    }

}

if opensearch.indices.exists(index=INDEX_NAME):
    print(f"L'index '{INDEX_NAME}' existe déjà.")
else:
    opensearch.indices.create(
        index=INDEX_NAME,
        body=body
    )
    print("Index créé.")
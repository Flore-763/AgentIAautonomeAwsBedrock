# from opensearch_config import opensearch, INDEX_NAME
# from opensearchpy.exceptions import ConflictError
# # DOCUMENT_INDEX_NAME = "document-memory"
# # opensearch_config.py - Add debug info
import os
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth
import boto3

# Add debug
session = boto3.Session()
credentials = session.get_credentials()
region = session.region_name or "us-west-2"
_default_host = "lyyrsiu0wihuv6t78nm4.us-west-2.aoss.amazonaws.com"
_raw_endpoint = os.environ.get("OPENSEARCH_ENDPOINT", _default_host)

OPENSEARCH_HOST = _raw_endpoint.replace("https://", "").replace("http://", "").rstrip("/")

print(f"Region: {region}")
print(f"Access Key ID: {credentials.access_key[:10]}...")  # Log only partial for security
print(f"Using endpoint: {OPENSEARCH_HOST}")

# Make sure you're using the right service name
awsauth = AWS4Auth(
    credentials.access_key,
    credentials.secret_key,
    region,
    "aoss",  #  Correct for OpenSearch Serverless
    session_token=credentials.token
)

opensearch = OpenSearch(
    headers={
        "Content-Type":"application/json"
    },
    hosts=[{
        "host": OPENSEARCH_HOST,
        "port":443
    }],

    http_auth=awsauth,

    use_ssl=True,

    verify_certs=True,
    connection_class = RequestsHttpConnection
)

INDEX_NAME="document-memory"


body = {
    "settings": {
        "index": {
            "knn": True
        }
    },
    "mappings": {
        "properties": {
            "record_type": {
                "type": "keyword"
            },

            "user_sub": {
                "type": "keyword"
            },

            "session_id": {
                "type": "keyword"
            },

            "original_session_id": {
                "type": "keyword"
            },

            "document_id": {
                "type": "keyword"
            },

            "filename": {
                "type": "keyword"
            },

            "chunk_id": {
                "type": "integer"
            },

            "content": {
                "type": "text"
            },

            "embedding": {
                "type": "knn_vector",
                "dimension": 1024,
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
    print(
        f"L'index '{INDEX_NAME}' existe déjà."
    )
else:
    opensearch.indices.create(
        index=INDEX_NAME,
        body=body
    )
    print(
        f" Index '{INDEX_NAME}' créé."
    )
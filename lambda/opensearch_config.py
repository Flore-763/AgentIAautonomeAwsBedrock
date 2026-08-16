import os
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth
import boto3



session=boto3.Session()
credentials=session.get_credentials()
region= session.region_name or "us-west-2"
service ="aoss"


_default_host = "lyyrsiu0wihuv6t78nm4.us-west-2.aoss.amazonaws.com"
_raw_endpoint = os.environ.get("OPENSEARCH_ENDPOINT", _default_host)
# _raw_endpoint = os.environ.get("OPENSEARCH_ENDPOINT")


if not _raw_endpoint:
    raise ValueError(
        " OPENSEARCH_ENDPOINT environment variable is not set! "
        "Please set it to your OpenSearch Serverless collection endpoint."
    )

OPENSEARCH_HOST = _raw_endpoint.replace("https://", "").replace("http://", "").rstrip("/")

INDEX_NAME = "conversation-memory"
# INDEX_NAME = "document-memory"


awsauth = AWS4Auth(
    credentials.access_key,
    credentials.secret_key,
    region,
    "aoss",
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
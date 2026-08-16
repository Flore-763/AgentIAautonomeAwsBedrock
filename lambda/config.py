"""
config.py
===========

Configuration centralisée des clients AWS (DynamoDB, Bedrock Runtime).
Ce module est importé par `services/memory_service.py` et
`services/bedrock_service.py` : les clients boto3 sont créés UNE SEULE FOIS
par conteneur Lambda (warm start), ce qui évite de recréer une connexion à
chaque invocation.
"""

import os

import boto3

# --- DynamoDB (mémoire conversationnelle court/long terme brute) ---
dynamodb = boto3.resource("dynamodb")
table_name = os.getenv("TABLE_NAME")
table = dynamodb.Table(table_name) if table_name else None

# --- Bedrock Runtime (appels bas niveau : embeddings, invoke_model direct) ---
bedrock_runtime = boto3.client(
    "bedrock-runtime",
    region_name=os.getenv("BEDROCK_REGION", "us-west-2"),
)

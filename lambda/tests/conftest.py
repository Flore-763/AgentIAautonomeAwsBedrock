"""
tests/conftest.py
===================

Ce fichier est chargé par pytest AVANT toute collecte de test. Il fait
deux choses, dans cet ordre, avant que le moindre module du projet ne
soit importé par un fichier de test :

  1. Ajoute `lambda/` (le dossier parent de `tests/`) à `sys.path`, pour
     que les imports du code testé (`from tools.calculator import
     calculator`, `from services.memory_service import ...`, etc.)
     fonctionnent exactement comme en production, où `lambda/` est la
     racine du conteneur Lambda.

  2. Définit des variables d'environnement BIDON pour toutes les
     ressources AWS (nom de table DynamoDB, endpoint OpenSearch, région,
     credentials factices...). Objectif : permettre à `config.py` et
     `opensearch_config.py` de CONSTRUIRE leurs clients boto3/OpenSearch
     au moment de l'import (ils font ça au niveau module, donc dès le
     premier `import`), sans jamais lever d'exception faute de config —
     et SANS jamais faire de vrai appel réseau, puisque chaque test
     mocke explicitement (`monkeypatch`/`unittest.mock`) le SEUL point
     d'entrée externe qui l'intéresse (`requests.get`, le client
     OpenSearch, `invoke_titan_embedding`, etc.).

Ces tests ne parlent JAMAIS à un vrai service AWS, Tavily ou Open-Meteo :
c'est tout l'intérêt du "mock LLM"/"mock outils" demandé par le cahier
des charges (AGENT-TK-08) — on teste la LOGIQUE de chaque outil (parsing,
formatage, gestion d'erreur, retries...), pas la disponibilité d'un
service tiers.
"""

import os
import sys

# lambda/ (racine du conteneur Lambda en production) : permet
# "from tools.calculator import calculator", "from services.memory_service
# import ...", etc.
_LAMBDA_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _LAMBDA_DIR)

# Racine du projet (parent de lambda/) : le stack CDK vit dans
# `aws_ai_agent/`, un dossier SIBLING de `lambda/`, pas dedans. Sans ce
# chemin, tout test qui importe `aws_ai_agent.aws_ai_agent_stack` (ex:
# tests/unit/test_aws_ai_agent_stack.py) échoue avec
# `ModuleNotFoundError: No module named 'aws_ai_agent'`, même si le
# fichier est bien présent sur le disque à côté de lambda/.
_PROJECT_ROOT = os.path.dirname(_LAMBDA_DIR)
sys.path.insert(0, _PROJECT_ROOT)

_FAKE_ENV = {
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_DEFAULT_REGION": "us-west-2",
    "BEDROCK_REGION": "us-west-2",
    "TABLE_NAME": "test-agent-memory",
    "OPENSEARCH_ENDPOINT": "test-collection.us-west-2.aoss.amazonaws.com",
    "RATE_LIMIT_TABLE_NAME": "test-agent-api-rate-limit",
    "API_KEYS_TABLE_NAME": "test-agent-api-keys",
    "CONVERSATIONS_INDEX_TABLE_NAME": "test-agent-conversations-index",
    "COGNITO_USER_POOL_ID": "us-west-2_TESTPOOL",
    "COGNITO_CLIENT_ID": "test-cognito-client-id",
    "KNOWLEDGE_BUCKET_NAME": "test-agent-ia-knowledge-documents",
    "TAVILY_SECRET_NAME": "test/tavily-api-key",
}
for _key, _value in _FAKE_ENV.items():
    os.environ.setdefault(_key, _value)

"""
    services/api_key_service.py

    Validation des clés API applicatives.

    Pourquoi ce module(et pas seulement l'API Key/usagePaln d'API Gateway):
    le conteneur lambda est invoqué à la fois via la Function URL (streaming utilisée par le frontend Streamlit)
    et via API Gateway . Dans les deux cas, AWS Lambda Web Adapter traduit l'invocation en une requete HTTP locale
    traitée par `server.py`. La Function URL est nécessairement en `AuthType.NONE`(le streaming SSE ne fonctionne pas avec `AWS_IAM`):
    ni IAM ni API Gatrway ne protègent donc cette entrée-là.La vérification doit se faire dans le cpode applicatif, sur le
    header `x-api-key`, avant tout traitement. c'est le role de ce module, appelé depuis `server.py`.

    Les clés valides sont stockées dans une table DynamoDB dédiée(`AgentApiKEysTable`), gérée hors déploiement (ajout/révocation via AWS CLI ou Console, pas âr le CDK):
    partition key = la clé elle-même, attribut `acive`(bool, permet de révoquer sans supprimer l'item).

    exemple pour ajouter une clé:
    aws dynamodb put-item --table-name agent-api-keys --item file://item.json
"""
import os 
from typing import Optional
import boto3  
from botocore.exceptions import ClientError

API_KEYS_TABLE_NAME = os.getenv("API_KEYS_TABLE_NAME")

_dynamodb=boto3.resource("dynamodb")
_table= _dynamodb.Table(API_KEYS_TABLE_NAME) if API_KEYS_TABLE_NAME else None

def is_valid_api_key(api_key:Optional[str]) -> bool:
    """True si `api_key` existe dans la table est active.

    Fail-closed: si la table est configurée mais l'appel DynamoDB echoue,
    on refuse l'accès (contrairement au rate limiting, une panne d'infra ne doit pas se traduire par une API grande ouverte).

    Si la table n'est pas configurée du tout(variable d'env absente,typiquement en dev local sans déploiement AWS), on laisse passer pour ne pas bloquer
    le développemnt comme le fait déjà `config.py` pour `TABLE_NAME`.

    
    """

    if _table is None:
        return True

    if not api_key:
        return False

    try:
        response = _table.get_item(Key={"api_key":api_key})
    except ClientError as error:
        print(f"Erreur de vérification de la clé API(fail-closed):{error}")
        return False

    item = response.get("Item")
    return bool(item) and item.get("active",True)
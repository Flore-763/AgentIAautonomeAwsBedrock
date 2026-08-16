"""
services/auth_service.py
=========================
 
Vérification des tokens JWT émis par Cognito (User Pool), pour identifier
l'utilisateur derrière chaque requête sur la Function URL.
 
Principe (identique dans son esprit à api_key_service.py, mais pour
l'identité de l'utilisateur plutôt que l'app appelante) :
  - Le client (UI.py) envoie le "id_token" Cognito dans le header
    `Authorization: Bearer <token>` après avoir fait InitiateAuth.
  - On vérifie la SIGNATURE du token contre les clés publiques (JWKS) du
    User Pool -> ça prouve que le token a bien été émis par NOTRE Cognito,
    sans jamais contacter Cognito lui-même (vérification cryptographique
    pure, donc rapide, et ne nécessite aucune permission IAM).
  - On vérifie ensuite `aud` (= notre client_id), `iss` (= notre user
    pool) et l'expiration, comme n'importe quel JWT standard.
    - Le champ `sub` du payload est l'identifiant STABLE et unique de
    l'utilisateur (un UUID généré par Cognito à la création du compte,
    ne change jamais, contrairement à l'email qui peut être modifié).
    C'est CE champ qu'on utilise partout ensuite pour cloisonner les
    données (session_id namespacé, rate limiting, sidebar).
 
Les clés JWKS sont mises en cache en mémoire du conteneur Lambda (comme
`config.py` le fait pour les clients boto3) : récupérées une seule fois
par "warm start", pas à chaque requête.
"""

import json
import os
import time
from urllib.request import urlopen

from jose import jwt 
from jose.exceptions import JOSEError

AWS_REGION = os.getenv("BEDROCK_REGION", "us-west-2")

USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID")
CLIENT_ID = os.getenv("COGNITO_CLIENT_ID")

_JWKS_URL= (f"https://cognito-idp.{AWS_REGION}.amazonaws.com/{USER_POOL_ID}/.well-known/jwks.json"
            if USER_POOL_ID else None)

_ISSUER=(f"https://cognito-idp.{AWS_REGION}.amazonaws.com/{USER_POOL_ID}"
            if USER_POOL_ID else None)

#Cache mémoire du conteneur:(keys,fetched_at). Pas de TTL aggressif,
# les clés JWKS de Cognito changent extrememet rarement (rotation planifiée).

_jwks_cache:dict | None = None
_JWKS_CACHE_TTL_SECONDS = 3600

def _get_jwks() -> list:
    """Récupère et met en cache les clés publics JWKS du User Pool."""
    global _jwks_cache
    now=time.time()
    if _jwks_cache is not None and (now - _jwks_cache["fetched_at"]) < _JWKS_CACHE_TTL_SECONDS:
        return _jwks_cache["keys"]

    with urlopen(_JWKS_URL, timeout=5) as response:
        keys=json.loads(response.read())["keys"]

    _jwks_cache={"keys":keys, "fetched_at":now}
    return keys


def verify_id_token(token:str) -> dict | None:
    """vérifie un id_token Cognito et retourne son payload décodé si valide.
    Returns:
        dict avec au minimum `sub`(identifiant utilisateur) et `email` si le token est vzlide sinon None

    Fail-closed volontaire (contrairement au rate limiting) : un problème
    de vérification de token doit bloquer l'accès, pas l'autoriser -
    l'identité de l'utilisateur est ce qui protège ses propres données.
    
    """

    if not token or not USER_POOL_ID or not CLIENT_ID:
        return None

    try :
        unverified_headers=jwt.get_unverified_header(token)
        kid = unverified_headers.get("kid")
        key=next((k for k in _get_jwks() if k["kid"] == kid), None)
        if key is None:
            return None
        payload = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=CLIENT_ID,
            issuer=_ISSUER,
        )

        # Un access_token et un id_token ont des claims différents;
        # on exige explicitement un id_token(celui qui contient l'email).

        if payload.get("token_use")!="id":
            return None
        return payload

    except JOSEError as error:
        print(f"Token JWT inavlide:{error}")
        return None
    except Exception as error:
        print(
            f"Erreur inattendue lors de la vérification du token:{error}"
        )
        return None
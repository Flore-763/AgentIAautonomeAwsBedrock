import json
import os
import time
from datetime import datetime, timezone
import boto3 
from boto3.dynamodb.conditions import Key    
from decimal import Decimal




## INITIALISATION

dynamodb = boto3.resource("dynamodb")
table_name= os.environ["TABLE_NAME"]
table= dynamodb.Table(table_name)


### Fonctions utilitaires

def get_expiration_time():
    """ 
        Retourne un timestamp Unix correspondant à une expiration au bout de 30 jours.
    """
    return int(
        time.time() + (30*24*60*60)
    )

def decimal_to_int(obj):

    if isinstance(obj, Decimal):
        return int(obj)

    raise TypeError(
        f"Type {type(obj)} non sérialisable"
    )


## HANDLER PRINCIPALE

def lambda_handler(event, context):

    print("Agent Lambda started ...")
    print("Event: ")
    print(json.dumps(event))


    http_method = event.get(
        "httpMethod"
    )

    path = event.get(
        "path"
    )



    ### POST: /agent/chat



    if(
        http_method =="POST" and path =="/agent/chat"
    ):
        body = json.loads(
            event.get("body" ) or "{}"
        )

        session_id = body.get("session_id")

        message = body.get("message")

        if not session_id or not message:
            return{
                "statusCode":400,

                "body": json.dumps({
                    "error": (
                        "session_id et message sont obligatoires" 
                    )
                })
            }
        

        timestamp = datetime.now(
            timezone.utc
        ).isoformat()

        expiration_time = (get_expiration_time())

        table.put_item(
            Item= {
                "session_id": session_id,
                "timestamp": timestamp,
                "role": "user",
                "content": message,
                "ttl": (expiration_time)
            }
        )

        return {

        "statusCode": 200,

        "headers": {
            "Content-Type": "application/json"
        },

        "body": json.dumps({

            "message": (
                "Message enregistré avec succes"
            ),

            "session_id": session_id,
            "timestamp": timestamp

            })

         }
    

    ### GET : /agent/sessions/{id}/history

    if http_method == "GET"  :
        path_parameters = (
            event.get ("pathParameters") or {}
        )
        
        session_id= (
            path_parameters.get("id")
        )

        if not session_id:

            return{
                "statusCode": 400,
                "body":json.dumps({
                    "error": (
                        "session_id manquant"
                    )
                })
            }

        response = table.query(
            KeyConditionExpression = Key(
                "session_id"
            ).eq(session_id)
        )

        return {
            "statusCode" : 200,
            "headers": {"Content-Type":(
                "application/json"
            )
            },

            "body": json.dumps({
                "session_id": session_id,
                "history": response.get(
                    "Items",
                    []
                )
            },default=decimal_to_int)
        }
    

    return {

        "statusCode": 404,

        "body": json.dumps({

            "error": "Route inconnue"

        })

    }


    
import boto3 
import time
from datetime import datetime, timezone

dynamo= boto3.resource(
    "dynamodb",
    region_name ="us-west-2"
)

table= dynamo.Table("agent-memory")

session_id= "session-test-002"

timestamp =datetime.now(
timezone.utc
).isoformat()

expiration_time = int(
    time.time()
) + (30*24*60*60)   # 30 jours de durée de vie.

table.put_item(
    Item= {
        "session_id": session_id,
        "timestamp": timestamp,
        "role": "user",
        "content":(
            "la deuxieme session de discussion"
        ),
        "ttl": expiration_time
    }
)

print("Message enregistré avec succès.")
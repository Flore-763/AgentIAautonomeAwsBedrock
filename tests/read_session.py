import boto3 
from boto3.dynamodb.conditions import Key


dynamodb= boto3.resource(
    "dynamodb",
    region_name= "us-west-2"
)

table = dynamodb.Table("agent-memory")

session_id = "session-test-002"

response = table.query(
    KeyConditionExpression= Key(
        "session_id"
    ).eq(session_id)
)


items = response.get(
    "Items",
    []
)

for item in items:

    print(
        f"{item['timestamp']} : "
        f"{item['role']} : "
        f"{item['content']}"
    )
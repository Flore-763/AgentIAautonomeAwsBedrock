from aws_cdk import (
    Duration,
    Stack, # un stack est une unite de deploiement CloudFormation
    # aws_iam as iam,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
    aws_lambda as lambda_,
    aws_apigateway as apigateway,
    RemovalPolicy,
    
)
from constructs import Construct

class AwsAiAgentStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        
        ## Table DYNAMODB: Memoire de l'agent

        agent_memory_table= dynamodb.Table(
            self,
            "AgentMemoryTable", # identifiant logique: c'est a dire le nom de la ressource pour cloudformation
            table_name= "agent-memory",

            partition_key= dynamodb.Attribute(  # la clé qui regroupe tous les événements d'une session.
                name="session_id",
                type=dynamodb.AttributeType.STRING
            ),

            sort_key= dynamodb.Attribute(   # clé de tri permet d'ordonner les événements à l'intérieur d'une session
                name="timestamp",
                type=dynamodb.AttributeType.STRING
            ),

            time_to_live_attribute="ttl", # a definir dans lambda

            billing_mode= dynamodb.BillingMode.PAY_PER_REQUEST,

            removal_policy = RemovalPolicy.DESTROY # en cas de cdk destroy, le table et tout le contenu sera detruit.
        )


        #### Bucket S3 pour le stockage des documents d'apprentissage

        knowledge_bucket = s3.Bucket(
            self,
            "KnowledgeBucket",
            bucket_name= "agent-ia-knowledge-documents",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL, # les docs ne doivent pas etre accessibles publiquement
            encryption= s3.BucketEncryption.S3_MANAGED, ## Les docs sont chiffrés.  
            removal_policy = RemovalPolicy.DESTROY,
            auto_delete_objects = True

        )




        ### l'Agent lambda

        agent_lambda = lambda_.Function(
            self,
            "AgentLambda",
            runtime = lambda_.Runtime.PYTHON_3_12, 
            handler = "agent_handler.lambda_handler", ## le fichier et la fonction principale
            code = lambda_.Code.from_asset(
                "lambda"
            ),

            environment = {
                "TABLE_NAME": (
                    agent_memory_table.table_name
                )
            }, 

            timeout = Duration.seconds(
                30
            ),

            memory_size= 512,
        )




        api = apigateway.RestApi(

            self,

            "AgentApi",

            rest_api_name="Agent API",

            description=(
                "API pour l'agent IA autonome"
            ),

            deploy_options=apigateway.StageOptions(

                stage_name="prod"
            )

         )
        

        lambda_integration = (
            apigateway.LambdaIntegration(
                agent_lambda
            )
        )

        agent_resource = (api.root.add_resource(
            "agent"    ### racine des urls
        )
        )



        ##### créer  POST : /agent/chat

        chat_resource = (
            agent_resource.add_resource(
                "chat"
            )
        )
        chat_resource.add_method(
            "POST",
            lambda_integration
        )


        #### créer  GET  /agent/sessions/{id}/history

        sessions_resource= (
            agent_resource.add_resource(
                "sessions"
            )
        )
        session_id_resource = (
            sessions_resource.add_resource(
                "{id}"
            )
        )

        history_resource = (
            session_id_resource.add_resource(
                "history"
            )
        )


        history_resource.add_method(

            "GET",

            lambda_integration
        )



        ###  ROLE IAM POUR  LAMBDA

        ### plus besoin de creer le role vu qu'on a configurer le service aws lambda
        # agent_lambda_role = iam.Role(
        #     self,
        #     "AgentLambdaExecutionRole",
        #     assumed_by = iam.ServicePrincipal("lambda.amazonaws.com"),

        #     description= (
        #         "Role used by AI Agent Lambda"
        #         "to acces only the required AWS services."
        #     )
        # )


        ### Permissions lambda sur dynamodb

        agent_memory_table.grant_read_write_data(  # peut interroger , lire et ecrire
            agent_lambda
        )

        ### Permissions lambda sur dynamodb

        knowledge_bucket.grant_read(  # lambda peut juste lire
            agent_lambda
        )

        ## Permissions lambda sur cloudwatch pour les logs

        # agent_lambda.add_to_policy(
        #     iam.PolicyStatement(
        #         sid= "AllowCloudWatchLogs",
        #         effect=iam.Effect.ALLOW,
        #         actions=[
        #             "logs:CreateLogGroup",
        #             "logs:CreateLogStream",
        #             "logs:PutLogEvents",
        #         ],
        #         resources=["*"]
        #     )
        # )

       
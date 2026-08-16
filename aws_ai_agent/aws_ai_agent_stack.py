from aws_cdk import (
    Duration,
    Stack, # un stack est une unite de deploiement CloudFormation
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
    aws_lambda as lambda_,
    aws_apigateway as apigateway,
    aws_iam as iam,
    aws_cognito as cognito,
    RemovalPolicy, # definit ce qui arrive aux ressources quand je detruis le stack
    aws_opensearchserverless as aoss,
    CfnOutput   # permet d'afficher une valeur utilse apres le deploiement, par exemple l'endpoint OpenSearch
)
import json
import os
from constructs import Construct # construct est un bloc d'infrastructure: table dynamo,lambda,..

class AwsAiAgentStack(Stack): # classe qui decrit mon infrastructure

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        
        ## Table DYNAMODB: Memoire de l'agent

        agent_memory_table= dynamodb.Table(
            self,
            "AgentMemoryTable", # identifiant logique: c'est a dire le nom de la ressource pour cloudformation
            table_name= "agent-memory",

            partition_key= dynamodb.Attribute(  # DynamoDB regroupe les messages par session de conversation
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


        ## Table DYNAMODB : compteur de rate limiting (100 req/min par clé API)
        # Clé de partition unique = "{api_key_id}#{fenêtre_minute}" (voir
        # services/rate_limit_service.py). Le TTL purge automatiquement les
        # anciennes fenêtres, pas besoin de job de nettoyage.
        rate_limit_table = dynamodb.Table(
            self,
            "ApiRateLimitTable",
            table_name="agent-api-rate-limit",
            partition_key=dynamodb.Attribute(
                name="rate_limit_key",
                type=dynamodb.AttributeType.STRING,
            ),
            time_to_live_attribute="ttl",
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        ## Table DYNAMODB : clés API applicatives valides
        # Protège l'entrée réelle utilisée par le frontend Streamlit : la
        # Function URL (AuthType.NONE, obligatoire pour le streaming) n'est
        # protégée ni par IAM ni par API Gateway. La vérification se fait
        # donc dans le code applicatif (server.py), contre cette table.
        # Partition key = la clé API elle-même. Gérée hors déploiement
        # (ajout/révocation via `aws dynamodb put-item` / Console), donc
        # PAS de removal_policy DESTROY : on ne veut pas perdre les clés
        # en production à chaque `cdk deploy`.
        api_keys_table = dynamodb.Table(
            self,
            "AgentApiKeysTable",
            table_name="agent-api-keys",
            partition_key=dynamodb.Attribute(
                name="api_key",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
        )

        ### Table DYNAMODB: index des conversations par utilisateur
        #remplace le fichier local conversations_index.jon du UI.py que j'avais qui ne fonctionne pas en multi-user(partagé/perdu entre utilisateurs)
        # partition_key = user_sub(identifiant Cognito stable de l'utilisateur)
        # sort key = session_id -> permet un Query "toutes les conversations de ce utilisateur",triées sans jamais voir celles des autres

        conversations_index_table =dynamodb.Table(
            self,
            "ConversationsIndexTable",
            table_name="agent-conversations-index",
            partition_key=dynamodb.Attribute(
                name="user_sub",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="session_id",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
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

        # aws impose toujours Encryption Policy, Network Policy, Access Policy, Collection pour opensearch

        current_user_arn = f"arn:aws:sts::136609826386:assumed-role/AWSReservedSSO_AdministratorAccess_e4bb8ceea756d078/simporeflore763@gmail.com"

        encryption_policy = aoss.CfnSecurityPolicy(
            self,
            "VectorEncryptionPolicy",
            name="vector-encryption-policy",
            type="encryption",
            policy=json.dumps({
                "Rules":[
                    {
                        "Resource":[
                            "collection/agent-memory"
                        ],
                        "ResourceType":"collection"
                    }
                ],
                "AWSOwnedKey":True
            })
        )

        network_policy = aoss.CfnSecurityPolicy(

            self,

            "VectorNetworkPolicy",

            name="vector-network-policy",

            type="network",

            policy=json.dumps([

                {

                    "Rules":[

                        {

                            "Resource":[
                                "collection/agent-memory"
                            ],

                            "ResourceType":"collection"

                        }

                    ],

                    "AllowFromPublic":True

                }

            ])

        )

        

        vector_collection = aoss.CfnCollection(

            self,

            "VectorCollection",

            name="agent-memory",

            type="VECTORSEARCH"
        )


        vector_collection.add_dependency(
            encryption_policy
        )
        vector_collection.add_dependency(
            network_policy
        )


        ## COGNITO : annuaire des utilisateurs (inscription + authentification)
        # self_sign_up_enabled=True -> un visiteur peut créer lui-même son
        # compte (SignUp), pas besoin qu'un admin le crée à la main.
        # auto_verify=email -> Cognito envoie un code de confirmation par
        # mail après l'inscription (ConfirmSignUp), evite les faux comptes.

        user_pool=cognito.UserPool(
            self,
            "AgentUserPool",
            user_pool_name="agent-ia-users",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=False,
                require_digits=True,
                require_symbols=False,
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.DESTROY, # en dev :cdk destroy supprime aussi les comptes
        )


        # App Client "public" : PAS de secret. Notre appelant est le process
        # Streamlit (UI.py) qui appelle l'API Cognito directement via boto3
        # (pas de Hosted UI, pas de redirection OAuth) -> generate_secret=False
        # évite d'avoir à calculer un SECRET_HASH HMAC à chaque appel.
        # auth_flows.user_password=True active USER_PASSWORD_AUTH, désactivé
        # par défaut sur un nouveau client : sans ça, InitiateAuth échoue.

        user_pool_client= user_pool.add_client(
            "AgentUserPoolClient",
            user_pool_client_name="agent-ia-streamlit-client",
            generate_secret=False,
            auth_flows=cognito.AuthFlow(
                user_password=True,
                user_srp=True,
            ),
            access_token_validity=Duration.minutes(60),
            id_token_validity=Duration.minutes(60),
            refresh_token_validity=Duration.days(30) # durée de la reconnexion "silencieuse"
        )
        CfnOutput(self,"cognito_user_poll_id",value=user_pool.user_pool_id)
        CfnOutput(self,"cognito_client_id",value=user_pool_client.user_pool_client_id)


        ### l'Agent lambda

        agent_lambda = lambda_.DockerImageFunction(
            self,
            "AgentLambda",

            code=lambda_.DockerImageCode.from_image_asset(
                directory="lambda"
            ),

            timeout=Duration.seconds(60),

            memory_size=3008,

            environment={
                "TABLE_NAME": agent_memory_table.table_name,
                "OPENSEARCH_ENDPOINT": vector_collection.attr_collection_endpoint,
                "TAVILY_API_KEY": os.getenv("TAVILY_API_KEY", ""),
                "AWS_LWA_INVOKE_MODE": "RESPONSE_STREAM",
                "RATE_LIMIT_TABLE_NAME": rate_limit_table.table_name,
                "API_KEYS_TABLE_NAME": api_keys_table.table_name,
                "COGNITO_USER_POOL_ID":user_pool.user_pool_id,
                "COGNITO_CLIENT_ID":user_pool_client.user_pool_client_id,
                "CONVERSATIONS_INDEX_TABLE_NAME":conversations_index_table.table_name,
                "KNOWLEDGE_BUCKET_NAME": knowledge_bucket.bucket_name,
            }
        )

        # fn_url = lambda_.FunctionUrl(
        #     self,
        #     "AgentFunctionUrl",
        #     function=agent_lambda,
        #     auth_type=lambda_.FunctionUrlAuthType.NONE,  # doit etre obligatoirement en NONE si on veut du stream sse .
        #     invoke_mode=lambda_.InvokeMode.RESPONSE_STREAM
        # )

        # # Politique de ressource explicite autorisant l'invocation PUBLIQUE
        # # de la Function URL. Indispensable avec AuthType.NONE : CDK ne
        # # l'ajoute PAS automatiquement quand on construit `FunctionUrl(...)`
        # # directement (contrairement à `agent_lambda.add_function_url(...)`,
        # # qui gère ça tout seul). Sans cette permission, AWS répond 403
        # # "Forbidden" avant même que le code Python de server.py ne soit
        # # exécuté — la sécurité applicative (x-api-key + token Cognito)
        # # n'a alors jamais l'occasion de s'appliquer.
        # agent_lambda.add_permission(
        #     "PublicInvokeFunctionUrl",
        #     principal=iam.AnyPrincipal(),
        #     action=["lambda:InvokeFunctionUrl","lambda:InvokeFunction"],
        #     function_url_auth_type=lambda_.FunctionUrlAuthType.NONE,
        # )

        fn_url = agent_lambda.add_function_url(
            auth_type=lambda_.FunctionUrlAuthType.NONE,
            invoke_mode=lambda_.InvokeMode.RESPONSE_STREAM,
        )

        CfnOutput(self, "agent_lambda", value=fn_url.url)

        # Permission pour le compteur de rate limiting (lecture + écriture,
        # UpdateItem uniquement en pratique, cf. rate_limit_service.py)
        rate_limit_table.grant_read_write_data(agent_lambda)

        # Lecture seule sur les clés API : le Lambda ne fait que vérifier,
        # jamais créer/révoquer (ça se fait hors déploiement).
        api_keys_table.grant_read_data(agent_lambda)


        # NOTE sur Cognito : le Lambda n'a besoin d'AUCUNE permission IAM
        # particulière sur le User Pool. La vérification du token côté
        # server.py se fait par cryptographie pure (signature JWT contre les
        # clés publiques JWKS, récupérées via une simple requête HTTPS), pas
        # via un appel d'API Cognito authentifié. C'est volontaire : ça évite
        # un appel réseau à Cognito à chaque requête entrante.


###Access Policy : C'est elle qui autorise Lambda.

        access_policy= aoss.CfnAccessPolicy(
            self,
            "VectorAccessPolicy",
            name="vector-access-policy",
            type="data",
            policy=json.dumps([
                {
                    "Rules":[
                        {
                            "Resource":[
                                "collection/agent-memory"
                            ],
                            "Permission":[
                                "aoss:*"
                            ],
                            "ResourceType":"collection"
                        },
                        {
                            "Resource":[
                                "index/agent-memory/conversation-memory",
                                "index/agent-memory/document-memory"
                            ],
                            "Permission":[
                                "aoss:*"
                            ],
                            "ResourceType":"index"
                        }
                    ],
                    "Principal":[
                        agent_lambda.role.role_arn,
                        current_user_arn
                    ]
                }
            ])
        )


        ## role iam attribué à lambda pour les policy bedrock

        # Dans aws_ai_agent_stack.py - Ajouter ces permissions
        agent_lambda.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                    "bedrock:Converse",
                    "bedrock:ConverseStream",
                  
                    "aoss:APIAccessAll",
                    # Permissions DynamoDB
                    "dynamodb:Query",
                    "dynamodb:Scan",
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:DeleteItem",
                    "dynamodb:BatchWriteItem",
                ],
                resources=["*"]  # À restreindre en production
            )
        )

        CfnOutput( ## Valeur de retour de l'infrastructure
            self,
            "CollectionEndpoint",
            value=vector_collection.attr_collection_endpoint
        )

##### role iam pour le modele Nova
        agent_lambda.add_to_role_policy(
            iam.PolicyStatement(
                sid="AllowInvokeModels",
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                    "bedrock:Converse",
                    "bedrock:ConverseStream"
                ],
                # resources=[
                #     "arn:aws:bedrock:*::foundation-model/*",     # ← Autorise TOUS les modèles de base
                #     f"arn:aws:bedrock:*:{Stack.account}:inference-profile/*"  # ← Autorise TOUS les profils
                # ]
                resources=[
                    # Pour les inference profiles (cross-region)
                    "arn:aws:bedrock:*:*:inference-profile/*",
                    
                    # Pour les foundation models (direct)
                    "arn:aws:bedrock:*:*:foundation-model/*"
                ]
            )
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
        

        lambda_integration = ( # connecte apigetway à lambda 
            apigateway.LambdaIntegration(
                agent_lambda,
                proxy=True,  # ← Important pour le streaming !
                # Pour le streaming, ajoute ces options :
                request_parameters={
                    "integration.request.header.Content-Type": "'text/event-stream'"
                }
            )
        )

        agent_resource = (api.root.add_resource(
            "agent"    ### racine des urls
        )
        )

        ## Post agent/documents
        documents_resource = agent_resource.add_resource(
            "documents"
        )

        documents_resource.add_method(
            "POST",
            lambda_integration,
            api_key_required=True,
        )

        ##### créer  POST : /agent/chat

        chat_resource = (
            agent_resource.add_resource(
                "chat"
            )
        )
        # chat_resource.add_method(
        #     "POST",
        #     lambda_integration
        # )

        # ===== AJOUTER CETTE ROUTE POUR LE STREAMING =====
        stream_chat_resource = (
           chat_resource.add_resource(
               "stream"
           )
        )
        stream_chat_resource.add_method(
            "POST",
            lambda_integration,  # Utilise la même intégration Lambda
            api_key_required=True,  # Sécurise l'API : header x-api-key obligatoire
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

            lambda_integration,
            api_key_required=True,  # Sécurise l'API : header x-api-key obligatoire
        )

        ## Sécurisation de l'API : clé API + UsagePlan
        #
        # Le UsagePlan est OBLIGATOIRE pour qu'une clé associée à une méthode
        # `api_key_required=True` soit acceptée par API Gateway (sinon 403
        # "Forbidden" même avec une clé valide). Le throttle ici est une
        # limite "plafond" côté API Gateway (en req/s, réglage natif) — la
        # vraie limite métier "100 req/min par clé" est appliquée dans le
        # Lambda (services/rate_limit_service.py), qui raisonne en fenêtre
        # de 60s exacte. Le throttle API Gateway agit comme filet de
        # sécurité supplémentaire contre les pics/abus, réglé large pour ne
        # pas entrer en conflit avec la limite applicative.
        api_key = apigateway.ApiKey(
            self,
            "AgentApiKey",
            api_key_name="agent-api-key",
            description="Clé API pour l'agent IA (header x-api-key requis).",
        )

        usage_plan = apigateway.UsagePlan(
            self,
            "AgentUsagePlan",
            name="agent-usage-plan",
            throttle=apigateway.ThrottleSettings(
                rate_limit=10,   # req/s en régime stable (>> 100/min réparti dans le temps)
                burst_limit=20,  # pic instantané toléré
            ),
            api_stages=[
                apigateway.UsagePlanPerApiStage(
                    api=api,
                    stage=api.deployment_stage,
                )
            ],
        )
        usage_plan.add_api_key(api_key)

        CfnOutput(self, "agent_api_key_id", value=api_key.key_id)



        

        agent_memory_table.grant_read_write_data(  # peut interroger , lire et ecrire
            agent_lambda
        )

        ### Permissions lambda sur dynamodb

        knowledge_bucket.grant_read_write(  # lambda peut juste lire
            agent_lambda
        )
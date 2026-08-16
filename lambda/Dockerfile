# Utiliser Alpine pour une image plus légère
FROM public.ecr.aws/docker/library/python:3.12-alpine

# AWS Lambda Web Adapter
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.1 /lambda-adapter /opt/extensions/lambda-adapter

ENV PORT=8000
ENV AWS_LWA_INVOKE_MODE=RESPONSE_STREAM
ENV AWS_LWA_READINESS_CHECK_PATH=/health
ENV PYTHONUNBUFFERED=1

WORKDIR /var/task

# Installer les dépendances système minimales
RUN apk add --no-cache gcc musl-dev

# Installer les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=600 -r requirements.txt

# Nettoyer
RUN find /usr/local/lib/python3.12/site-packages -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true && \
    find /usr/local/lib/python3.12/site-packages -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

COPY . .

CMD ["python", "-c", "from server import run_server; run_server()"]








# FROM public.ecr.aws/docker/library/python:3.12-slim-bullseye

# # AWS Lambda Web Adapter
# COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.1 /lambda-adapter /opt/extensions/lambda-adapter

# # Environnement
# ENV PORT=8000
# ENV AWS_LWA_INVOKE_MODE=RESPONSE_STREAM
# ENV AWS_LWA_READINESS_CHECK_PATH=/health
# ENV PYTHONUNBUFFERED=1
# ENV PIP_DEFAULT_TIMEOUT=300
# ENV PIP_NO_CACHE_DIR=1

# WORKDIR /var/task

# # Installer les dépendances système nécessaires (réduit)
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     gcc \
#     && rm -rf /var/lib/apt/lists/*

# # Copier et installer les dépendances Python
# COPY requirements.txt .
# RUN pip install --no-cache-dir --default-timeout=300 \
#     -r requirements.txt

# # Nettoyer les fichiers inutiles pour réduire la taille
# RUN find /usr/local/lib/python3.12/site-packages -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true && \
#     find /usr/local/lib/python3.12/site-packages -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true && \
#     find /usr/local/lib/python3.12/site-packages -type f -name "*.pyc" -delete 2>/dev/null || true

# # Copier le code APRÈS les dépendances (meilleur caching Docker)
# COPY . .

# # Commande
# CMD ["python", "-c", "from server import run_server; run_server()"]










# FROM public.ecr.aws/docker/library/python:3.12-slim-bullseye

# # AWS Lambda Web Adapter
# COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.1 /lambda-adapter /opt/extensions/lambda-adapter

# # Environnement
# ENV PORT=8000
# ENV AWS_LWA_INVOKE_MODE=RESPONSE_STREAM
# ENV AWS_LWA_READINESS_CHECK_PATH=/health
# ENV PYTHONUNBUFFERED=1

# WORKDIR /var/task

# # Installation des dépendances
# COPY requirements.txt .
# RUN pip install --no-cache-dir --default-timeout=300 -r requirements.txt 
# # && \
# #     # Nettoyage
# #     rm -rf /var/lang/lib/python3.12/site-packages/pip \
# #            /var/lang/lib/python3.12/site-packages/setuptools \
# #            /var/lang/lib/python3.12/site-packages/wheel && \
# #     find /var/lang/lib/python3.12/site-packages -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true && \
# #     find /var/lang/lib/python3.12/site-packages -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# # Copie du code
# COPY . .

# # Commande : lance le serveur HTTP minimaliste
# CMD ["python", "-c", "from server import run_server; run_server()"]






# FROM public.ecr.aws/lambda/python:3.12

# COPY requirements.txt .

# RUN pip install --no-cache-dir -r requirements.txt && \
#     # Supprime pip/setuptools/wheel de l'image finale (inutiles en runtime)
#     rm -rf /var/lang/lib/python3.12/site-packages/pip \
#            /var/lang/lib/python3.12/site-packages/setuptools \
#            /var/lang/lib/python3.12/site-packages/wheel && \
#     # Supprime les fichiers de test et caches
#     find /var/lang/lib/python3.12/site-packages -type d -name "tests" -exec rm -rf {} + 2>/dev/null; \
#     find /var/lang/lib/python3.12/site-packages -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; \
#     # Réduit botocore aux services réellement utilisés
#     python3 -c "\
# import os, shutil, botocore; \
# data_dir = os.path.join(os.path.dirname(botocore.__file__), 'data'); \
# keep = {'bedrock-runtime','bedrock','dynamodb','s3','sts','_retry.json','endpoints.json','partitions.json','sdk-default-configuration.json'}; \
# [shutil.rmtree(os.path.join(data_dir, d)) for d in os.listdir(data_dir) if d not in keep and os.path.isdir(os.path.join(data_dir, d))]"

# COPY . .

# CMD ["agent_handler.lambda_handler"]

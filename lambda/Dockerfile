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









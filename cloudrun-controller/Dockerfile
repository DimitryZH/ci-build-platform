# -------- Terraform stage --------
FROM hashicorp/terraform:1.7.5 AS terraform

# -------- Runtime stage --------
FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Copy terraform binary only
COPY --from=terraform /bin/terraform /usr/local/bin/terraform

WORKDIR /workspace

COPY cloudrun-controller/app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY cloudrun-controller/app ./app
COPY terraform ./terraform
COPY runner ./runner

CMD ["python", "/workspace/app/app.py"]

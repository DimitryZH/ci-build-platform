FROM hashicorp/terraform:1.7.5

RUN apk add --no-cache python3 py3-pip bash curl

WORKDIR /workspace

# Install controller dependencies
COPY cloudrun-controller/app/requirements.txt ./requirements.txt
RUN pip3 install -r requirements.txt

# Copy controller application code
COPY cloudrun-controller/app /workspace/app

# Copy Terraform configuration (root terraform directory)
COPY terraform /workspace/terraform

ENV PYTHONUNBUFFERED=1

CMD ["python3", "/workspace/app/app.py"]

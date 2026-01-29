FROM hashicorp/terraform:1.7.5

RUN apk add --no-cache python3 py3-pip bash curl

WORKDIR /workspace

COPY requirements.txt .
RUN pip3 install -r requirements.txt

COPY app.py /workspace/app.py
COPY terraform /workspace/terraform

ENV PYTHONUNBUFFERED=1

CMD ["python3", "/workspace/app.py"]

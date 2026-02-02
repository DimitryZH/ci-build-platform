FROM python:3.11-slim

WORKDIR /app

# Install Python dependencies from pinned requirements
COPY src/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY src/ .

CMD ["python", "main.py"]

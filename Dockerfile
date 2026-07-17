FROM python:3.11-slim

WORKDIR /app
RUN apt-get update && apt-get install -y curl libpq5 && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN npm install -g hyperframes && hyperframes --version

COPY src/ ./src/
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]

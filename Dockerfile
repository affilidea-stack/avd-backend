# Dockerfile per Render
FROM python:3.11-slim

# (facoltativo ma utile per alcuni provider)
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# 🔴 Fondamentale: usa la porta fornita da Render
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT}"]

# Dockerfile per Render
FROM python:3.11-slim

# opzionale ma utile: ffmpeg per casi particolari
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# 🔴 IMPORTANTE: usa la porta che Render mette in $PORT
# (niente EXPOSE/ENV fissi; Render gestisce il routing)
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT}"]


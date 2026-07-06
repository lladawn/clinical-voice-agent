# Build from the repo root:  docker build -f agent/Dockerfile .
FROM python:3.11-slim

WORKDIR /app

# System deps some audio/ML wheels expect at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent/ ./agent/
COPY data/ ./data/

# Pre-download plugin model files (e.g. Silero VAD) so the first call is fast.
RUN python -m agent.main download-files || true

CMD ["python", "-m", "agent.main", "start"]

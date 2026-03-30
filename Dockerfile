FROM python:3.11-slim

WORKDIR /app

# System deps for audio libs (numpy, sounddevice headers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    libportaudio2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create data dir for SQLite
RUN mkdir -p data

EXPOSE 8088

CMD ["python", "main.py"]

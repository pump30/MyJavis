FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

# Install Python deps — skip audio/ML packages that won't work in container
# (sounddevice, openwakeword, faster-whisper, pyttsx3, edge-tts, yt-dlp)
# The app gracefully falls back to text-only mode without them.
RUN grep -v -E '^#|^$|sounddevice|openwakeword|faster-whisper|pyttsx3|edge-tts|yt-dlp' requirements.txt > /tmp/reqs.txt \
    && pip install --no-cache-dir -r /tmp/reqs.txt

COPY . .

# Create data directory for persistent memory storage
RUN mkdir -p data/memory

EXPOSE 8088

CMD ["python", "main.py"]

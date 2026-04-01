FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

# Install Python deps — skip audio/ML packages that need system audio libs
# (sounddevice, openwakeword, faster-whisper, pyttsx3)
# edge-tts and yt-dlp are pure Python and work fine in containers.
RUN grep -v -E '^#|^$|sounddevice|openwakeword|faster-whisper|pyttsx3' requirements.txt > /tmp/reqs.txt \
    && pip install --no-cache-dir -r /tmp/reqs.txt

COPY . .

# Create data directory for persistent memory storage
RUN mkdir -p data/memory

EXPOSE 8088

CMD ["python", "main.py"]

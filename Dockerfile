# AdaptiBoard - board + controller + server in one container (Render, Hugging Face, Koyeb, any Docker host).
# PRIVATE_ROOMS=1: every visitor gets their own board (mouse / keyboard control, in-memory learning).
# The EEG decoder is NOT in here. To use a headset with the hosted app, open the board with
# ?room=myroom and run:  python eeg/decoder.py --server https://<app-url> --room myroom --port <serial port>

# 1) build the React app
FROM node:20-slim AS web
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# 2) Python server that serves the built app + WebSockets + AI endpoints
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PORT=8000 PRIVATE_ROOMS=1
COPY server/requirements.txt server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt
COPY server/ server/
COPY --from=web /app/web/dist web/dist
EXPOSE 8000
# API keys (GROQ_API_KEY, ...) come from the host's environment-variable settings, never from the image.
CMD ["sh", "-c", "python server/main.py --host 0.0.0.0 --port ${PORT}"]

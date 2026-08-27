FROM node:22-bookworm-slim
ARG CODEX_VERSION=0.150.0
RUN apt-get update && apt-get install -y --no-install-recommends git python3 ca-certificates \
 && npm install -g "@openai/codex@${CODEX_VERSION}" && rm -rf /var/lib/apt/lists/* \
 && useradd --uid 10001 --home-dir /home/codex codex
COPY harness /opt/harness
USER 10001:10001
ENTRYPOINT ["python3", "/opt/harness/entrypoint.py"]

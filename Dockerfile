# ZeroProof — zero-token, proof-carrying routing agent (Track 1).
# Target platform: linux/amd64, CPU-only. Final image ~1.6 GB (<< 5 GB limit).
# Nothing is downloaded at runtime: the model is baked in at build time.
FROM --platform=linux/amd64 python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ZP_MODEL_PATH=/models/model.gguf \
    ZP_N_THREADS=2 \
    PYTHONPATH=/app/src

WORKDIR /app

# --- System deps: only curl+ca-certificates for the build-time model fetch. ---
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# --- Python deps (prebuilt CPU wheel for llama-cpp-python: no compiler needed). ---
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
        --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu \
 && pip install --no-cache-dir \
        https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl

# --- Bake the local model into the image at BUILD time (never at runtime). ---
ARG MODEL_URL="https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"
ARG MODEL_SHA256=""
COPY scripts/fetch_model.sh /app/scripts/fetch_model.sh
RUN chmod +x /app/scripts/fetch_model.sh \
 && MODEL_URL="${MODEL_URL}" MODEL_SHA256="${MODEL_SHA256}" bash /app/scripts/fetch_model.sh /models/model.gguf

# --- Application code ---
COPY src/ /app/src/
COPY config/ /app/config/
COPY LICENSE NOTICE /app/
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Pre-warm spaCy so the model is validated in-image (helps < 60s readiness).
RUN python -c "import spacy; spacy.load('en_core_web_sm'); print('spaCy OK')"

# Sanity: the agent imports cleanly.
RUN python -c "import sys; sys.path.insert(0,'/app/src'); import zeroproof.main; print('ZeroProof import OK')"

ENTRYPOINT ["/app/entrypoint.sh"]

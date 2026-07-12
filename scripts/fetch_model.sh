#!/usr/bin/env bash
# Download the bundled local model at BUILD time (never at runtime).
#
# Default: Qwen2.5-1.5B-Instruct, Q4_K_M GGUF — Apache-2.0 licensed and
# redistributable, ~1.1 GB, comfortably fits the 4 GB / 2 vCPU grader.
#
# Override MODEL_URL / OUT to bake a different license-clean GGUF (e.g. the
# ~3B bake-off challenger). See PROJECT.md for the model bake-off notes.
set -euo pipefail

OUT="${1:-/models/model.gguf}"
MODEL_URL="${MODEL_URL:-https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf}"
EXPECTED_SHA256="${MODEL_SHA256:-}"   # optional integrity pin

mkdir -p "$(dirname "$OUT")"
echo "[fetch_model] downloading model into ${OUT}"
echo "[fetch_model] source: ${MODEL_URL}"

download() {
  if command -v curl >/dev/null 2>&1; then
    curl -fL --retry 5 --retry-delay 4 --retry-all-errors -o "$OUT" "$MODEL_URL"
  elif command -v wget >/dev/null 2>&1; then
    wget -t 5 -w 4 -O "$OUT" "$MODEL_URL"
  else
    echo "[fetch_model] ERROR: neither curl nor wget available" >&2
    exit 1
  fi
}

attempt=0
until download; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 4 ]; then
    echo "[fetch_model] ERROR: download failed after ${attempt} attempts" >&2
    exit 1
  fi
  echo "[fetch_model] retrying (${attempt})..."
  sleep $((attempt * 4))
done

BYTES=$(wc -c < "$OUT")
echo "[fetch_model] downloaded ${BYTES} bytes"
if [ "$BYTES" -lt 100000000 ]; then
  echo "[fetch_model] ERROR: file too small (${BYTES} bytes); likely an error page" >&2
  exit 1
fi

if [ -n "$EXPECTED_SHA256" ]; then
  echo "[fetch_model] verifying sha256"
  echo "${EXPECTED_SHA256}  ${OUT}" | sha256sum -c -
fi

echo "[fetch_model] OK"

#!/bin/sh
# Server start (Docker, e.g. on Render): fill an empty database from AFAQ_SEED_URL once,
# then serve. --proxy-headers: behind the host's proxy, the reader's address comes from
# X-Forwarded-For, so the per-reader limits of the AI section count each reader apart.
set -e
python -m app.seed
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'

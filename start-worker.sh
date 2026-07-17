#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

exec conda run --no-capture-output -n perfume-video \
  celery -A src.tasks.celery_app worker --loglevel=info --concurrency=2 -Q perfume-video

#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

exec conda run --no-capture-output -n perfume-video \
  celery -A src.tasks.celery_app beat --loglevel=info

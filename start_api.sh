#!/bin/bash

cd /home/server/server || exit 1

exec /home/server/.local/bin/uvicorn main:app \
  --host 0.0.0.0 \
  --port 8000
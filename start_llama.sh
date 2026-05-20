#!/bin/bash

exec llama-server \
  -m /home/server/models/Qwen3.5-4B-Q4_0.gguf \
  -ngl 99 \
  --flash-attn 1 \
  -ctk f16 \
  -ctv f16 \
  -c 4096 \
  -b 512 \
  -ub 512 \
  --threads 4 \
  -np 1 \
  --host 0.0.0.0 \
  --port 8080 \
  --temp 0.7 \
  --top-p 0.8 \
  --reasoning off \
  --jinja \
  --no-mmap \
  --chat-template-kwargs '{"enable_thinking":false}' \
  --kv-unified

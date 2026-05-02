#!/bin/bash

exec llama-server \
  -m /home/server/models/Qwen_Qwen3.5-4B-Q4_K_L.gguf \
  --port 8080 \
  -ngl 99 \
  --flash-attn on \
  --ctx-size 8192 \
  --cache-type-k q8_0 \
  --cache-type-v q8_0 \
  --threads 6 \
  --temp 0.2 \
  --top-p 0.1 \
  --top-k 20 \
  --alias Rytle \
  --cache-ram 1024 \
  --reasoning off \
  --context-shift \
  --cont-batching \
  --verbosity 3 \
  --parallel 1

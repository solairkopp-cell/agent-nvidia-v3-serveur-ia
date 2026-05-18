#!/bin/bash

exec llama-server \
  -m /home/server/models/Qwen_Qwen3.5-4B-Q4_K_L.gguf \
  --port 8080 \
  -ngl 99 \
  --flash-attn on \
  --ctx-size 4096 \
  --cache-type-k f16 \
  --cache-type-v f16 \
  --threads 2 \
  --temp 0.0 \
  --top-p 0.1 \
  --alias Rytle \
  --reasoning off \
  --jinja \
  --presence-penalty 1.5 \
  --parallel 1

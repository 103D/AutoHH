#!/bin/bash
# Cline Free через OpenRouter — бесплатный резерв и простые задачи.
# Для: fallback, второе мнение, простые задачи.

cd /home/user/Projects/AtoHH
export OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-}"
exec hermes \
  --provider openrouter \
  --model openai/gpt-4o-mini \
  --in . \
  "$@"

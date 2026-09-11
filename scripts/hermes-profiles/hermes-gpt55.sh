#!/bin/bash
# GPT-5.5 / Codex — основной high-intelligence профиль.
# Для: архитектура, debugging, сложный refactoring, анализ, финальная проверка.

cd /home/user/Projects/AtoHH
exec hermes \
  --provider openai-codex \
  --model gpt-5.5 \
  "$@"

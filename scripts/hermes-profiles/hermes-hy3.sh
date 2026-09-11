#!/bin/bash
# HY3 через OmniRoute — дешёвый/быстрый исполнитель.
# Для: тесты, lint, CRUD, небольшие исправления, документация, mass tasks.

cd /home/user/Projects/AtoHH
export AI_API_KEY="${AI_API_KEY:-}"
exec hermes \
  --provider custom \
  --model oc/hy3-free \
  --in . \
  "$@"

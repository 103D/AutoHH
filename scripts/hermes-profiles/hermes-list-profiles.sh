#!/bin/bash
# Показать доступные профили Hermes и способы их использования.

cd /home/user/Projects/AtoHH

echo "=== Hermes Agent Profiles — AutoHH ==="
echo ""
echo "Основной профиль (по умолчанию):"
echo "  GPT-5.5 / Codex"
echo "  Для: архитектура, debugging, сложный refactoring, анализ, финальная проверка"
echo "  Запуск: hermes chat --in /home/user/Projects/AtoHH"
echo ""
echo "Профиль HY3 (OmniRoute):"
echo "  oc/hy3-free через http://localhost:20128/v1"
echo "  Для: тесты, lint, CRUD, небольшие исправления, документация"
echo "  Запуск: ./scripts/hermes-profiles/hermes-hy3.sh chat --in ."
echo ""
echo "Профиль Cline Free (OpenRouter):"
echo "  openai/gpt-4o-mini через https://openrouter.ai/api/v1"
echo "  Для: бесплатный fallback, второе мнение, простые задачи"
echo "  Запуск: ./scripts/hermes-profiles/hermes-free.sh chat --in ."
echo ""
echo "Fallback chain:"
echo "  Если GPT-5.5 недоступна → HY3 → Cline Free"
echo ""
echo "Проверка конфигурации:"
echo "  hermes config show"
echo "  hermes fallback list"

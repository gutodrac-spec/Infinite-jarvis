#!/usr/bin/env bash
# Instala tudo (roda uma vez quando o Codespace é criado).
set -euo pipefail
cd "$(dirname "$0")/.."
pip install --user -r requirements.txt
npm --prefix whatsapp ci || npm --prefix whatsapp install
npm install -g @anthropic-ai/claude-code
[ -f .env ] || cp .env.example .env
echo "Pronto. Preencha o .env (ou os secrets do Codespaces) e rode: bash scripts/start.sh"

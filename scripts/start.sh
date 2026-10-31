#!/usr/bin/env bash
# Sobe o Jarvis (servidor Python + ponte WhatsApp) em segundo plano, reiniciando se cair.
#   bash scripts/start.sh          inicia (ou reinicia)
#   bash scripts/start.sh stop     para
#   tail -f logs/*.log             acompanha (o QR code do WhatsApp aparece em logs/whatsapp.log)
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs .jarvis_state

stop() {  # cada serviço roda na própria sessão (setsid): mata o grupo inteiro
  [ -f .jarvis_state/pids ] && for pid in $(cat .jarvis_state/pids); do kill -- "-$pid" 2>/dev/null; done
  rm -f .jarvis_state/pids
}

if [ "${1:-}" = "stop" ]; then stop; echo "Jarvis parado."; exit 0; fi
stop

set -a; [ -f .env ] && . ./.env; set +a
# Segredo compartilhado entre os processos; gerado uma vez e guardado.
if [ -z "${JARVIS_SECRET:-}" ]; then
  [ -f .jarvis_state/secret ] || python3 -c "import secrets; print(secrets.token_urlsafe(32))" > .jarvis_state/secret
  export JARVIS_SECRET="$(cat .jarvis_state/secret)"
fi

forever() {  # forever <nome> <comando...>
  local name=$1; shift
  while true; do
    echo "[$(date '+%F %T')] iniciando $name" >> "logs/$name.log"
    "$@" >> "logs/$name.log" 2>&1
    echo "[$(date '+%F %T')] $name caiu (código $?); reiniciando em 5s" >> "logs/$name.log"
    sleep 5
  done
}

launch() {  # launch <nome> <comando...>: sessão própria; o PID do líder vai para .jarvis_state/pids
  setsid bash -c "echo \$\$ >> .jarvis_state/pids; $(declare -f forever); forever $*" < /dev/null > /dev/null 2>&1 &
}

launch jarvis python3 -m jarvis serve
[ "${WHATSAPP_PROVIDER:-baileys}" = "baileys" ] && launch whatsapp node whatsapp/index.js

# No Codespaces, a porta 8000 precisa ser pública para Twilio e ElevenLabs alcançarem os webhooks.
if [ -n "${CODESPACE_NAME:-}" ]; then
  (sleep 8; gh codespace ports visibility 8000:public -c "$CODESPACE_NAME" >> logs/jarvis.log 2>&1 \
     || echo "Torne a porta 8000 pública na aba PORTS (botão direito > Port Visibility > Public)" >> logs/jarvis.log) &
  echo "URL pública: https://${CODESPACE_NAME}-8000.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
fi
echo "Jarvis rodando em segundo plano. Logs: tail -f logs/*.log"

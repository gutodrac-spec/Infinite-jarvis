"""Iniciativa própria: de tempos em tempos o Jarvis acorda, olha tudo e decide se precisa falar com você."""
import asyncio
import json
import logging
from datetime import datetime

from . import brain, memory, monitor
from .config import config

log = logging.getLogger("jarvis.heartbeat")

NOTHING = "NADA"


def is_quiet_hours(hour: int) -> bool:
    start, end = config.quiet_start, config.quiet_end
    return start <= hour or hour < end if start > end else start <= hour < end


def build_prompt(now: datetime, snap: dict, alerts: list[str]) -> str:
    quiet = is_quiet_hours(now.hour)
    return f"""[CICLO AUTÔNOMO — {now:%A %d/%m/%Y %H:%M}]

Estado do computador:
{json.dumps(snap, ensure_ascii=False, indent=2)}

Alertas automáticos: {", ".join(alerts) if alerts else "nenhum"}
Horário de silêncio: {"SIM — só ligue se for realmente urgente" if quiet else "não"}

Faça sua ronda:
1. Leia `Jarvis/Lembretes.md` e veja se algo venceu ou vence nos próximos {config.heartbeat_minutes} minutos.
2. Leia `Jarvis/Rotina.md` e veja se há alguma checagem programada para agora.
3. Avalie o estado do computador e os alertas.
4. Decida: precisa avisar o dono? Use `send_whatsapp` para avisos normais e `call_owner` só para urgências
   ou lembretes que ele pediu por ligação. Não repita avisos que já constam em `Jarvis/Avisos.md`.
5. Se avisou, registre em `Jarvis/Avisos.md` (data/hora + o quê) e marque lembretes concluídos.

Se não houver nada relevante, não use nenhuma ferramenta de contato e responda só: {NOTHING}"""


async def tick() -> str:
    now = datetime.now()
    snap = monitor.snapshot()
    result = await brain.ask(build_prompt(now, snap, monitor.alerts(snap)), channel="heartbeat", session="ronda")
    if result and result != NOTHING:
        memory.log_exchange("ronda", "Jarvis", result)
    return result


async def run_forever() -> None:
    if config.heartbeat_minutes <= 0:
        log.info("Heartbeat desligado (HEARTBEAT_MINUTES=0)")
        return
    while True:
        try:
            log.info("Ronda: %s", await tick())
        except Exception:
            log.exception("Erro na ronda autônoma")
        await asyncio.sleep(config.heartbeat_minutes * 60)

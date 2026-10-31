"""Cérebro: cada mensagem vira uma conversa com o Claude Code rodando dentro do vault do Obsidian."""
import asyncio
import logging
import re

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

from . import memory
from .config import config
from .tools import TOOL_NAMES, server

log = logging.getLogger("jarvis.brain")

# Ferramentas pré-aprovadas. Como não tem ninguém para clicar em "permitir",
# o modo dontAsk nega qualquer coisa fora desta lista.
ALLOWED_TOOLS = ["Read", "Write", "Edit", "Glob", "Grep", "Bash", "WebSearch", "WebFetch", *TOOL_NAMES]

CHANNEL_HINTS = {
    "whatsapp": "Resposta vai por WhatsApp: seja direto, pode usar emojis com moderação.",
    "voice": "Resposta será FALADA numa ligação: frases curtas, sem markdown, sem listas, sem emojis. "
    "Se o dono se despedir ou encerrar a conversa, termine a resposta com [FIM].",
    "heartbeat": "Ninguém está falando com você. Este é seu ciclo autônomo.",
}

_locks: dict[str, asyncio.Lock] = {}


def speakable(text: str) -> str:
    """Remove emojis e marcação que a voz leria em voz alta."""
    text = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]", "", text)
    return re.sub(r"[*_#`>]", "", text).strip()


async def ask(prompt: str, channel: str, session: str = "conversa") -> str:
    """Envia `prompt` ao Claude Code e retorna o texto final. Sessões nomeadas mantêm o contexto entre mensagens."""
    lock = _locks.setdefault(session, asyncio.Lock())
    async with lock:
        options = ClaudeAgentOptions(
            cwd=str(config.vault_path),
            setting_sources=["project"],  # carrega vault/CLAUDE.md (a "personalidade" e regras de memória)
            system_prompt={
                "type": "preset",
                "preset": "claude_code",
                "append": f"Canal atual: {channel}. {CHANNEL_HINTS.get(channel, '')} O dono se chama {config.owner_name}.",
            },
            allowed_tools=ALLOWED_TOOLS,
            permission_mode="dontAsk",
            mcp_servers={"jarvis": server},
            resume=memory.get_session(session),
            max_turns=config.max_turns,
            model=config.model or None,
        )
        reply = ""
        try:
            async for msg in query(prompt=prompt, options=options):
                if isinstance(msg, ResultMessage):
                    memory.save_session(session, msg.session_id)
                    reply = msg.result or ""
        except Exception:
            log.exception("Falha ao consultar o Claude Code")
            return "Desculpe, tive um problema para pensar agora. Tente de novo em instantes."
        return reply.strip()

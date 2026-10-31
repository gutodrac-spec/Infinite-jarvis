"""Ferramentas extras que o Claude Code pode usar além de ler/escrever arquivos e rodar comandos."""
import json

from claude_agent_sdk import create_sdk_mcp_server, tool

from . import comms, monitor


def _text(s: str) -> dict:
    return {"content": [{"type": "text", "text": s}]}


@tool("send_whatsapp", "Envia uma mensagem de WhatsApp para o dono.", {"text": str})
async def send_whatsapp(args: dict) -> dict:
    return _text(comms.send_whatsapp(args["text"]))


@tool(
    "call_owner",
    "Liga para o celular do dono e fala a mensagem em voz alta. Use só quando for importante ou urgente.",
    {"message": str},
)
async def call_owner(args: dict) -> dict:
    return _text(comms.call_owner(args["message"]))


@tool("system_status", "Retorna CPU, memória, disco, bateria e processos do computador.", {})
async def system_status(args: dict) -> dict:
    snap = monitor.snapshot()
    return _text(json.dumps({"snapshot": snap, "alerts": monitor.alerts(snap)}, ensure_ascii=False))


server = create_sdk_mcp_server("jarvis", tools=[send_whatsapp, call_owner, system_status])
TOOL_NAMES = ["mcp__jarvis__send_whatsapp", "mcp__jarvis__call_owner", "mcp__jarvis__system_status"]

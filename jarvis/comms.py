"""Boca do Jarvis: WhatsApp e ligações via Twilio, com limite de frequência para não virar spam."""
import time
from collections import deque
from xml.sax.saxutils import escape

import httpx
from twilio.rest import Client

from .config import config

_client: Client | None = None
_sent_messages: deque[float] = deque()
_sent_calls: deque[float] = deque()


def client() -> Client:
    global _client
    if _client is None:
        _client = Client(config.twilio_sid, config.twilio_token)
    return _client


def _allow(history: deque[float], limit: int) -> bool:
    now = time.time()
    while history and now - history[0] > 3600:
        history.popleft()
    if len(history) >= limit:
        return False
    history.append(now)
    return True


def send_whatsapp(text: str) -> str:
    if not _allow(_sent_messages, config.max_messages_per_hour):
        return "Limite de mensagens por hora atingido; mensagem não enviada."
    if config.whatsapp_provider == "baileys":
        r = httpx.post(f"{config.baileys_url}/send", json={"text": text}, headers={"x-jarvis-secret": config.secret}, timeout=30)
        return "Mensagem enviada." if r.status_code == 200 else f"Falha no WhatsApp (Baileys): {r.text}"
    # WhatsApp aceita até 1600 caracteres por mensagem via Twilio
    for i in range(0, len(text), 1500):
        client().messages.create(from_=config.twilio_whatsapp, to=config.owner_whatsapp, body=text[i : i + 1500])
    return "Mensagem enviada."


def say_and_listen_twiml(text: str) -> str:
    """TwiML que fala `text` e depois escuta a resposta do dono."""
    return (
        "<Response>"
        f'<Say voice="{config.voice_name}" language="{config.voice_language}">{escape(text)}</Say>'
        f'<Gather input="speech" language="{config.voice_language}" speechTimeout="auto" '
        f'action="{config.public_url}/voice/gather" method="POST"/>'
        f'<Say voice="{config.voice_name}" language="{config.voice_language}">Tudo bem, até mais.</Say>'
        "</Response>"
    )


def call_owner(message: str) -> str:
    if not _allow(_sent_calls, config.max_calls_per_hour):
        return "Limite de ligações por hora atingido; use WhatsApp."
    if config.voice_provider == "elevenlabs":
        from . import eleven

        return eleven.outbound_call(message)
    call = client().calls.create(to=config.owner_phone, from_=config.twilio_phone, twiml=say_and_listen_twiml(message))
    return f"Ligando para o dono (call sid {call.sid})."

"""Chamada grátis pelo navegador: o celular abre o app do Jarvis (PWA) e conversa em tempo real.

- O áudio vai e volta por WebSocket (PCM 16 kHz), passando pelo Whisper e pelo Piper locais.
- Para "ligar" para você, o Jarvis manda uma notificação push (Web Push/VAPID, grátis) e um WhatsApp com o link.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import os
import time

import numpy as np
from fastapi import WebSocket, WebSocketDisconnect

from . import brain, localvoice, memory
from .config import config

log = logging.getLogger("jarvis.webcall")

FRAME = 320  # 20 ms a 16 kHz
VAD_THRESHOLD = float(os.getenv("VAD_THRESHOLD", "600"))  # RMS mínimo para contar como fala
START_FRAMES = 12  # 240 ms de fala para começar a ouvir
END_FRAMES = 35  # 700 ms de silêncio para considerar que você terminou
MAX_FRAMES = 50 * 20  # no máximo 20 s por fala
FILLER = "Hum, deixa eu ver."
END_TOKEN = "[FIM]"

_pending: dict = {}  # motivo da ligação que o Jarvis está fazendo
_tts_cache: dict[str, bytes] = {}


def app_token() -> str:
    return hmac.new(config.secret.encode(), b"app", hashlib.sha256).hexdigest()[:32]


def valid_token(token: str) -> bool:
    return bool(config.secret) and hmac.compare_digest(token or "", app_token())


def app_link(call: bool = False) -> str:
    return f"{config.public_url}/app/{'?call=1' if call else ''}#k={app_token()}"


# ---------- Push (VAPID) ----------

def _vapid():
    from py_vapid import Vapid

    path = config.state_dir / "vapid.pem"
    if not path.exists():
        config.state_dir.mkdir(parents=True, exist_ok=True)
        v = Vapid()
        v.generate_keys()
        v.save_key(str(path))
    return Vapid.from_file(str(path))


def vapid_public_key() -> str:
    from cryptography.hazmat.primitives import serialization
    from py_vapid.utils import b64urlencode

    raw = _vapid().public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return b64urlencode(raw)


def _subs_file():
    return config.state_dir / "push.json"


def subscriptions() -> list[dict]:
    path = _subs_file()
    return json.loads(path.read_text()) if path.exists() else []


def add_subscription(sub: dict) -> None:
    subs = [s for s in subscriptions() if s.get("endpoint") != sub.get("endpoint")] + [sub]
    config.state_dir.mkdir(parents=True, exist_ok=True)
    _subs_file().write_text(json.dumps(subs))


def _push_all(payload: dict) -> int:
    from pywebpush import WebPushException, webpush

    alive, sent = [], 0
    for sub in subscriptions():
        try:
            webpush(sub, json.dumps(payload), vapid_private_key=_vapid(), vapid_claims={"sub": "mailto:jarvis@example.com"}, ttl=120)
            alive.append(sub)
            sent += 1
        except WebPushException as e:
            if getattr(e.response, "status_code", None) not in (404, 410):  # 404/410 = celular cancelou a inscrição
                alive.append(sub)
            log.warning("Push falhou: %s", e)
    _subs_file().write_text(json.dumps(alive))
    return sent


def ring(message: str) -> str:
    """O Jarvis 'liga': notificação no celular + WhatsApp com o link para atender."""
    from . import comms

    _pending.update(motivo=message, at=time.time())
    sent = _push_all({"title": "📞 Jarvis ligando", "body": message[:180], "url": app_link(call=True)})
    whats = comms.send_whatsapp(f"📞 Jarvis quer falar com você: {message}\nAtender: {app_link(call=True)}")
    return f"Chamando no app ({sent} aparelho(s) notificados). WhatsApp: {whats}"


def _take_pending() -> str | None:
    if _pending and time.time() - _pending.get("at", 0) < 600:
        motivo = _pending.get("motivo")
        _pending.clear()
        return motivo
    _pending.clear()
    return None


# ---------- A chamada ----------

async def _tts(text: str) -> bytes:
    if text in _tts_cache:
        return _tts_cache[text]
    pcm = await asyncio.to_thread(localvoice.synthesize, text)
    if text == FILLER:
        _tts_cache[text] = pcm
    return pcm


class CallSession:
    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.leftover = b""
        self.voiced = 0
        self.silent = 0
        self.speech: list[bytes] = []
        self.in_speech = False
        self.playing = False
        self.busy = False
        self.tasks: set[asyncio.Task] = set()

    async def send(self, kind: str, **data) -> None:
        await self.ws.send_text(json.dumps({"type": kind, **data}, ensure_ascii=False))

    async def speak(self, text: str) -> None:
        pcm = await _tts(text)
        if not pcm:
            return
        self.playing = True
        for i in range(0, len(pcm), 32000):  # blocos de 1 s
            await self.ws.send_bytes(pcm[i : i + 32000])

    async def run(self) -> None:
        await self.ws.accept()
        try:
            auth = json.loads(await asyncio.wait_for(self.ws.receive_text(), timeout=10))
        except (asyncio.TimeoutError, ValueError, WebSocketDisconnect):
            await self.ws.close(code=4401)
            return
        if not valid_token(auth.get("k", "")):
            await self.ws.close(code=4401)
            return

        motivo = _take_pending()
        greeting = motivo or f"Oi {config.owner_name}, Jarvis aqui. Pode falar."
        memory.log_exchange("app", "Jarvis", greeting)
        await self.send("jarvis", text=greeting)
        await self.speak(greeting)
        try:
            while True:
                msg = await self.ws.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                if msg.get("bytes"):
                    self.feed(msg["bytes"])
                elif msg.get("text"):
                    event = json.loads(msg["text"]).get("type")
                    if event == "played":
                        self.playing = False
                    elif event == "hangup":
                        break
        except WebSocketDisconnect:
            pass
        finally:
            for t in self.tasks:
                t.cancel()

    def feed(self, data: bytes) -> None:
        """Detecção de fala por energia (VAD simples), quadro a quadro."""
        data = self.leftover + data
        cut = len(data) - len(data) % (FRAME * 2)
        self.leftover = data[cut:]
        for i in range(0, cut, FRAME * 2):
            frame = data[i : i + FRAME * 2]
            rms = float(np.sqrt(np.mean(np.frombuffer(frame, dtype=np.int16).astype(np.float32) ** 2)))
            # Enquanto o Jarvis fala, exige voz mais forte (evita interromper com o eco do alto-falante).
            loud = rms > VAD_THRESHOLD * (2 if self.playing else 1)
            if not self.in_speech:
                self.voiced = self.voiced + 1 if loud else 0
                self.speech = (self.speech + [frame])[-START_FRAMES:]
                if self.voiced >= START_FRAMES:
                    self.in_speech, self.silent = True, 0
                    if self.playing:  # você interrompeu: para de falar
                        self.playing = False
                        self._spawn(self.send("clear"))
                continue
            self.speech.append(frame)
            self.silent = 0 if loud else self.silent + 1
            if self.silent >= END_FRAMES or len(self.speech) >= MAX_FRAMES:
                pcm = b"".join(self.speech)
                self.in_speech, self.voiced, self.speech = False, 0, []
                if not self.busy:
                    self._spawn(self.respond(pcm))

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def respond(self, pcm: bytes) -> None:
        self.busy = True
        try:
            text = await asyncio.to_thread(localvoice.transcribe_pcm, pcm)
            if not text:
                return
            await self.send("you", text=text)
            memory.log_exchange("app", config.owner_name, text)
            await self.speak(FILLER)
            reply = await brain.ask(text, channel="voice", session="voz")
            ending = END_TOKEN in reply
            reply = brain.speakable(reply.replace(END_TOKEN, "")) or "Feito."
            memory.log_exchange("app", "Jarvis", reply)
            await self.send("jarvis", text=reply, end=ending)
            await self.speak(reply)
        except Exception:
            log.exception("Falha ao responder na chamada")
        finally:
            self.busy = False

"""Ouvidos do Jarvis: webhooks do Twilio (WhatsApp e voz) + a ronda autônoma em segundo plano."""
import asyncio
import logging
import re
import uuid
from contextlib import asynccontextmanager
from xml.sax.saxutils import escape

from fastapi import FastAPI, HTTPException, Request, Response
from twilio.request_validator import RequestValidator

from . import brain, comms, heartbeat, memory
from .config import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("jarvis.server")

_background: set[asyncio.Task] = set()
_voice_jobs: dict[str, asyncio.Task] = {}


def _spawn(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)
    return task


@asynccontextmanager
async def lifespan(app: FastAPI):
    _spawn(heartbeat.run_forever())
    yield


app = FastAPI(title="Infinite Jarvis", lifespan=lifespan)


def twiml(body: str) -> Response:
    return Response(content=body, media_type="application/xml")


async def verified_form(request: Request) -> dict:
    """Valida a assinatura do Twilio e garante que quem fala é o dono."""
    form = dict(await request.form())
    if config.validate_signature:
        url = config.public_url + request.url.path
        if request.url.query:
            url += "?" + request.url.query
        signature = request.headers.get("X-Twilio-Signature", "")
        if not RequestValidator(config.twilio_token).validate(url, form, signature):
            raise HTTPException(403, "Assinatura inválida")
    sender = form.get("From", "")
    # Em ligações feitas pelo Jarvis, o dono é o "To".
    if config.owner_phone not in (sender.removeprefix("whatsapp:"), form.get("To", "")):
        log.warning("Contato ignorado de %s", sender)
        raise HTTPException(403, "Não autorizado")
    return form


# ---------- WhatsApp ----------

async def _answer_whatsapp(text: str) -> None:
    memory.log_exchange("whatsapp", config.owner_name, text)
    reply = await brain.ask(text, channel="whatsapp")
    if reply:
        memory.log_exchange("whatsapp", "Jarvis", reply)
        comms.send_whatsapp(reply)


@app.post("/whatsapp")
async def whatsapp(request: Request):
    form = await verified_form(request)
    text = form.get("Body", "").strip()
    if form.get("NumMedia", "0") != "0":
        text += "\n[O dono enviou mídia: " + ", ".join(
            form[k] for k in form if k.startswith("MediaUrl")
        ) + "]"
    # Responde já ao Twilio (limite de 15s) e manda a resposta depois, quando o Claude terminar.
    _spawn(_answer_whatsapp(text))
    return twiml("<Response/>")


# ---------- Voz ----------

def _say(text: str) -> str:
    return f'<Say voice="{config.voice_name}" language="{config.voice_language}">{escape(text)}</Say>'


def _speakable(text: str) -> str:
    """Remove emojis e marcação que a voz leria em voz alta."""
    text = re.sub(r"[\U0001F000-\U0001FAFF☀-➿️]", "", text)
    return re.sub(r"[*_#`>]", "", text).strip()


async def _answer_voice(text: str) -> str:
    memory.log_exchange("ligação", config.owner_name, text)
    reply = _speakable(await brain.ask(text, channel="voice"))
    memory.log_exchange("ligação", "Jarvis", reply)
    return reply


@app.post("/voice")
async def voice_incoming(request: Request):
    await verified_form(request)
    return twiml(comms.say_and_listen_twiml(f"Oi {config.owner_name}, Jarvis aqui. Pode falar."))


@app.post("/voice/gather")
async def voice_gather(request: Request):
    form = await verified_form(request)
    speech = form.get("SpeechResult", "").strip()
    if not speech:
        return twiml(comms.say_and_listen_twiml("Não entendi. Pode repetir?"))
    job = uuid.uuid4().hex
    _voice_jobs[job] = _spawn(_answer_voice(speech))
    return twiml(f'<Response>{_say("Um instante.")}<Redirect method="POST">{config.public_url}/voice/wait?job={job}</Redirect></Response>')


@app.post("/voice/wait")
async def voice_wait(request: Request, job: str):
    await verified_form(request)
    task = _voice_jobs.get(job)
    if task is None:
        return twiml(comms.say_and_listen_twiml("Perdi o fio da meada. O que você disse?"))
    if not task.done():
        # Segura a ligação enquanto o Claude pensa.
        return twiml(f'<Response><Pause length="2"/><Redirect method="POST">{config.public_url}/voice/wait?job={job}</Redirect></Response>')
    _voice_jobs.pop(job)
    return twiml(comms.say_and_listen_twiml(task.result() or "Feito."))


@app.get("/health")
async def health():
    return {"ok": True, "vault": str(config.vault_path), "heartbeat_minutes": config.heartbeat_minutes}

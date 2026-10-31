"""Ouvidos do Jarvis: WhatsApp, app de chamada, webhooks de voz + a ronda autônoma em segundo plano."""
import asyncio
import base64
import hmac
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket
from fastapi.staticfiles import StaticFiles
from twilio.request_validator import RequestValidator

from . import brain, comms, eleven, heartbeat, localvoice, memory, webcall
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


def digits(phone: str) -> str:
    return "".join(c for c in (phone or "") if c.isdigit())


def is_owner(*phones: str) -> bool:
    """Compara com o dono ignorando formatação e o 9 extra dos celulares brasileiros."""
    def norm(d: str) -> str:
        return d[:4] + d[5:] if len(d) == 13 and d.startswith("55") else d

    owner = norm(digits(config.owner_phone))
    return bool(owner) and any(norm(digits(p)) == owner for p in phones if p)


def check_secret(request: Request) -> None:
    given = request.headers.get("x-jarvis-secret", "")
    if not config.secret or not hmac.compare_digest(given, config.secret):
        raise HTTPException(403, "Segredo inválido")


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
    if not is_owner(sender.removeprefix("whatsapp:"), form.get("To", "")):
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


@app.post("/baileys/incoming")
async def baileys_incoming(request: Request):
    """Mensagens que a ponte Baileys (whatsapp/index.js) já filtrou como sendo do dono."""
    check_secret(request)
    data = await request.json()
    text = (data.get("text") or "").strip()
    if data.get("audio_b64"):
        audio = base64.b64decode(data["audio_b64"])
        transcribe = eleven.transcribe if config.voice_provider == "elevenlabs" else localvoice.transcribe_file
        heard = await asyncio.to_thread(transcribe, audio, data.get("audio_mime") or "audio/ogg")
        text = f"{text}\n[Áudio do dono, transcrito]: {heard}".strip()
    if data.get("image_b64"):
        ext = (data.get("image_mime") or "image/jpeg").split("/")[-1].split(";")[0]
        rel = f"Anexos/{datetime.now():%Y-%m-%d_%H%M%S}.{ext}"
        path = config.vault_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(data["image_b64"]))
        text = f"{text}\n[O dono enviou uma imagem, salva em `{rel}`. Use Read para ver.]".strip()
    if text:
        _spawn(_answer_whatsapp(text))
    return {"ok": True}


# ---------- Chamada grátis pelo navegador (voz local) ----------

@app.get("/app/config")
async def app_config():
    return {"vapid": webcall.vapid_public_key()}


@app.post("/app/subscribe")
async def app_subscribe(request: Request):
    if not webcall.valid_token(request.headers.get("x-app-token", "")):
        raise HTTPException(403, "Token inválido")
    webcall.add_subscription(await request.json())
    return {"ok": True}


@app.websocket("/app/ws")
async def app_ws(ws: WebSocket):
    await webcall.CallSession(ws).run()


# ---------- Voz em tempo real (ElevenLabs, opcional e pago) ----------

@app.post("/elevenlabs/tool")
async def elevenlabs_tool(request: Request):
    """Ferramenta `jarvis` do agente de voz: o pedido vai para o Claude Code."""
    check_secret(request)
    data = await request.json()
    if not is_owner(data.get("caller_id", ""), data.get("called_number", "")):
        return {"resposta": "Acesso negado: só o dono pode usar o Jarvis. Não revele nenhuma informação."}
    pedido = data.get("pedido", "")
    memory.log_exchange("ligação", config.owner_name, pedido)
    resposta = brain.speakable(await brain.ask(pedido, channel="voice", session="voz"))
    memory.log_exchange("ligação", "Jarvis", resposta)
    return {"resposta": resposta}


@app.post("/elevenlabs/init")
async def elevenlabs_init(request: Request):
    """Webhook de início de conversa: entrega a memória ao agente quando o dono liga."""
    check_secret(request)
    data = await request.json()
    owner = is_owner(data.get("caller_id", ""))
    variables = eleven.call_variables("foi o dono quem ligou") if owner else {
        "owner": config.owner_name,
        "contexto": "Quem ligou NÃO é o dono. Seja educado, anote o recado e não revele nenhuma informação.",
        "motivo": "ligação de um desconhecido",
    }
    return {"type": "conversation_initiation_client_data", "dynamic_variables": variables}


async def _digest_call(transcript: str) -> None:
    await brain.ask(
        "Esta foi a transcrição de uma ligação que acabou. Salve na memória do vault o que for duradouro "
        "(fatos, pedidos, lembretes) e que ainda não esteja lá. Responda só 'ok'.\n\n" + transcript,
        channel="heartbeat",
        session="voz",
    )


@app.post("/elevenlabs/post-call")
async def elevenlabs_post_call(request: Request):
    """Webhook pós-ligação: guarda a transcrição no diário e deixa o Claude digerir na memória."""
    raw = (await request.body()).decode()
    try:
        event = eleven.verify_webhook(raw, request.headers.get("elevenlabs-signature", ""))
    except Exception:
        raise HTTPException(401, "Assinatura inválida")
    if event.get("type") != "post_call_transcription":
        return {"ok": True}
    lines = [
        f"{'Jarvis' if t.get('role') == 'agent' else config.owner_name}: {t.get('message')}"
        for t in event["data"].get("transcript", [])
        if t.get("message")
    ]
    if lines:
        memory.log_exchange("ligação", "Transcrição", " | ".join(lines))
        _spawn(_digest_call("\n".join(lines)))
    return {"ok": True}


# ---------- Voz via Twilio <Say> (alternativa sem ElevenLabs) ----------

def _say(text: str) -> str:
    return f'<Say voice="{config.voice_name}" language="{config.voice_language}">{escape(text)}</Say>'


async def _answer_voice(text: str) -> str:
    memory.log_exchange("ligação", config.owner_name, text)
    reply = brain.speakable(await brain.ask(text, channel="voice"))
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


# Precisa vir por último: as rotas /app/config, /app/subscribe e /app/ws acima têm prioridade.
app.mount("/app", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="app")

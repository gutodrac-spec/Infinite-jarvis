"""Voz em tempo real com ElevenLabs Agents.

A ElevenLabs cuida da ligação (ouvir, falar e saber quando é a vez de cada um) com um modelo rápido.
Quando precisa de memória, lembretes ou do computador, ela chama a ferramenta `jarvis`, que é um
webhook para o nosso servidor. Ali quem responde é o Claude Code dentro do vault.
"""
import json
import os

from elevenlabs import ElevenLabs

from . import memory
from .config import config

_client: ElevenLabs | None = None

AGENT_PROMPT = """Você é o JARVIS, assistente pessoal de {{owner}}, numa LIGAÇÃO telefônica em tempo real.
Fale português do Brasil, com frases curtas, naturais e um leve humor britânico. Nada de listas ou markdown.

O que você já sabe (memória):
{{contexto}}

Motivo desta ligação: {{motivo}}

Você tem a ferramenta `jarvis`: ela é o seu cérebro completo, com memória de longo prazo no Obsidian,
lembretes, agenda, o computador e a internet. Use-a SEMPRE que precisar:
- lembrar de algo que não está acima;
- salvar qualquer coisa (lembrete, fato, preferência, tarefa);
- fazer qualquer ação no computador ou pesquisar algo.
Passe o pedido completo, em linguagem natural, no campo `pedido`. Nunca invente o que a ferramenta
responderia. Se a ligação foi feita por você, comece explicando o motivo."""


def client() -> ElevenLabs:
    global _client
    if _client is None:
        _client = ElevenLabs(api_key=config.elevenlabs_key)
    return _client


def _ids_file():
    config.state_dir.mkdir(parents=True, exist_ok=True)
    return config.state_dir / "elevenlabs.json"


def ids() -> dict:
    path = _ids_file()
    data = json.loads(path.read_text()) if path.exists() else {}
    for key in ("agent_id", "tool_id", "phone_number_id"):
        env = os.getenv(f"ELEVENLABS_{key.upper()}")
        if env:
            data[key] = env
    return data


def _save_ids(data: dict) -> None:
    _ids_file().write_text(json.dumps(data, indent=2))


def _tool_request() -> dict:
    caller = {"type": "string", "description": "Telefone de quem ligou", "dynamic_variable": "system__caller_id"}
    called = {"type": "string", "description": "Telefone que recebeu a ligação", "dynamic_variable": "system__called_number"}
    return {
        "tool_config": {
            "type": "webhook",
            "name": "jarvis",
            "description": "Cérebro do Jarvis: memória (Obsidian), lembretes, computador e internet.",
            "response_timeout_secs": 120,
            "pre_tool_speech": "force",
            "tool_call_sound": "typing",
            "api_schema": {
                "url": f"{config.public_url}/elevenlabs/tool",
                "method": "POST",
                "request_headers": {"X-Jarvis-Secret": config.secret},
                "request_body_schema": {
                    "type": "object",
                    "required": ["pedido"],
                    "properties": {
                        "pedido": {"type": "string", "description": "O que o dono pediu ou o que você precisa saber/fazer"},
                        "caller_id": caller,
                        "called_number": called,
                    },
                },
            },
        }
    }


def _agent_config(tool_id: str) -> dict:
    tts = {"model_id": "eleven_flash_v2_5"}
    if config.elevenlabs_voice_id:
        tts["voice_id"] = config.elevenlabs_voice_id
    return {
        "agent": {
            "first_message": f"Oi {config.owner_name}, Jarvis na linha.",
            "language": "pt",
            "dynamic_variables": {
                "dynamic_variable_placeholders": {
                    "owner": config.owner_name,
                    "contexto": "(ainda nada carregado — use a ferramenta jarvis)",
                    "motivo": "foi o dono quem ligou",
                }
            },
            "prompt": {"prompt": AGENT_PROMPT, "llm": config.elevenlabs_llm, "tool_ids": [tool_id]},
        },
        "tts": tts,
    }


PLATFORM_SETTINGS = {
    "overrides": {
        "enable_conversation_initiation_client_data_from_webhook": True,
        "conversation_config_override": {"agent": {"first_message": True}},
    }
}


def setup() -> dict:
    """Cria ou atualiza a ferramenta, o agente e o número de telefone na ElevenLabs. Pode rodar várias vezes."""
    if not (config.elevenlabs_key and config.public_url and config.secret):
        raise SystemExit("Defina ELEVENLABS_API_KEY, PUBLIC_URL e JARVIS_SECRET antes do setup.")
    ca = client().conversational_ai
    data = ids()

    if data.get("tool_id"):
        ca.tools.update(data["tool_id"], request=_tool_request())
    else:
        data["tool_id"] = ca.tools.create(request=_tool_request()).id
    _save_ids(data)

    conversation_config = _agent_config(data["tool_id"])
    if data.get("agent_id"):
        ca.agents.update(data["agent_id"], conversation_config=conversation_config, platform_settings=PLATFORM_SETTINGS)
    else:
        data["agent_id"] = ca.agents.create(
            name="Infinite Jarvis", conversation_config=conversation_config, platform_settings=PLATFORM_SETTINGS
        ).agent_id
    _save_ids(data)

    if config.twilio_phone and config.twilio_sid:
        if data.get("phone_number_id"):
            ca.phone_numbers.update(data["phone_number_id"], agent_id=data["agent_id"])
        else:
            # Importar o número faz a ElevenLabs configurar o webhook de voz dele no Twilio.
            data["phone_number_id"] = ca.phone_numbers.create(
                request={
                    "provider": "twilio",
                    "phone_number": config.twilio_phone,
                    "label": "Jarvis",
                    "sid": config.twilio_sid,
                    "token": config.twilio_token,
                    "agent_id": data["agent_id"],
                }
            ).phone_number_id
        _save_ids(data)
    return data


def call_variables(motivo: str) -> dict:
    return {"owner": config.owner_name, "contexto": memory.context_summary(), "motivo": motivo}


def outbound_call(message: str) -> str:
    data = ids()
    if not (data.get("agent_id") and data.get("phone_number_id")):
        return "ElevenLabs não configurada: rode `python -m jarvis setup-elevenlabs`."
    resp = client().conversational_ai.twilio.outbound_call(
        agent_id=data["agent_id"],
        agent_phone_number_id=data["phone_number_id"],
        to_number=config.owner_phone,
        conversation_initiation_client_data={
            "dynamic_variables": call_variables(message),
            "conversation_config_override": {"agent": {"first_message": message}},
        },
    )
    return f"Ligando para o dono pela ElevenLabs (conversa {resp.conversation_id})." if resp.success else resp.message


def transcribe(audio: bytes, mime: str = "audio/ogg") -> str:
    """Transcreve áudios do WhatsApp com o Scribe."""
    resp = client().speech_to_text.convert(
        model_id=os.getenv("ELEVENLABS_STT_MODEL", "scribe_v1"),
        file=("audio.ogg", audio, mime),
        language_code="por",
    )
    return getattr(resp, "text", "") or ""


def verify_webhook(raw_body: str, signature: str) -> dict:
    return client().webhooks.construct_event(raw_body, signature, config.elevenlabs_webhook_secret)

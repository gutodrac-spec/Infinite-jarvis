import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _default_public_url() -> str:
    # No GitHub Codespaces a porta encaminhada vira https://<codespace>-8000.<domínio>
    name, domain = os.getenv("CODESPACE_NAME"), os.getenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN")
    return f"https://{name}-{os.getenv('PORT', '8000')}.{domain}" if name and domain else ""


@dataclass(frozen=True)
class Config:
    # Twilio (WhatsApp + voz)
    twilio_sid: str = field(default_factory=lambda: _env("TWILIO_ACCOUNT_SID"))
    twilio_token: str = field(default_factory=lambda: _env("TWILIO_AUTH_TOKEN"))
    twilio_phone: str = field(default_factory=lambda: _env("TWILIO_PHONE_NUMBER"))  # +1555...
    twilio_whatsapp: str = field(default_factory=lambda: _env("TWILIO_WHATSAPP_NUMBER"))  # whatsapp:+1555...
    validate_signature: bool = field(default_factory=lambda: _env("TWILIO_VALIDATE_SIGNATURE", "true") == "true")

    # Dono (o único que o Jarvis obedece)
    owner_phone: str = field(default_factory=lambda: _env("OWNER_PHONE"))  # +5511999999999
    owner_name: str = field(default_factory=lambda: _env("OWNER_NAME", "chefe"))

    # URL pública do servidor (Codespaces é detectado sozinho; senão ngrok, Cloudflare Tunnel etc.)
    public_url: str = field(default_factory=lambda: (_env("PUBLIC_URL") or _default_public_url()).rstrip("/"))
    # Segredo compartilhado entre o servidor, a ponte Baileys e os webhooks da ElevenLabs
    secret: str = field(default_factory=lambda: _env("JARVIS_SECRET"))

    # Canais: whatsapp = baileys | twilio ; voz = elevenlabs | twilio
    whatsapp_provider: str = field(default_factory=lambda: _env("WHATSAPP_PROVIDER", "baileys"))
    voice_provider: str = field(default_factory=lambda: _env("VOICE_PROVIDER", "elevenlabs"))
    baileys_url: str = field(default_factory=lambda: _env("BAILEYS_URL", "http://127.0.0.1:3001"))

    # ElevenLabs (voz em tempo real)
    elevenlabs_key: str = field(default_factory=lambda: _env("ELEVENLABS_API_KEY"))
    elevenlabs_voice_id: str = field(default_factory=lambda: _env("ELEVENLABS_VOICE_ID"))
    elevenlabs_llm: str = field(default_factory=lambda: _env("ELEVENLABS_LLM", "claude-haiku-4-5"))
    elevenlabs_webhook_secret: str = field(default_factory=lambda: _env("ELEVENLABS_WEBHOOK_SECRET"))

    # Cérebro (Claude Code via Agent SDK)
    vault_path: Path = field(default_factory=lambda: Path(_env("OBSIDIAN_VAULT", "./vault")).expanduser().resolve())
    model: str = field(default_factory=lambda: _env("JARVIS_MODEL"))  # vazio = padrão do Claude Code
    max_turns: int = field(default_factory=lambda: int(_env("JARVIS_MAX_TURNS", "25")))

    # Autonomia
    heartbeat_minutes: int = field(default_factory=lambda: int(_env("HEARTBEAT_MINUTES", "15")))
    quiet_start: int = field(default_factory=lambda: int(_env("QUIET_HOURS_START", "23")))
    quiet_end: int = field(default_factory=lambda: int(_env("QUIET_HOURS_END", "7")))
    max_calls_per_hour: int = field(default_factory=lambda: int(_env("MAX_CALLS_PER_HOUR", "2")))
    max_messages_per_hour: int = field(default_factory=lambda: int(_env("MAX_MESSAGES_PER_HOUR", "10")))

    voice_language: str = field(default_factory=lambda: _env("VOICE_LANGUAGE", "pt-BR"))
    voice_name: str = field(default_factory=lambda: _env("VOICE_NAME", "Polly.Camila-Neural"))

    # Sincroniza o vault com o GitHub (git commit/push) a cada ronda
    vault_git_sync: bool = field(default_factory=lambda: _env("VAULT_GIT_SYNC", "false") == "true")

    state_dir: Path = field(default_factory=lambda: Path(_env("JARVIS_STATE_DIR", "./.jarvis_state")).resolve())

    @property
    def owner_whatsapp(self) -> str:
        return f"whatsapp:{self.owner_phone}"


config = Config()

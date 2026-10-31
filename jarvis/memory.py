"""Memória: o vault do Obsidian é a memória de longo prazo; aqui só ficam o log diário e o estado das sessões."""
import json
from datetime import datetime
from pathlib import Path

from .config import config


def daily_note(now: datetime | None = None) -> Path:
    now = now or datetime.now()
    path = config.vault_path / "Diario" / f"{now:%Y-%m-%d}.md"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {now:%Y-%m-%d}\n\n## Conversas\n", encoding="utf-8")
    return path


def log_exchange(channel: str, who: str, text: str) -> None:
    """Acrescenta uma linha no diário do dia (ex.: '- 14:32 [whatsapp] Você: ...')."""
    now = datetime.now()
    one_line = " ".join(text.split())
    with daily_note(now).open("a", encoding="utf-8") as f:
        f.write(f"- {now:%H:%M} [{channel}] **{who}:** {one_line}\n")


def _state_file() -> Path:
    config.state_dir.mkdir(parents=True, exist_ok=True)
    return config.state_dir / "sessions.json"


def get_session(name: str) -> str | None:
    path = _state_file()
    if not path.exists():
        return None
    return json.loads(path.read_text()).get(name)


def save_session(name: str, session_id: str) -> None:
    path = _state_file()
    data = json.loads(path.read_text()) if path.exists() else {}
    data[name] = session_id
    path.write_text(json.dumps(data, indent=2))

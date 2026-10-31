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


def context_summary(limit: int = 3000) -> str:
    """Resumo curto da memória para a voz em tempo real: perfil, lembretes em aberto e o fim do diário de hoje."""
    parts = []
    perfil = config.vault_path / "Jarvis" / "Perfil.md"
    if perfil.exists():
        parts.append(perfil.read_text(encoding="utf-8").strip())
    lembretes = config.vault_path / "Jarvis" / "Lembretes.md"
    if lembretes.exists():
        abertos = [l for l in lembretes.read_text(encoding="utf-8").splitlines() if l.startswith("- [ ]")]
        parts.append("Lembretes em aberto:\n" + ("\n".join(abertos) or "nenhum"))
    hoje = config.vault_path / "Diario" / f"{datetime.now():%Y-%m-%d}.md"
    if hoje.exists():
        parts.append("Conversas de hoje (fim):\n" + "\n".join(hoje.read_text(encoding="utf-8").splitlines()[-15:]))
    return "\n\n".join(parts)[:limit]


def sync_vault() -> None:
    """Salva a memória no GitHub para ela sobreviver ao Codespace e aparecer no Obsidian (plugin Obsidian Git)."""
    import subprocess

    vault = str(config.vault_path)

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", vault, *args], capture_output=True, text=True)

    git("add", "-A", ".")
    if git("diff", "--cached", "--quiet").returncode != 0:
        git("commit", "-m", f"Jarvis: memória {datetime.now():%Y-%m-%d %H:%M}")
    git("pull", "--rebase", "--autostash")
    git("push")

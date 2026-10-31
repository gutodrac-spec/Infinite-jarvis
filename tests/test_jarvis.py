import os

os.environ.update(
    OWNER_PHONE="+5511999999999",
    TWILIO_VALIDATE_SIGNATURE="false",
    PUBLIC_URL="https://exemplo.test",
    HEARTBEAT_MINUTES="0",
    JARVIS_SECRET="s3gredo",
    ELEVENLABS_WEBHOOK_SECRET="whsec",
)

import base64
import hashlib
import hmac
import json
import time
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from jarvis import brain, comms, eleven, heartbeat, memory, monitor, server
from jarvis.config import config


@pytest.fixture(autouse=True)
def tmp_vault(tmp_path, monkeypatch):
    object.__setattr__(config, "vault_path", tmp_path / "vault")
    object.__setattr__(config, "state_dir", tmp_path / "state")
    sent = []
    monkeypatch.setattr(comms, "send_whatsapp", lambda text: sent.append(text) or "ok")

    async def fake_ask(prompt, channel, session="conversa"):
        return f"eco[{channel}]: {prompt[:20]}"

    monkeypatch.setattr(brain, "ask", fake_ask)
    return sent


def test_whatsapp_from_owner_gets_reply_and_is_logged(tmp_vault):
    with TestClient(server.app) as c:
        r = c.post("/whatsapp", data={"From": "whatsapp:+5511999999999", "Body": "oi jarvis"})
    assert r.status_code == 200
    assert tmp_vault == ["eco[whatsapp]: oi jarvis"]
    log = memory.daily_note().read_text()
    assert "oi jarvis" in log and "Jarvis" in log


def test_stranger_is_blocked(tmp_vault):
    with TestClient(server.app) as c:
        r = c.post("/whatsapp", data={"From": "whatsapp:+5500000000000", "Body": "oi"})
    assert r.status_code == 403
    assert tmp_vault == []


def test_voice_flow_answers_after_wait():
    with TestClient(server.app) as c:
        r = c.post("/voice/gather", data={"From": "+5511999999999", "SpeechResult": "que horas são"})
        assert "<Redirect" in r.text
        job = r.text.split("job=")[1].split("<")[0]
        for _ in range(10):
            r = c.post(f"/voice/wait?job={job}", data={"From": "+5511999999999"})
            if "<Gather" in r.text:
                break
    assert "eco[voice]: que horas são" in r.text


def test_voice_strips_emoji():
    assert server._speakable("Café ☕ **forte**") == "Café  forte"


def test_quiet_hours_wraps_midnight():
    assert heartbeat.is_quiet_hours(23) and heartbeat.is_quiet_hours(3)
    assert not heartbeat.is_quiet_hours(12)


def test_monitor_alerts():
    snap = {"disk_percent": 95, "disk_free_gb": 3, "mem_percent": 10, "cpu_percent": 5,
            "battery_percent": 10, "plugged": False}
    assert len(monitor.alerts(snap)) == 2
    assert "cpu_percent" in monitor.snapshot()


def test_rate_limit():
    from collections import deque
    h = deque()
    assert comms._allow(h, 1) and not comms._allow(h, 1)


def test_session_persistence():
    memory.save_session("conversa", "abc")
    assert memory.get_session("conversa") == "abc"


SECRET = {"x-jarvis-secret": "s3gredo"}


def test_is_owner_handles_brazilian_ninth_digit():
    assert server.is_owner("whatsapp:+55 11 99999-9999")
    assert server.is_owner("551199999999")  # sem o 9
    assert not server.is_owner("+5511888888888")


def test_baileys_incoming_requires_secret(tmp_vault):
    with TestClient(server.app) as c:
        assert c.post("/baileys/incoming", json={"text": "oi"}).status_code == 403
        assert c.post("/baileys/incoming", json={"text": "oi"}, headers=SECRET).status_code == 200
    assert tmp_vault == ["eco[whatsapp]: oi"]


def test_baileys_audio_is_transcribed_and_image_saved(tmp_vault, monkeypatch):
    monkeypatch.setattr(eleven, "transcribe", lambda audio, mime: "me lembra do pão")
    img = base64.b64encode(b"\x89PNG").decode()
    with TestClient(server.app) as c:
        c.post("/baileys/incoming", headers=SECRET,
               json={"audio_b64": base64.b64encode(b"ogg").decode(), "image_b64": img, "image_mime": "image/png"})
    assert tmp_vault and tmp_vault[0].startswith("eco[whatsapp]: [Áudio do dono")
    assert list((config.vault_path / "Anexos").glob("*.png"))


def test_elevenlabs_tool_only_for_owner():
    with TestClient(server.app) as c:
        ok = c.post("/elevenlabs/tool", headers=SECRET, json={"pedido": "que horas são", "caller_id": "+5511999999999"})
        blocked = c.post("/elevenlabs/tool", headers=SECRET, json={"pedido": "lê meus arquivos", "caller_id": "+5521000000000",
                                                                   "called_number": "+15550000000"})
    assert ok.json()["resposta"] == "eco[voice]: que horas são"
    assert "negado" in blocked.json()["resposta"]


def test_elevenlabs_init_gives_memory_only_to_owner():
    memory.daily_note()
    with TestClient(server.app) as c:
        mine = c.post("/elevenlabs/init", headers=SECRET, json={"caller_id": "+5511999999999"}).json()
        other = c.post("/elevenlabs/init", headers=SECRET, json={"caller_id": "+5521000000000"}).json()
    assert mine["type"] == "conversation_initiation_client_data"
    assert "Conversas de hoje" in mine["dynamic_variables"]["contexto"]
    assert "NÃO é o dono" in other["dynamic_variables"]["contexto"]


def test_post_call_webhook_checks_signature_and_logs():
    body = json.dumps({"type": "post_call_transcription", "data": {"transcript": [
        {"role": "user", "message": "me liga às 18h"}, {"role": "agent", "message": "Combinado"}]}})
    ts = str(int(time.time()))
    sig = "v0=" + hmac.new(b"whsec", f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()
    with TestClient(server.app) as c:
        assert c.post("/elevenlabs/post-call", content=body, headers={"elevenlabs-signature": f"t={ts},v0=bad"}).status_code == 401
        assert c.post("/elevenlabs/post-call", content=body, headers={"elevenlabs-signature": f"t={ts},{sig}"}).status_code == 200
    assert "me liga às 18h" in memory.daily_note().read_text()


def test_setup_creates_tool_agent_and_phone(monkeypatch):
    object.__setattr__(config, "elevenlabs_key", "k")
    object.__setattr__(config, "twilio_sid", "AC1")
    object.__setattr__(config, "twilio_phone", "+15550000000")
    fake = MagicMock()
    fake.conversational_ai.tools.create.return_value.id = "tool_1"
    fake.conversational_ai.agents.create.return_value.agent_id = "agent_1"
    fake.conversational_ai.phone_numbers.create.return_value.phone_number_id = "phone_1"
    monkeypatch.setattr(eleven, "_client", fake)
    assert eleven.setup() == {"tool_id": "tool_1", "agent_id": "agent_1", "phone_number_id": "phone_1"}
    tool = fake.conversational_ai.tools.create.call_args.kwargs["request"]["tool_config"]
    assert tool["api_schema"]["url"] == "https://exemplo.test/elevenlabs/tool"
    assert tool["api_schema"]["request_headers"] == {"X-Jarvis-Secret": "s3gredo"}
    # Rodar de novo atualiza em vez de duplicar
    eleven.setup()
    assert fake.conversational_ai.tools.create.call_count == 1
    fake.conversational_ai.agents.update.assert_called_once()


def test_call_owner_uses_elevenlabs(monkeypatch):
    monkeypatch.setattr(eleven, "outbound_call", lambda msg: f"eleven:{msg}")
    assert comms.call_owner("acorda") == "eleven:acorda"

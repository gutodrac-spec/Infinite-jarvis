import os

os.environ.update(
    OWNER_PHONE="+5511999999999",
    TWILIO_VALIDATE_SIGNATURE="false",
    PUBLIC_URL="https://exemplo.test",
    HEARTBEAT_MINUTES="0",
)

import pytest
from fastapi.testclient import TestClient

from jarvis import brain, comms, heartbeat, memory, monitor, server
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

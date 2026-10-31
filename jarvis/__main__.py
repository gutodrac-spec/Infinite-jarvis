"""Uso:
    python -m jarvis serve          # sobe o servidor (WhatsApp, voz e ronda autônoma)
    python -m jarvis chat           # conversa pelo terminal, sem Twilio
    python -m jarvis ronda          # roda uma ronda autônoma agora
    python -m jarvis ligar "texto"  # faz o Jarvis te ligar
"""
import asyncio
import os
import sys

from . import brain, comms, heartbeat


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if cmd == "serve":
        import uvicorn

        uvicorn.run("jarvis.server:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
    elif cmd == "chat":
        while True:
            try:
                text = input("você> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if text:
                print("jarvis>", asyncio.run(brain.ask(text, channel="terminal")))
    elif cmd == "ronda":
        print(asyncio.run(heartbeat.tick()))
    elif cmd == "ligar":
        print(comms.call_owner(" ".join(sys.argv[2:]) or "Oi, é o Jarvis. Só testando a ligação."))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()

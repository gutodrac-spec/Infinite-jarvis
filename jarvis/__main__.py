"""Uso:
    python -m jarvis serve          # sobe o servidor (WhatsApp, voz e ronda autônoma)
    python -m jarvis chat           # conversa pelo terminal, sem Twilio
    python -m jarvis ronda          # roda uma ronda autônoma agora
    python -m jarvis ligar "texto"  # faz o Jarvis te ligar
    python -m jarvis link           # mostra (e com --whatsapp manda) o link do app de chamada
    python -m jarvis modelos        # baixa os modelos de voz locais (Whisper + Piper)
    python -m jarvis setup-elevenlabs  # opcional/pago: agente de voz ElevenLabs + número Twilio
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
    elif cmd == "link":
        from . import webcall

        link = webcall.app_link()
        print("App de chamada do Jarvis (abra no celular e adicione à tela inicial):\n" + link)
        if "--whatsapp" in sys.argv:
            print(comms.send_whatsapp(f"Seu app de chamada do Jarvis: {link}"))
    elif cmd == "modelos":
        from . import localvoice

        localvoice.download_models()
    elif cmd == "setup-elevenlabs":
        from . import eleven

        ids = eleven.setup()
        print("ElevenLabs pronta:", ids)
        print("Webhooks opcionais (painel ElevenLabs > Agents > Settings):")
        print(f"  início de conversa: {eleven.config.public_url}/elevenlabs/init  (header X-Jarvis-Secret)")
        print(f"  pós-ligação:        {eleven.config.public_url}/elevenlabs/post-call")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()

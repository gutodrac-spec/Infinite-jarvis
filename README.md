# Infinite Jarvis

Assistente pessoal que **fala com você por WhatsApp e por ligação**, pensa com o **Claude Code** e
guarda a memória no **Obsidian**. Ele também tem **iniciativa própria**: a cada X minutos acorda
sozinho, olha o computador, os lembretes e a rotina, e decide se precisa te mandar mensagem ou te ligar.

```
 Você ──WhatsApp/Ligação──► Twilio ──webhook──► servidor (FastAPI)
                                                     │
                                                     ▼
                                     Claude Code (Agent SDK), rodando DENTRO do vault
                                     ├─ lê/escreve notas  → memória (Obsidian)
                                     ├─ Bash / system_status → olha o computador
                                     └─ send_whatsapp / call_owner → fala com você
                                                     ▲
                       Ronda autônoma (a cada 15 min) ┘  ← "consciência" própria
```

## O que ele faz

| Você                                   | Jarvis                                                               |
|----------------------------------------|----------------------------------------------------------------------|
| Manda WhatsApp                         | Responde pelo WhatsApp, consultando e atualizando a memória          |
| Liga para o número Twilio              | Atende, ouve (fala → texto), pensa e responde com voz                |
| "Me liga amanhã às 9h pra lembrar X"   | Anota em `Jarvis/Lembretes.md` e **te liga sozinho** na hora         |
| Nada                                   | Faz a ronda: disco cheio, bateria baixa, lembretes vencidos e rotina |

Todas as conversas ficam registradas em `vault/Diario/AAAA-MM-DD.md`. O que ele aprende vai para
`vault/Jarvis/Perfil.md`, `vault/Pessoas/` e `vault/Projetos/`. A "personalidade" e as regras de
memória ficam em `vault/CLAUDE.md`, que você pode editar à vontade.

## Instalação

Requisitos: Python 3.11+, Node 18+ e Claude Code (`npm i -g @anthropic-ai/claude-code`).

```bash
git clone https://github.com/gutodrac-spec/Infinite-jarvis && cd Infinite-jarvis
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # preencha
claude login            # ou coloque ANTHROPIC_API_KEY no .env
```

**Usar o seu vault do Obsidian:** aponte `OBSIDIAN_VAULT` para ele e copie para lá `vault/CLAUDE.md`
e a pasta `vault/Jarvis/`. Ou então abra a pasta `vault/` deste repositório como um vault no Obsidian.

### Teste rápido, sem Twilio

```bash
python -m jarvis chat     # conversa pelo terminal
python -m jarvis ronda    # roda uma ronda autônoma agora
```

### Twilio (WhatsApp + telefone)

1. Crie uma conta em twilio.com e compre um número com **Voice**. Para usar número do Brasil, a
   Twilio pede cadastro (Regulatory Bundle).
2. **WhatsApp:** para testar, use o *WhatsApp Sandbox* (Messaging → Try it out). Em produção,
   registre um WhatsApp Sender.
3. Exponha o servidor: `python -m jarvis serve` e, em outro terminal, `ngrok http 8000`. Coloque a
   URL gerada em `PUBLIC_URL`.
4. Configure os webhooks (método POST):
   - WhatsApp → "When a message comes in": `https://SUA-URL/whatsapp`
   - Número de voz → "A call comes in": `https://SUA-URL/voice`
5. Teste: `python -m jarvis ligar "Fala, chefe. Jarvis online."`

## Segurança e limites

- Só o número `OWNER_PHONE` é atendido. Os demais recebem 403, e a assinatura do Twilio é validada.
- O Claude roda com `permission_mode="dontAsk"`: só as ferramentas da lista em `jarvis/brain.py` são
  liberadas. Isso **inclui `Bash`**, que é como ele "olha o computador". Rode numa máquina ou conta
  de usuário de confiança. Se não quiser isso, tire `Bash` da lista.
- Para não virar spam, há limite de ligações e mensagens por hora (`MAX_CALLS_PER_HOUR` e
  `MAX_MESSAGES_PER_HOUR`) e horário de silêncio (`QUIET_HOURS_*`).
- Cada ronda é uma chamada ao Claude e tem custo. Ajuste `HEARTBEAT_MINUTES`; com `0`, desliga.

## Estrutura

```
jarvis/
  server.py     webhooks WhatsApp/voz + inicia a ronda
  brain.py      ponte para o Claude Code (Agent SDK), sessão persistente
  heartbeat.py  ronda autônoma (iniciativa própria)
  tools.py      ferramentas extras: send_whatsapp, call_owner, system_status
  comms.py      Twilio + limites
  monitor.py    CPU, RAM, disco, bateria
  memory.py     diário no Obsidian + IDs de sessão
vault/          memória (vault do Obsidian)
tests/          pytest
```

## Próximos passos sugeridos

- Voz mais natural e em tempo real (Twilio Media Streams + ElevenLabs/OpenAI Realtime) no lugar do `<Say>`.
- Transcrever áudios do WhatsApp (hoje o link da mídia é repassado ao Claude).
- Rodar como serviço (systemd/launchd) para ele ficar sempre ligado.

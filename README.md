# Infinite Jarvis

Assistente pessoal que **fala com você por WhatsApp e por ligação com voz em tempo real**, pensa com
o **Claude Code** e guarda a memória no **Obsidian**. Ele tem **iniciativa própria**: a cada X minutos
acorda sozinho, olha o computador, os lembretes e a rotina, e decide se precisa te mandar mensagem ou te ligar.

```
                 ┌── WhatsApp (Baileys: QR code, sem API oficial) ──┐
 Você ───────────┤                                                  ├──► servidor Jarvis (FastAPI)
                 └── Ligação ─► Twilio ─► ElevenLabs Agent (voz     │          │
                                          em tempo real) ── tool ───┘          ▼
                                                              Claude Code dentro do vault
                                                              ├─ notas  → memória (Obsidian)
                                                              ├─ Bash   → olha o computador
                                                              └─ send_whatsapp / call_owner
                                       Ronda autônoma a cada 15 min ┘  ← iniciativa própria
```

## O que ele faz

| Você                                   | Jarvis                                                                      |
|----------------------------------------|-----------------------------------------------------------------------------|
| Manda WhatsApp (texto, áudio ou foto)  | Transcreve o áudio (ElevenLabs Scribe), vê a foto e responde no WhatsApp    |
| Liga para o número do Jarvis           | Conversa por voz em tempo real (ElevenLabs) e consulta o Claude quando precisa |
| "Me liga amanhã às 9h pra lembrar X"   | Anota em `Jarvis/Lembretes.md` e **te liga sozinho** na hora                |
| Nada                                   | Faz a ronda: disco cheio, bateria baixa, lembretes vencidos e rotina        |

**Como funciona a voz em tempo real:** quem fala com você é um agente da ElevenLabs com um modelo
rápido (`claude-haiku-4-5` por padrão). Por isso não há atraso para ouvir e responder. Quando precisa
de memória, lembretes ou do computador, ele chama a ferramenta `jarvis`, que é o Claude Code no seu
vault, e enquanto isso diz algo como "deixa eu ver". Ao fim da ligação, a transcrição vai para o
diário e o Claude guarda na memória o que for importante.

## Rodando no GitHub Codespaces

1. **Cadastre os secrets** em github.com → Settings → Codespaces → Secrets e libere-os para este
   repositório: `ANTHROPIC_API_KEY`, `OWNER_PHONE`, `OWNER_NAME`, `ELEVENLABS_API_KEY`,
   `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` e `TWILIO_PHONE_NUMBER`. O Codespace também pede esses
   valores na criação.
2. **Crie o Codespace:** botão verde *Code* → *Codespaces* → *Create codespace on main*. Ele instala
   tudo (Python, Node, Claude Code, Baileys) e já **sobe o Jarvis sozinho** em segundo plano.
3. **Conecte o WhatsApp:** no terminal, rode `tail -f logs/whatsapp.log` e escaneie o QR code em
   WhatsApp → Aparelhos conectados → Conectar aparelho. Se o QR ficar ruim no terminal, defina
   `BAILEYS_PAIRING_NUMBER` e use o código de pareamento.
4. **Ligue a voz:** rode `python -m jarvis setup-elevenlabs`. Esse comando cria o agente e a
   ferramenta e importa o seu número Twilio na ElevenLabs. Pode rodar de novo quando quiser (ele
   atualiza em vez de duplicar).
5. **Teste:** mande um "oi" no WhatsApp e rode `python -m jarvis ligar "Jarvis online, chefe."`.

Comandos úteis: `bash scripts/start.sh` (reinicia), `bash scripts/start.sh stop` e `tail -f logs/*.log`.

> **Importante: o Codespace não é um servidor 24h.** Ele desliga depois de um tempo sem uso (padrão de
> 30 min, máximo de 4 h, ajustável em Settings → Codespaces) e, quando ele para, o Jarvis para junto.
> O plano gratuito dá cerca de 60 h por mês num Codespace de 2 núcleos. Para religar sozinho existe o
> workflow `.github/workflows/keep-alive.yml` (veja as instruções no arquivo). Ficar ligado 24h passa
> da cota gratuita e gera cobrança. Para um Jarvis permanente de verdade, uma VPS barata roda
> exatamente os mesmos `scripts/setup.sh` e `scripts/start.sh`.

### Webhooks opcionais da ElevenLabs (painel → Agents → Settings)

- **Início de conversa** (entrega a memória ao agente quando *você* liga):
  `https://SUA-URL/elevenlabs/init`, com o header `X-Jarvis-Secret` igual ao conteúdo de `.jarvis_state/secret`.
- **Pós-ligação** (transcrição no diário e na memória): `https://SUA-URL/elevenlabs/post-call`.
  Copie o segredo HMAC para `ELEVENLABS_WEBHOOK_SECRET`.

## Memória no Obsidian

Todas as conversas ficam em `vault/Diario/AAAA-MM-DD.md`. O que ele aprende vai para
`vault/Jarvis/Perfil.md`, `vault/Pessoas/` e `vault/Projetos/`, e as fotos para `vault/Anexos/`. A
personalidade e as regras ficam em `vault/CLAUDE.md`.

Para ver a memória no seu Obsidian, no PC ou no celular, enquanto o Jarvis roda no Codespace:

- Defina `VAULT_GIT_SYNC=true`: a cada ronda o Jarvis faz commit e push do vault.
- No Obsidian, abra este repositório como vault e instale o plugin **Obsidian Git** para puxar as mudanças.
- **Deixe o repositório privado**, porque a sua memória pessoal vai para o GitHub.

## Rodando no seu computador ou numa VPS

```bash
bash scripts/setup.sh   # instala tudo
nano .env               # preencha
bash scripts/start.sh   # sobe servidor + WhatsApp
ngrok http 8000         # se não houver URL pública: coloque a URL gerada em PUBLIC_URL e rode o setup-elevenlabs
```

Teste sem nenhum serviço externo: `python -m jarvis chat` (terminal) e `python -m jarvis ronda`.

## Alternativas via Twilio

- `WHATSAPP_PROVIDER=twilio`: WhatsApp pela API oficial da Twilio. Webhook: `https://SUA-URL/whatsapp`.
- `VOICE_PROVIDER=twilio`: voz simples com `<Say>`, sem ElevenLabs. Webhook do número: `https://SUA-URL/voice`.
  Rodar o `setup-elevenlabs` aponta o número para a ElevenLabs; para voltar, troque o webhook no painel da Twilio.

## Segurança e limites

- **Só o seu número é atendido.** Isso vale no Baileys, nos webhooks da Twilio (com assinatura
  validada) e na ferramenta de voz, que confere o número da ligação. Se outra pessoa ligar, o agente
  conversa, mas não tem acesso a memória nem ao computador.
- **A comunicação interna é protegida** pelo segredo `JARVIS_SECRET`, compartilhado entre os
  serviços. O webhook pós-ligação é validado por HMAC.
- **O Claude roda com `permission_mode="dontAsk"`.** Só as ferramentas listadas em `jarvis/brain.py`
  ficam liberadas, e essa lista **inclui `Bash`**. Rode o Jarvis numa máquina de confiança.
- **O Baileys não é oficial.** O WhatsApp pode banir números que usam automação. Prefira um chip
  separado para o Jarvis. Usar o seu próprio número também funciona: aí você fala com ele no chat
  "Você" (mensagens para si mesmo).
- **Há limites contra spam:** ligações e mensagens por hora (`MAX_CALLS_PER_HOUR` e
  `MAX_MESSAGES_PER_HOUR`) e horário de silêncio (`QUIET_HOURS_*`). Cada ronda e cada minuto de
  ligação têm custo de uso.

## Estrutura

```
jarvis/
  server.py     webhooks: Baileys, ElevenLabs (tool/init/post-call), Twilio + inicia a ronda
  brain.py      ponte para o Claude Code (Agent SDK), sessões persistentes
  eleven.py     ElevenLabs: setup do agente, ligação de saída, transcrição de áudios
  heartbeat.py  ronda autônoma (iniciativa própria)
  tools.py      ferramentas extras: send_whatsapp, call_owner, system_status
  comms.py      roteia WhatsApp (Baileys/Twilio) e ligações (ElevenLabs/Twilio) + limites
  monitor.py    CPU, RAM, disco, bateria
  memory.py     diário, resumo de contexto e sync do vault com o GitHub
whatsapp/       ponte Baileys (Node)
scripts/        setup.sh e start.sh (usados pelo Codespaces)
.devcontainer/  configuração do Codespaces
vault/          memória (vault do Obsidian)
tests/          pytest
```

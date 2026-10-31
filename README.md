# Infinite Jarvis

Assistente pessoal **100% grátis** que fala com você pelo **WhatsApp** e por **chamada de voz em tempo
real**. Ele pensa com o **Claude Code** e guarda a memória no **Obsidian**. Também tem **iniciativa
própria**: a cada X minutos acorda sozinho, olha o computador, os lembretes e a rotina, e decide se
precisa te mandar mensagem ou te ligar.

```
                ┌── WhatsApp (Baileys: QR code, grátis) ─────────────────┐
 Você ──────────┤                                                        ├─► servidor Jarvis
 (celular)      └── App de chamada (navegador/PWA) ⇄ WebSocket ⇄ Whisper ┘        │
                         ▲ notificação push "📞 Jarvis ligando"   + Piper          ▼
                         │                                       (voz local) Claude Code no vault
                         └──────────── ronda autônoma a cada 15 min ◄──── ├─ notas → memória (Obsidian)
                                                                          ├─ Bash  → olha o computador
                                                                          └─ send_whatsapp / call_owner
```

## Ligação grátis, sem número de telefone

Não existe número de telefone de verdade grátis com API de voz: Twilio e similares cobram pelo número
e pelo minuto. Por isso o Jarvis tem o **próprio app de chamada**:

- Ele roda no navegador do celular e dá para **instalar na tela inicial** (Android/Chrome ou
  iPhone com iOS 16.4+, pelo menu Compartilhar → Adicionar à Tela de Início).
- **Quando o Jarvis quer te ligar**, chega uma **notificação push** "📞 Jarvis ligando" com
  vibração, e também um WhatsApp com o link. Você toca, depois toca em **ATENDER**, e conversa.
- **Quando você quer falar com ele**, abra o app e toque em **LIGAR**.
- A voz é **local e leve**: o [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
  (modelo `base`, cerca de 150 MB) ouve e o [Piper](https://github.com/OHF-Voice/piper1-gpl) (voz
  `pt_BR-faber-medium`, cerca de 60 MB) fala, tudo na CPU, sem pagar nada. Você pode interromper o
  Jarvis falando por cima.

O tempo de resposta é o tempo que o Claude leva para pensar, normalmente alguns segundos. Enquanto
isso o Jarvis diz "Hum, deixa eu ver".

## Rodando no GitHub Codespaces

1. Cadastre os secrets em github.com → Settings → Codespaces → Secrets: `ANTHROPIC_API_KEY` (ou
   rode `claude login` depois), `OWNER_PHONE` e `OWNER_NAME`.
2. Crie o Codespace: botão verde *Code* → *Codespaces* → *Create codespace*. Ele instala tudo
   (Python, Node, Claude Code, Baileys e os modelos de voz) e **sobe o Jarvis sozinho**.
3. **Conecte o WhatsApp:** rode `tail -f logs/whatsapp.log` e escaneie o QR code em WhatsApp →
   Aparelhos conectados.
4. **Instale o app de chamada:** rode `python -m jarvis link --whatsapp`. O link chega no seu
   WhatsApp. Abra no celular, toque em **🔔 Ativar notificações** e adicione o app à tela inicial.
   Na primeira visita, o GitHub mostra um aviso sobre a porta do Codespace: toque em *Continue*.
5. **Teste:** `python -m jarvis ligar "Jarvis online, chefe."`.

Comandos úteis: `bash scripts/start.sh` (reinicia), `bash scripts/start.sh stop`, `tail -f logs/*.log`
e `python -m jarvis modelos` (baixa os modelos de voz de novo).

> **O Codespace não é um servidor 24h.** Ele desliga depois de um tempo sem uso (padrão de 30 min,
> máximo de 4 h, ajustável em Settings → Codespaces), e o Jarvis para junto. O plano gratuito dá
> cerca de 60 h por mês num Codespace de 2 núcleos. O workflow `.github/workflows/keep-alive.yml`
> religa o Codespace sozinho (veja as instruções no arquivo), mas ficar ligado 24h passa da cota
> gratuita. Para um Jarvis permanente e grátis, o *Always Free* da Oracle Cloud (VM ARM) roda os
> mesmos `scripts/setup.sh` e `scripts/start.sh`.
>
> Se você recriar o Codespace, a URL muda: rode `python -m jarvis link --whatsapp` e ative as
> notificações de novo.

## Memória no Obsidian

Todas as conversas ficam em `vault/Diario/AAAA-MM-DD.md`. O que ele aprende vai para
`vault/Jarvis/Perfil.md`, `vault/Pessoas/` e `vault/Projetos/`, e as fotos para `vault/Anexos/`. A
personalidade e as regras ficam em `vault/CLAUDE.md`.

Para ver a memória no Obsidian do PC ou do celular, defina `VAULT_GIT_SYNC=true`: a cada ronda o
Jarvis faz commit e push do vault. No Obsidian, abra o repositório como vault e use o plugin
**Obsidian Git**. **Deixe o repositório privado.**

## Rodando no seu computador ou numa VPS

```bash
bash scripts/setup.sh   # instala tudo e baixa os modelos de voz
nano .env               # preencha
bash scripts/start.sh   # sobe servidor + WhatsApp e mostra o link do app
```

O app de chamada precisa de HTTPS para usar o microfone e as notificações. Fora do Codespaces, use
`cloudflared tunnel --url http://localhost:8000` (grátis) e coloque a URL em `PUBLIC_URL`.

Teste sem nada externo: `python -m jarvis chat` (terminal) e `python -m jarvis ronda`.

## Opcionais pagos

O código continua aceitando serviços pagos, se um dia você quiser:

- `VOICE_PROVIDER=elevenlabs`: voz da ElevenLabs num número Twilio de verdade. Rode
  `python -m jarvis setup-elevenlabs`.
- `VOICE_PROVIDER=twilio`: número Twilio com voz simples (`<Say>`). Webhook: `/voice`.
- `WHATSAPP_PROVIDER=twilio`: WhatsApp pela API oficial. Webhook: `/whatsapp`.

## Segurança e limites

- **Só você é atendido.** No WhatsApp, a ponte Baileys só repassa o seu número. O app de chamada
  exige o token do seu link, que fica guardado no aparelho; quem não tiver o link não entra.
- **O Claude roda com `permission_mode="dontAsk"`.** Só as ferramentas listadas em `jarvis/brain.py`
  ficam liberadas, e essa lista **inclui `Bash`**. Rode o Jarvis numa máquina de confiança.
- **O Baileys não é oficial.** O WhatsApp pode banir números que usam automação. Prefira um chip
  separado para o Jarvis. Com o seu próprio número, você fala com ele no chat "Você".
- **Há limites contra spam:** ligações e mensagens por hora e horário de silêncio
  (`MAX_CALLS_PER_HOUR`, `MAX_MESSAGES_PER_HOUR` e `QUIET_HOURS_*`).
- **Nem tudo é grátis:** o Claude (cérebro) é o único custo. Use a sua assinatura via `claude login`
  ou uma chave de API.

## Estrutura

```
jarvis/
  server.py     rotas: Baileys, app de chamada (WebSocket), webhooks opcionais + inicia a ronda
  webcall.py    chamada pelo navegador: VAD, interrupção, push "Jarvis ligando"
  localvoice.py voz local: Whisper (ouvir) e Piper (falar)
  brain.py      ponte para o Claude Code (Agent SDK), sessões persistentes
  heartbeat.py  ronda autônoma (iniciativa própria)
  tools.py      ferramentas extras: send_whatsapp, call_owner, system_status
  comms.py      roteia WhatsApp e ligações + limites
  monitor.py    CPU, RAM, disco, bateria
  memory.py     diário, resumo de contexto e sync do vault com o GitHub
  eleven.py     (opcional, pago) ElevenLabs
  static/       o app de chamada (PWA)
whatsapp/       ponte Baileys (Node)
scripts/        setup.sh e start.sh (usados pelo Codespaces)
.devcontainer/  configuração do Codespaces
vault/          memória (vault do Obsidian)
tests/          pytest
```

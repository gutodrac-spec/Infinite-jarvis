// Ponte WhatsApp do Jarvis via Baileys (WhatsApp Web, sem API oficial).
// - Recebe mensagens do dono e repassa ao servidor Python (POST /baileys/incoming)
// - Expõe POST /send em localhost para o Jarvis mandar mensagens
import http from 'node:http'
import makeWASocket, {
  DisconnectReason,
  downloadMediaMessage,
  fetchLatestBaileysVersion,
  useMultiFileAuthState,
} from 'baileys'
import pino from 'pino'
import qrcode from 'qrcode-terminal'

const OWNER = (process.env.OWNER_PHONE || '').replace(/\D/g, '')
const SECRET = process.env.JARVIS_SECRET || ''
const JARVIS_URL = process.env.JARVIS_INTERNAL_URL || 'http://127.0.0.1:8000'
const PORT = Number(process.env.BAILEYS_PORT || 3001)
const AUTH_DIR = process.env.BAILEYS_AUTH_DIR || './auth'
const PAIRING_NUMBER = (process.env.BAILEYS_PAIRING_NUMBER || '').replace(/\D/g, '')

const logger = pino({ level: process.env.BAILEYS_LOG_LEVEL || 'warn' })
let sock = null
let ownerJid = null
const sentByJarvis = new Set() // evita loop quando o Jarvis usa a mesma conta do dono

// Celulares do Brasil: o WhatsApp às vezes guarda o número sem o 9 depois do DDD.
const withoutBr9 = (d) => (d.length === 13 && d.startsWith('55') ? d.slice(0, 4) + d.slice(5) : d)
const samePhone = (a, b) => a && b && (a === b || withoutBr9(a) === withoutBr9(b))
const digits = (jid) => (jid || '').split('@')[0].split(':')[0]

function isFromOwner(msg) {
  const k = msg.key
  const own = digits(sock.user?.id)
  const chat = [k.remoteJid, k.remoteJidAlt].map(digits)
  // Caso 1: o Jarvis tem um número próprio e o dono manda mensagem para ele.
  if (!k.fromMe) return [k.remoteJid, k.remoteJidAlt, k.participant, k.participantAlt].map(digits).some((d) => samePhone(d, OWNER))
  // Caso 2: o Jarvis usa a conta do próprio dono, que fala com ele no chat "Você" (mensagens para si mesmo).
  return samePhone(own, OWNER) && chat.some((d) => samePhone(d, own)) && !sentByJarvis.has(k.id)
}

function textOf(m) {
  return (
    m?.conversation ||
    m?.extendedTextMessage?.text ||
    m?.imageMessage?.caption ||
    m?.videoMessage?.caption ||
    m?.documentMessage?.caption ||
    ''
  )
}

async function forward(msg) {
  const m = msg.message?.ephemeralMessage?.message || msg.message
  const payload = { text: textOf(m), id: msg.key.id }
  for (const [kind, node] of [['audio', m?.audioMessage], ['image', m?.imageMessage]]) {
    if (!node) continue
    const buf = await downloadMediaMessage(msg, 'buffer', {}, { logger, reuploadRequest: sock.updateMediaMessage })
    payload[`${kind}_b64`] = buf.toString('base64')
    payload[`${kind}_mime`] = node.mimetype
  }
  if (!payload.text && !payload.audio_b64 && !payload.image_b64) return
  ownerJid = msg.key.remoteJid
  await sock.sendPresenceUpdate('composing', ownerJid).catch(() => {})
  const res = await fetch(`${JARVIS_URL}/baileys/incoming`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-jarvis-secret': SECRET },
    body: JSON.stringify(payload),
  })
  if (!res.ok) logger.error({ status: res.status }, 'Jarvis recusou a mensagem')
}

async function resolveOwnerJid() {
  if (ownerJid) return ownerJid
  const [hit] = (await sock.onWhatsApp(OWNER)) || []
  ownerJid = hit?.exists ? hit.jid : `${OWNER}@s.whatsapp.net`
  return ownerJid
}

async function sendToOwner(text) {
  const jid = await resolveOwnerJid()
  await sock.sendPresenceUpdate('paused', jid).catch(() => {})
  const sent = await sock.sendMessage(jid, { text })
  sentByJarvis.add(sent.key.id)
  if (sentByJarvis.size > 500) sentByJarvis.delete(sentByJarvis.values().next().value)
}

async function connect() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR)
  const { version } = await fetchLatestBaileysVersion()
  sock = makeWASocket({ version, auth: state, logger, markOnlineOnConnect: false })
  sock.ev.on('creds.update', saveCreds)

  sock.ev.on('connection.update', async ({ connection, lastDisconnect, qr }) => {
    if (qr && !PAIRING_NUMBER) {
      console.log('\nEscaneie no WhatsApp > Aparelhos conectados > Conectar aparelho:\n')
      qrcode.generate(qr, { small: true })
    }
    if (qr && PAIRING_NUMBER && !state.creds.registered) {
      const code = await sock.requestPairingCode(PAIRING_NUMBER)
      console.log(`\nCódigo de pareamento: ${code}\nWhatsApp > Aparelhos conectados > Conectar com número de telefone\n`)
    }
    if (connection === 'open') console.log(`WhatsApp conectado como ${digits(sock.user?.id)}`)
    if (connection === 'close') {
      const code = lastDisconnect?.error?.output?.statusCode
      if (code === DisconnectReason.loggedOut) {
        console.error(`Sessão encerrada no celular. Apague ${AUTH_DIR} e conecte de novo.`)
        process.exit(1)
      }
      setTimeout(connect, 2000)
    }
  })

  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    if (type !== 'notify') return
    for (const msg of messages) {
      if (!msg.message || !isFromOwner(msg)) continue
      forward(msg).catch((err) => logger.error({ err }, 'Falha ao repassar mensagem'))
    }
  })
}

http
  .createServer((req, res) => {
    if (req.method !== 'POST' || req.url !== '/send' || req.headers['x-jarvis-secret'] !== SECRET) {
      res.writeHead(404).end()
      return
    }
    let body = ''
    req.on('data', (c) => (body += c))
    req.on('end', async () => {
      try {
        await sendToOwner(JSON.parse(body).text)
        res.writeHead(200).end('ok')
      } catch (err) {
        logger.error({ err }, 'Falha ao enviar')
        res.writeHead(503).end(String(err))
      }
    })
  })
  .listen(PORT, '127.0.0.1', () => console.log(`Ponte WhatsApp ouvindo em 127.0.0.1:${PORT}`))

if (!OWNER || !SECRET) {
  console.error('Defina OWNER_PHONE e JARVIS_SECRET.')
  process.exit(1)
}
connect()

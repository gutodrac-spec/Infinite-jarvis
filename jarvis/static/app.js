// App de chamada do Jarvis: microfone → WebSocket (PCM 16 kHz) → Jarvis → voz de volta.
const RATE = 16000

// O token vem no link (#k=...) uma vez e fica guardado no aparelho.
const hash = new URLSearchParams(location.hash.slice(1))
if (hash.get('k')) {
  try { localStorage.setItem('jarvis-k', hash.get('k')) } catch {}
  history.replaceState(null, '', location.pathname + location.search)
}
let TOKEN = null
try { TOKEN = localStorage.getItem('jarvis-k') } catch {}

const $ = (id) => document.getElementById(id)
const status = (t) => ($('status').textContent = t)
const say = (who, text) => {
  const div = document.createElement('div')
  div.className = `msg ${who}`
  div.textContent = text
  $('log').prepend(div)
}

let ws = null, ctx = null, mic = null, nextTime = 0, playing = new Set(), hangupAfterPlay = false

function playPcm(buf) {
  const pcm = new Int16Array(buf)
  const audio = ctx.createBuffer(1, pcm.length, RATE)
  const ch = audio.getChannelData(0)
  for (let i = 0; i < pcm.length; i++) ch[i] = pcm[i] / 32768
  const src = ctx.createBufferSource()
  src.buffer = audio
  src.connect(ctx.destination)
  nextTime = Math.max(nextTime, ctx.currentTime + 0.05)
  src.start(nextTime)
  nextTime += audio.duration
  playing.add(src)
  src.onended = () => {
    playing.delete(src)
    if (playing.size === 0) finishedPlaying()
  }
}

function finishedPlaying() {
  ws?.readyState === 1 && ws.send(JSON.stringify({ type: 'played' }))
  if (hangupAfterPlay) hangup()
}

function stopPlayback() {
  for (const src of playing) { src.onended = null; src.stop() }
  playing.clear()
  nextTime = 0
  finishedPlaying()
}

async function call() {
  if (!TOKEN) return status('Abra o link que o Jarvis te mandou para entrar.')
  document.body.classList.remove('ringing')
  status('Conectando...')
  ctx = new AudioContext({ sampleRate: RATE })
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  })
  await ctx.audioWorklet.addModule('worklet.js')
  const node = new AudioWorkletNode(ctx, 'mic')
  const mute = ctx.createGain()
  mute.gain.value = 0
  ctx.createMediaStreamSource(stream).connect(node).connect(mute).connect(ctx.destination)
  mic = { stream, node }

  ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/app/ws`)
  ws.binaryType = 'arraybuffer'
  ws.onopen = () => {
    ws.send(JSON.stringify({ k: TOKEN }))
    document.body.classList.add('incall')
    $('label').textContent = 'DESLIGAR'
    status('Em chamada')
    node.port.onmessage = (e) => {
      if (ws.readyState === 1) ws.send(e.data.pcm)
      document.body.style.setProperty('--level', Math.min(1, e.data.level * 4).toFixed(2))
    }
  }
  ws.onmessage = (e) => {
    if (typeof e.data !== 'string') return playPcm(e.data)
    const msg = JSON.parse(e.data)
    if (msg.type === 'you') { say('you', msg.text); status('Pensando...') }
    if (msg.type === 'jarvis') { say('jarvis', msg.text); status('Em chamada'); hangupAfterPlay = !!msg.end }
    if (msg.type === 'clear') stopPlayback()
  }
  ws.onclose = (e) => {
    if (e.code === 4401) status('Link inválido. Peça um novo: python -m jarvis link')
    hangup()
  }
}

function hangup() {
  if (ws?.readyState === 1) ws.send(JSON.stringify({ type: 'hangup' }))
  ws?.close()
  ws = null
  mic?.stream.getTracks().forEach((t) => t.stop())
  mic = null
  ctx?.close()
  ctx = null
  playing.clear()
  hangupAfterPlay = false
  document.body.classList.remove('incall')
  $('label').textContent = 'LIGAR'
  if (!$('status').textContent.startsWith('Link')) status('Chamada encerrada.')
}

$('reactor').onclick = () => (ws ? hangup() : call().catch((err) => { status('Erro: ' + err.message); hangup() }))

// Chegou pela notificação "Jarvis ligando": mostra o botão pulsando (navegador exige um toque para abrir o microfone).
if (new URLSearchParams(location.search).get('call')) {
  document.body.classList.add('ringing')
  $('label').textContent = 'ATENDER'
  status('📞 O Jarvis está te ligando')
}

// ---------- Notificações push ----------
const b64ToBytes = (s) => {
  const raw = atob((s + '='.repeat((4 - (s.length % 4)) % 4)).replace(/-/g, '+').replace(/_/g, '/'))
  return Uint8Array.from(raw, (c) => c.charCodeAt(0))
}

async function setupPush(ask) {
  if (!('serviceWorker' in navigator) || !('PushManager' in window) || !TOKEN) return
  const reg = await navigator.serviceWorker.register('sw.js')
  if (Notification.permission === 'default' && !ask) return ($('push').hidden = false)
  if ((await Notification.requestPermission()) !== 'granted') return
  const { vapid } = await (await fetch('config')).json()
  const sub = (await reg.pushManager.getSubscription()) ||
    (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToBytes(vapid) }))
  await fetch('subscribe', {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-app-token': TOKEN },
    body: JSON.stringify(sub),
  })
  $('push').hidden = true
}

$('push').onclick = () => setupPush(true).catch((err) => status('Notificações: ' + err.message))
setupPush(false).catch(() => {})

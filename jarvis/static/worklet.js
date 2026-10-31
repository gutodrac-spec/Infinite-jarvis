// Captura do microfone: junta blocos de 128 amostras em pacotes de 40 ms (PCM 16 bits) e manda para a página.
class Mic extends AudioWorkletProcessor {
  constructor() {
    super()
    this.buf = new Int16Array(640)
    this.n = 0
    this.sum = 0
  }
  process(inputs) {
    const ch = inputs[0][0]
    if (!ch) return true
    for (let i = 0; i < ch.length; i++) {
      const s = Math.max(-1, Math.min(1, ch[i]))
      this.buf[this.n++] = s * 32767
      this.sum += s * s
      if (this.n === this.buf.length) {
        const pcm = this.buf.slice().buffer
        this.port.postMessage({ pcm, level: Math.sqrt(this.sum / this.n) }, [pcm])
        this.n = 0
        this.sum = 0
      }
    }
    return true
  }
}
registerProcessor('mic', Mic)

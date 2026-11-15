// 很輕的聲音：秒針、找到東西時的一個音、倒帶時加快的滴答。全部用 WebAudio 合成，沒有音檔。
let ctx = null
let master = null
let enabled = true

export function initAudio() {
  if (ctx) return
  const AC = window.AudioContext || window.webkitAudioContext
  if (!AC) return
  ctx = new AC()
  master = ctx.createGain()
  master.gain.value = enabled ? 0.5 : 0
  master.connect(ctx.destination)
}

export const audioCtx = () => ctx
export const masterNode = () => master

export function setEnabled(on) {
  enabled = on
  if (master) master.gain.setTargetAtTime(on ? 0.5 : 0, ctx.currentTime, 0.05)
}

function blip(freq, dur, gain, type = 'sine') {
  if (!ctx || !enabled) return
  const t = ctx.currentTime
  const osc = ctx.createOscillator()
  const g = ctx.createGain()
  osc.type = type
  osc.frequency.setValueAtTime(freq, t)
  g.gain.setValueAtTime(0, t)
  g.gain.linearRampToValueAtTime(gain, t + 0.008)
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur)
  osc.connect(g).connect(master)
  osc.start(t)
  osc.stop(t + dur + 0.02)
}

// 秒針。倒帶時 pitch 高一點、短一點。
export function tick(fast = false) {
  blip(fast ? 1900 : 1250, fast ? 0.03 : 0.05, fast ? 0.05 : 0.07, 'triangle')
}

// 找到一樣東西：五聲音階裡的一個音，越找越高。
const SCALE = [392, 440, 523.25, 587.33, 659.25, 783.99]
export function chime(step = 0) {
  const f = SCALE[step % SCALE.length]
  blip(f, 1.6, 0.16)
  blip(f * 2, 1.1, 0.04)
}

// 時間線改變的那一刻。
export function resolve() {
  ;[392, 523.25, 659.25].forEach((f, i) => setTimeout(() => blip(f, 2.4, 0.13), i * 160))
}

// 電鈴：叮——咚。inside 是從門後聽到的版本，比較響、比較悶。
export function doorbell(inside = false) {
  const g = inside ? 0.2 : 0.12
  blip(659.25, 1.1, g)
  blip(1318.5, 0.5, g * 0.25)
  setTimeout(() => {
    blip(523.25, 1.5, g)
    blip(1046.5, 0.6, g * 0.25)
  }, 420)
}

// 手機鈴聲：兩個音很快地交替。inside 是在桌上、就在旁邊響的版本。
export function phoneRing(inside = false) {
  const g = inside ? 0.11 : 0.035
  for (let i = 0; i < 14; i++) setTimeout(() => blip(i % 2 ? 1320 : 1568, 0.07, g, 'triangle'), i * 85)
}

// 撥出去之後的等待音：嘟——
export function dialTone() {
  blip(440, 0.95, 0.07)
  blip(480, 0.95, 0.05)
}

// 鑰匙插進鎖孔、轉開
export function keys() {
  ;[2400, 3100, 2700, 1900].forEach((f, i) => setTimeout(() => blip(f, 0.05, 0.04, 'square'), i * 110))
  setTimeout(() => blip(180, 0.12, 0.12, 'square'), 620)
}

// 門慢慢打開
export function creak() {
  if (!ctx || !enabled) return
  const t = ctx.currentTime
  const o = ctx.createOscillator()
  const g = ctx.createGain()
  const lp = ctx.createBiquadFilter()
  lp.type = 'bandpass'
  lp.frequency.value = 700
  lp.Q.value = 6
  o.type = 'sawtooth'
  o.frequency.setValueAtTime(70, t)
  o.frequency.linearRampToValueAtTime(128, t + 0.9)
  o.frequency.linearRampToValueAtTime(92, t + 1.7)
  g.gain.setValueAtTime(0, t)
  g.gain.linearRampToValueAtTime(0.09, t + 0.25)
  g.gain.linearRampToValueAtTime(0, t + 1.8)
  o.connect(lp).connect(g).connect(master)
  o.start(t)
  o.stop(t + 1.9)
}

// 電視裡的人在講話：聽不清楚內容，只聽得出有人聲
export function murmur(seconds = 5) {
  if (!ctx || !enabled) return
  const t = ctx.currentTime
  const len = Math.floor(ctx.sampleRate * seconds)
  const buf = ctx.createBuffer(1, len, ctx.sampleRate)
  const d = buf.getChannelData(0)
  for (let i = 0; i < len; i++) {
    const s = i / ctx.sampleRate
    // 一個音節一個音節的起伏，偶爾停頓換氣
    const syll = Math.max(0, Math.sin(s * 2 * Math.PI * 4.3 + Math.sin(s * 1.7) * 2))
    const phrase = Math.sin(s * 0.9 + 1) > -0.55 ? 1 : 0.1
    d[i] = (Math.random() * 2 - 1) * syll * phrase
  }
  const src = ctx.createBufferSource()
  src.buffer = buf
  const bp = ctx.createBiquadFilter()
  bp.type = 'bandpass'
  bp.frequency.value = 620
  bp.Q.value = 1.6
  const g = ctx.createGain()
  g.gain.setValueAtTime(0, t)
  g.gain.linearRampToValueAtTime(0.085, t + 0.4)
  g.gain.setValueAtTime(0.085, t + seconds - 0.8)
  g.gain.linearRampToValueAtTime(0, t + seconds)
  src.connect(bp).connect(g).connect(master)
  src.start(t)
}

// 救護車：兩個音交替，由近而遠
export function siren(seconds = 7) {
  if (!ctx || !enabled) return
  const t = ctx.currentTime
  const o = ctx.createOscillator()
  const g = ctx.createGain()
  o.type = 'triangle'
  for (let k = 0; k * 0.55 < seconds; k++) o.frequency.setValueAtTime(k % 2 ? 690 : 920, t + k * 0.55)
  g.gain.setValueAtTime(0, t)
  g.gain.linearRampToValueAtTime(0.07, t + 0.6)
  g.gain.linearRampToValueAtTime(0.0001, t + seconds)
  o.connect(g).connect(master)
  o.start(t)
  o.stop(t + seconds + 0.1)
}

// 配樂：一首很慢的小調，鋼琴加一層很薄的弦樂，全部用 WebAudio 合成，沒有音檔。
//
// 八小節循環。平常是 A 小調（Am – Em/G – F – C/E – Dm – Am/C – Esus – E），
// 他活下來的那條時間線會轉成 C 大調，旋律往上走。
// 按住倒帶時，音樂也跟著倒著走：小節往回數、速度加倍、每個音由弱漸強再突然收掉。
//
// setMood({ mode, layer, slow, rewind })
//   mode   'minor' | 'major'
//   layer  0：只有弦樂和低音　1：加上分解和弦　2：再加上旋律
//   slow   夜裡放慢
//   rewind 倒帶中
import { audioCtx, masterNode } from './audio.js'

const m2f = (m) => 440 * Math.pow(2, (m - 69) / 12)

// 每小節：低音、和弦三個音、旋律 [第幾拍, 音高, 幾拍]
const MINOR = [
  { bass: 45, ch: [57, 60, 64], mel: [[0, 76, 2], [2, 72, 2]] },
  { bass: 43, ch: [59, 64, 67], mel: [[0, 71, 3.5]] },
  { bass: 41, ch: [57, 60, 65], mel: [[0, 69, 1.5], [1.5, 72, 1], [2.5, 69, 1.5]] },
  { bass: 40, ch: [55, 60, 64], mel: [[0, 67, 3.5]] },
  { bass: 38, ch: [57, 62, 65], mel: [[0, 65, 1], [1, 69, 1], [2, 74, 2]] },
  { bass: 48, ch: [57, 60, 64], mel: [[0, 72, 2], [2, 76, 2]] },
  { bass: 40, ch: [57, 59, 64], mel: [[0, 76, 2], [2, 74, 2]] },
  { bass: 40, ch: [56, 59, 64], mel: [[0, 71, 3.5]] },
]
const MAJOR = [
  { bass: 48, ch: [55, 60, 64], mel: [[0, 76, 2], [2, 79, 2]] },
  { bass: 47, ch: [55, 59, 62], mel: [[0, 74, 3.5]] },
  { bass: 45, ch: [57, 60, 64], mel: [[0, 72, 1.5], [1.5, 76, 1], [2.5, 72, 1.5]] },
  { bass: 41, ch: [57, 60, 65], mel: [[0, 69, 3.5]] },
  { bass: 40, ch: [55, 60, 64], mel: [[0, 67, 1], [1, 72, 1], [2, 76, 2]] },
  { bass: 41, ch: [57, 60, 65], mel: [[0, 77, 2], [2, 76, 2]] },
  { bass: 43, ch: [55, 60, 62], mel: [[0, 74, 2], [2, 72, 2]] },
  { bass: 43, ch: [55, 59, 62], mel: [[0, 74, 3.5]] },
]

const state = { mode: 'minor', layer: 1, slow: false, rewind: false }
let ctx = null
let bus = null
let wet = null
let timer = 0
let nextBar = 0
let bar = 0

function makeReverb() {
  const len = Math.floor(ctx.sampleRate * 3.4)
  const buf = ctx.createBuffer(2, len, ctx.sampleRate)
  for (let c = 0; c < 2; c++) {
    const d = buf.getChannelData(c)
    for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 3.2)
  }
  const conv = ctx.createConvolver()
  conv.buffer = buf
  return conv
}

// 鋼琴：基音加兩個泛音，敲下去之後慢慢消失
function piano(midi, t, dur, vel, reversed) {
  const f = m2f(midi)
  const g = ctx.createGain()
  const lp = ctx.createBiquadFilter()
  lp.type = 'lowpass'
  lp.frequency.value = 900 + vel * 9000
  const len = reversed ? 0.5 : dur * 1.6 + 1.4
  if (reversed) {
    g.gain.setValueAtTime(0.0001, t)
    g.gain.exponentialRampToValueAtTime(vel, t + len - 0.03)
    g.gain.linearRampToValueAtTime(0.0001, t + len)
  } else {
    g.gain.setValueAtTime(0.0001, t)
    g.gain.linearRampToValueAtTime(vel, t + 0.008)
    g.gain.exponentialRampToValueAtTime(vel * 0.35, t + 0.5)
    g.gain.exponentialRampToValueAtTime(0.0001, t + len)
  }
  ;[[1, 'sine', 1], [2, 'sine', 0.3], [1.003, 'triangle', 0.22], [3, 'sine', 0.08]].forEach(([mul, type, amp]) => {
    const o = ctx.createOscillator()
    const og = ctx.createGain()
    o.type = type
    o.frequency.value = f * mul
    og.gain.value = amp
    o.connect(og).connect(lp)
    o.start(t)
    o.stop(t + len + 0.05)
  })
  lp.connect(g)
  g.connect(bus)
  g.connect(wet)
}

// 弦樂：兩支微微走音的鋸齒波，濾得很暗，慢慢進來、慢慢離開
function pad(midi, t, len, vel) {
  const g = ctx.createGain()
  const lp = ctx.createBiquadFilter()
  lp.type = 'lowpass'
  lp.frequency.value = 520
  lp.Q.value = 0.4
  g.gain.setValueAtTime(0.0001, t)
  g.gain.linearRampToValueAtTime(vel, t + Math.min(1.6, len * 0.45))
  g.gain.setValueAtTime(vel, t + len - 0.4)
  g.gain.linearRampToValueAtTime(0.0001, t + len + 1.2)
  ;[-7, 7].forEach((cents) => {
    const o = ctx.createOscillator()
    o.type = 'sawtooth'
    o.frequency.value = m2f(midi)
    o.detune.value = cents
    o.connect(lp)
    o.start(t)
    o.stop(t + len + 1.3)
  })
  lp.connect(g)
  g.connect(bus)
  g.connect(wet)
}

function scheduleBar(index, t, beat) {
  const prog = state.mode === 'major' ? MAJOR : MINOR
  const b = prog[((index % 8) + 8) % 8]
  const rev = state.rewind
  const len = beat * 4
  const at = (k) => t + (rev ? 4 - k : k) * beat - (rev ? 0.5 : 0) // 倒帶時，小節裡的順序也倒過來

  b.ch.forEach((m) => pad(m - 12, t, len, 0.02))
  piano(b.bass, rev ? at(0.5) : t, 3, 0.2, rev)
  if (state.layer >= 1) [0, 1, 2, 1, 2, 1].forEach((n, i) => piano(b.ch[n], at(1 + i * 0.5), 0.6, 0.065 + (i % 2) * 0.02, rev))
  if (state.layer >= 2) b.mel.forEach(([k, m, d]) => piano(m, at(k), d, state.slow ? 0.14 : 0.17, rev))
}

function tick() {
  if (!ctx) return
  const beat = state.rewind ? 0.5 : state.slow ? 1.3 : 1.05
  while (nextBar < ctx.currentTime + 0.5) {
    scheduleBar(bar, nextBar, beat)
    nextBar += beat * 4
    bar += state.rewind ? -1 : 1
  }
}

export function startMusic() {
  ctx = audioCtx()
  if (!ctx || timer) return
  bus = ctx.createGain()
  bus.gain.value = 0.7
  wet = ctx.createGain()
  wet.gain.value = 0.55
  const reverb = makeReverb()
  wet.connect(reverb).connect(masterNode())
  bus.connect(masterNode())
  nextBar = ctx.currentTime + 0.3
  bar = 0
  timer = setInterval(tick, 120)
  tick()
}

export function setMood(next) {
  const wasRewind = state.rewind
  Object.assign(state, next)
  // 開始或結束倒帶時，馬上接下一個小節，不要等原本那一小節播完
  if (ctx && wasRewind !== state.rewind) nextBar = Math.min(nextBar, ctx.currentTime + 0.12)
}

export function stopMusic() {
  clearInterval(timer)
  timer = 0
}

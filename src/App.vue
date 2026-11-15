<script setup>
import { ref, computed, reactive, watch, onBeforeUnmount, nextTick } from 'vue'
import Scene from './components/Scene.vue'
import DayPage from './components/DayPage.vue'
import Newspaper from './components/Newspaper.vue'
import CardDeck from './components/CardDeck.vue'
import PhoneScreen from './components/PhoneScreen.vue'
import { chapters, mends, bands, relLabel, alive as aliveText, forwardPass, discovery, finale, FOUND_DAY, LISTING_DAY, BEFORE_DAYS } from './story.js'
import * as audio from './audio.js'
import { startMusic, setMood } from './music.js'

// intro → play（倒著走十一個章節）→ true（時間順著走一次）→ discover（玩家把門打開，他被發現）
//       → mend（把「下次」改成「這次」）→ forward（時間再走一次）→ ending → epilogue（桌上的報紙）→ final（門外，最後一個畫面）
const phase = ref('intro')
const ci = ref(0)
const day = ref(chapters[0].day)
const seen = reactive(new Set()) // 看過的圓點
const note = ref(null)
const soundOn = ref(true)
const caption = ref('')
const moving = ref(false)

const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2)

const chapter = computed(() => chapters[ci.value])
const next = computed(() => chapters[ci.value + 1])
const isLast = computed(() => ci.value === chapters.length - 1)

// ── 倒帶：按住，時間往回走；放開，彈回來 ─────────────────
const hold = ref(false)
const p = ref(0)
let raf = 0 // 倒帶用
let animRaf = 0 // 自動播放用（時間往前），兩個不能共用
let last = 0
let lastTickDay = 0

const shown = computed(() => (p.value > 0.5 && next.value ? next.value : chapter.value))
const seenCount = computed(() => chapter.value.hotspots.filter((h) => seen.has(`${ci.value}:${h.id}`)).length)
const allSeen = computed(() => seenCount.value === chapter.value.hotspots.length)
// 結尾：桌上那份可以拿起來看的報紙
const PAPER = { id: 'paper', at: [3.14, 0.99, -2.36], label: '桌上的報紙' }
const paperOpen = ref(false)
const paperRead = ref(false)
const hotspots = computed(() => {
  if (phase.value === 'play') return chapter.value.hotspots.map((h) => ({ ...h, found: seen.has(`${ci.value}:${h.id}`) }))
  if (phase.value === 'epilogue') return [{ ...PAPER, found: paperRead.value }]
  if (phase.value === 'final' && finalStage.value === 'bell') return [{ ...BELL, found: false }]
  return []
})
const interactive = computed(() => (phase.value === 'play' && p.value === 0 && !ringing.value) || (phase.value === 'epilogue' && !paperOpen.value) || (phase.value === 'final' && finalStage.value === 'bell'))

function frame(t) {
  const dt = Math.min(50, t - last)
  last = t
  p.value = hold.value ? Math.min(1, p.value + dt / 2600) : Math.max(0, p.value - dt / 450)
  day.value = chapter.value.day + (next.value.day - chapter.value.day) * ease(p.value)
  if (Math.round(day.value) !== lastTickDay) {
    lastTickDay = Math.round(day.value)
    if (hold.value) audio.tick(true)
  }
  if (p.value >= 1) return commitRewind()
  if (p.value > 0 || hold.value) raf = requestAnimationFrame(frame)
  else raf = 0
}
function startHold() {
  if (!allSeen.value || phase.value !== 'play' || isLast.value || ringing.value) return
  note.value = null
  if (reduceMotion) return commitRewind()
  hold.value = true
  if (!raf) {
    last = performance.now()
    raf = requestAnimationFrame(frame)
  }
}
function endHold() {
  hold.value = false
}
function commitRewind() {
  run++ // 還在播的橋段到這裡為止
  cancelAnimationFrame(raf)
  raf = 0
  hold.value = false
  p.value = 0
  ci.value += 1
  day.value = chapter.value.day
  note.value = null
}
function onKeyHold(e) {
  if ((e.key === ' ' || e.key === 'Enter') && !e.repeat) {
    e.preventDefault()
    startHold()
  }
}

const aliveCall = ref(false) // 結局裡那支等玩家按下去的手機
let answered = () => {}
const major = ref(false) // 配樂轉成大調
let run = 0 // 玩家中途離開時，讓進行中的播放流程（電鈴、時間往前）自己停下

// ── 互動 ────────────────────────────────────────
function start() {
  wake()
  phase.value = 'play'
  startClock()
}
// 瀏覽器要等使用者動過手才能出聲：第一次點擊時把聲音和配樂叫起來
function wake() {
  audio.initAudio()
  audio.setEnabled(soundOn.value)
  startMusic()
}
window.addEventListener('pointerdown', () => phase.value !== 'intro' && wake(), { once: true })
function toggleSound() {
  soundOn.value = !soundOn.value
  wake()
}

// 配樂跟著場景走：門外只有分解和弦，屋裡才有旋律；夜裡放慢；倒帶時音樂也倒著走；他活下來就轉大調
watch(
  () => {
    if (phase.value === 'play') return { mode: 'minor', layer: shown.value.scene === 'room' ? 2 : 1, slow: shown.value.time === 'night', rewind: hold.value }
    if (phase.value === 'mend' || phase.value === 'discover') return { mode: 'minor', layer: 0, slow: true, rewind: false }
    if (phase.value === 'true') return { mode: 'minor', layer: 2, slow: day.value > -1 && day.value < 1, rewind: false }
    if (phase.value === 'final') return { mode: major.value ? 'major' : 'minor', layer: 1, slow: true, rewind: false }
    return { mode: major.value ? 'major' : 'minor', layer: phase.value === 'intro' ? 1 : 2, slow: !major.value && day.value > -1, rewind: false }
  },
  (m) => setMood(m),
  { immediate: true },
)
function pick(h) {
  if (h.id === 'finalBell') return ringFinal()
  if (h.id === 'paper') {
    paperOpen.value = paperRead.value = true
    audio.tick(false)
    return
  }
  const key = `${ci.value}:${h.id}`
  if (!seen.has(key)) {
    if (h.id !== 'bell') audio.chime(seenCount.value)
    seen.add(key)
  }
  note.value = h
  if (h.cut) playCut(h.cut)
  if (h.tv) audio.murmur(6)
}

// ── 橋段：切到另一個鏡頭（門後、對面、門外），或是房東把門打開 ──────────
const ringing = ref(false) // 橋段進行中（這時不能點別的）
const pressing = ref(false) // 門口的人手在電鈴上
const calling = ref(false) // 桌上的手機在響
const opening = ref(false) // 房東在開門
const arrived = ref(false) // 被發現那天：員警和里長到了門口
const greet = ref(false) // 結尾：他來開門
const shot = ref(null)
const dark = ref(false) // 切鏡頭時的黑幕
async function cutTo(next) {
  dark.value = true
  await wait(380)
  shot.value = next
  dark.value = false
}
async function playCut(c) {
  if (ringing.value) return
  const me = ++run
  const ok = () => me === run && phase.value === 'play'
  ringing.value = true
  if (c.open) {
    // 房東：按電鈴、等、拿鑰匙、開門
    audio.doorbell()
    await wait(2400)
    if (ok()) audio.keys()
    await wait(1300)
    if (ok()) {
      opening.value = true
      audio.creak()
      await wait(c.hold)
    }
    opening.value = false
  } else {
    if (c.press) {
      pressing.value = true
      audio.doorbell()
      await wait(1700)
    }
    if (ok()) {
      await cutTo(c.shot)
      pressing.value = false
      for (let k = 0; k < (c.rings || 0) && ok(); k++) {
        await wait(k ? 2300 : 900)
        if (!ok()) break
        if (c.sound === 'phone') {
          calling.value = true
          audio.phoneRing(true)
        } else {
          audio.doorbell(c.shot === 'inside')
          if (c.shot === 'porch') {
            pressing.value = true
            setTimeout(() => (pressing.value = false), 900)
          }
        }
      }
      await wait(c.hold)
      calling.value = false
      if (shot.value) await cutTo(null)
    }
  }
  shot.value = null
  dark.value = false
  pressing.value = false
  calling.value = false
  ringing.value = false
}

// 平常的秒針
let clock = 0
function startClock() {
  clearInterval(clock)
  clock = setInterval(() => {
    if (phase.value === 'play' && !hold.value) audio.tick(false)
  }, 1000)
}

// ── 倒著看完之後：時間照原來的方向走一次，停在被發現的那一天 ──────────
const trueKind = ref('room')
async function cutDark(fn) {
  dark.value = true
  await wait(380)
  fn()
  dark.value = false
}
async function startTrue() {
  const me = ++run
  note.value = null
  phase.value = 'true'
  trueKind.value = 'room'
  moving.value = true
  day.value = -BEFORE_DAYS
  for (const seg of forwardPass) {
    caption.value = seg.text
    await Promise.all([animateDay(seg.to, seg.ms), wait(seg.ms)])
    if (seg.hold) await wait(seg.hold)
    if (me !== run) return
  }
  await cutDark(() => {
    trueKind.value = 'hall'
    day.value = FOUND_DAY
    caption.value = discovery.arrive
    arrived.value = true
    phase.value = 'discover'
  })
  moving.value = false
}

// 被發現：玩家按住，把門打開
const openP = ref(0)
const openHold = ref(false)
const discovering = ref(false)
let openRaf = 0
let openLast = 0
function openFrame(t) {
  const dt = Math.min(50, t - openLast)
  openLast = t
  openP.value = openHold.value ? Math.min(1, openP.value + dt / 2400) : Math.max(0, openP.value - dt / 500)
  if (openP.value >= 1) return discover()
  if (openP.value > 0 || openHold.value) openRaf = requestAnimationFrame(openFrame)
  else openRaf = 0
}
function startOpen() {
  if (phase.value !== 'discover' || discovering.value) return
  if (reduceMotion) return discover()
  if (!openHold.value && openP.value === 0) audio.keys()
  openHold.value = true
  if (!openRaf) {
    openLast = performance.now()
    openRaf = requestAnimationFrame(openFrame)
  }
}
function endOpen() {
  openHold.value = false
}
function onKeyOpen(e) {
  if ((e.key === ' ' || e.key === 'Enter') && !e.repeat) {
    e.preventDefault()
    startOpen()
  }
}
async function discover() {
  cancelAnimationFrame(openRaf)
  openRaf = 0
  openHold.value = false
  openP.value = 1
  discovering.value = true
  const me = ++run
  opening.value = true
  audio.creak()
  await wait(2800)
  if (me === run) await cutTo('inside')
  for (const line of discovery.inside) {
    if (me !== run) return
    caption.value = line
    await wait(3800)
  }
  if (me !== run) return
  // 樓下：救護車、圍觀的人
  caption.value = ''
  await cutTo('crowd')
  audio.siren(8)
  audio.murmur(16)
  for (const line of discovery.crowd) {
    if (me !== run) return
    caption.value = line
    await wait(line.startsWith('「') ? 3000 : 4400)
  }
  if (me !== run) return
  // 回到退休那天，問那個問題
  await cutDark(() => {
    shot.value = null
    opening.value = arrived.value = false
    openP.value = 0
    discovering.value = false
    ci.value = chapters.length - 1
    day.value = chapters[ci.value].day
    toMend()
  })
}

// 最後一個畫面：晚上，同一扇門。
// 他活下來的話，由玩家按電鈴，這一次有人來開門；沒有的話，門是暗的。
const finalStage = ref('lines') // lines → bell（等玩家按電鈴）→ answer → card
const finalLine = ref('')
const BELL = { id: 'finalBell', at: [6.25, 1.3, -3.62], label: '電鈴' }
async function toFinal() {
  const me = ++run
  paperOpen.value = false
  const lines = outcome.value === 'alive' ? finale.alive : finale.found
  await cutDark(() => {
    greet.value = false
    finalStage.value = 'lines'
    finalLine.value = lines[0]
    phase.value = 'final'
  })
  await wait(4200)
  if (me !== run) return
  finalLine.value = lines[1]
  await wait(4600)
  if (me !== run) return
  if (outcome.value === 'alive') {
    finalLine.value = finale.bell
    finalStage.value = 'bell'
  } else finalStage.value = 'card'
}
async function ringFinal() {
  if (finalStage.value !== 'bell') return
  const me = ++run
  finalStage.value = 'answer'
  pressing.value = true
  audio.doorbell()
  finalLine.value = finale.answer[0]
  await wait(2200)
  pressing.value = false
  if (me !== run) return
  finalLine.value = finale.answer[1]
  await wait(1600)
  if (me !== run) return
  greet.value = true
  audio.creak()
  await wait(2600)
  if (me !== run) return
  finalLine.value = finale.answer[2]
  await wait(5200)
  if (me !== run || location.hash.endsWith('!')) return
  finalStage.value = 'card'
}

// ── 把「下次」改成「這次」，然後讓時間往前 ───────────────
// 四個人的關心是一條救援鏈：知道不能等 → 願意開口 → 找得到人 → 進得了門。
// 四環都在，他活下來；少了哪一環，那天晚上就卡在哪裡。
const picked = reactive(new Set())
const outcome = computed(() => (picked.size === mends.length ? 'alive' : 'found'))
const pickedMends = computed(() => mends.filter((m) => picked.has(m.id)))
const broken = computed(() => mends.find((m) => !picked.has(m.id))) // 鏈上第一個斷掉的地方
const finder = computed(() => [...pickedMends.value].sort((a, b) => a.found - b.found || a.hour - b.hour)[0])
// 他已經向外求救了：當晚或隔天清晨就有人知道。沒有求救：等最早會察覺的那個人。
const foundDay = computed(() => (broken.value?.reached ? broken.value.brokenDay : (finder.value?.found ?? 1)))
const inMended = computed(() => ['forward', 'ending', 'epilogue', 'final'].includes(phase.value))

const mendFocus = ref(null)
async function toMend() {
  note.value = null
  phase.value = 'mend'
  await nextTick()
  mendFocus.value?.focus()
}
function toggleMend(m) {
  if (picked.has(m.id)) picked.delete(m.id)
  else {
    picked.add(m.id)
    audio.chime(picked.size)
  }
}
function animateDay(to, ms) {
  if (reduceMotion) {
    day.value = to
    return Promise.resolve()
  }
  return new Promise((done) => {
    const from = day.value
    const t0 = performance.now()
    const step = (t) => {
      const k = Math.min(1, (t - t0) / ms)
      day.value = from + (to - from) * ease(k)
      if (k < 1) animRaf = requestAnimationFrame(step)
      else done()
    }
    animRaf = requestAnimationFrame(step)
  })
}
const wait = (ms) => new Promise((r) => setTimeout(r, reduceMotion ? ms / 3 : ms))

async function playForward() {
  const me = ++run
  const alive = (v) => me === run && (v ?? true)
  phase.value = 'forward'
  moving.value = true
  day.value = -90
  audio.resolve()

  // 從退休那天往前走，每個被改掉的「下次」各停一下
  const list = pickedMends.value
  for (let i = 0; i < list.length; i++) {
    caption.value = list[i].vignette
    await Promise.all([animateDay(-90 + (88 * (i + 1)) / list.length, 3400), wait(3400)])
    if (!alive()) return
  }
  await animateDay(0, 900)
  if (!alive()) return

  if (outcome.value === 'alive') {
    caption.value = aliveText.night
    await wait(3200)
    if (!alive()) return
    // 等玩家自己按下撥號
    await new Promise((done) => ((answered = done), (aliveCall.value = true)))
    aliveCall.value = false
    if (!alive()) return
    major.value = true
    caption.value = aliveText.rescue
    audio.doorbell(true)
    await Promise.all([animateDay(1, 1200), wait(3800)])
    if (!alive()) return
    caption.value = aliveText.after
    await Promise.all([animateDay(FOUND_DAY, 5200), wait(5200)])
    if (!alive()) return
    caption.value = aliveText.day90
  } else {
    caption.value = broken.value.broken
    await wait(5200)
    if (!alive()) return
    if (foundDay.value > 0) await animateDay(foundDay.value, 1600)
    if (!broken.value.reached) caption.value = finder.value.finder
  }
  moving.value = false
  await wait(3000)
  if (!alive()) return
  phase.value = 'ending'
}

function backToMend(all = false) {
  paperOpen.value = false
  run++
  greet.value = pressing.value = false
  aliveCall.value = false
  major.value = false
  cancelAnimationFrame(animRaf)
  moving.value = false
  window.scrollTo(0, 0)
  if (all) mends.forEach((m) => picked.add(m.id))
  ci.value = chapters.length - 1
  day.value = chapters[ci.value].day
  toMend()
}
function restart() {
  paperOpen.value = paperRead.value = false
  shot.value = null
  opening.value = discovering.value = arrived.value = greet.value = pressing.value = false
  openP.value = 0
  run++
  aliveCall.value = false
  major.value = false
  cancelAnimationFrame(animRaf)
  clearInterval(clock)
  seen.clear()
  picked.clear()
  note.value = null
  moving.value = false
  ci.value = 0
  day.value = chapters[0].day
  phase.value = 'intro'
  window.scrollTo(0, 0)
}
function toEpilogue() {
  paperOpen.value = false
  phase.value = 'epilogue'
}

// ── 畫面要用的東西 ───────────────────────────────
const sceneKind = computed(() => {
  if (phase.value === 'intro' || phase.value === 'final') return 'hall'
  if (phase.value === 'play') return chapter.value.scene
  if (phase.value === 'true' || phase.value === 'discover') return trueKind.value
  return 'room'
})
const nextKind = computed(() => (phase.value === 'play' && next.value ? next.value.scene : null))
const sceneTime = computed(() => {
  if (phase.value === 'intro') return 'day'
  if (phase.value === 'play') return shown.value.time
  if (phase.value === 'mend') return chapter.value.time
  if (phase.value === 'final') return 'night'
  if (phase.value === 'discover') return 'dusk'
  if (phase.value === 'true') {
    if (day.value < -60) return 'morning'
    if (day.value > -0.75 && day.value < 0.6) return 'night'
    return 'day'
  }
  if (day.value > 0.6) return 'morning'
  if (day.value > -0.6) return 'night'
  return 'day'
})
const focus = computed(() => (phase.value === 'play' && note.value && !ringing.value ? note.value.at : null))
const sceneDay = computed(() => {
  if (phase.value === 'intro') return LISTING_DAY
  if (phase.value === 'final') return outcome.value === 'alive' ? FOUND_DAY : foundDay.value
  return day.value
})
const sceneMends = computed(() => (inMended.value ? [...picked] : []))
const sceneAlive = computed(() => inMended.value && outcome.value === 'alive')
const heading = computed(() => relLabel(day.value, sceneAlive.value))
const kicker = computed(() => {
  if (phase.value === 'play') return shown.value.kicker
  if (phase.value === 'mend') return '還來得及的時候'
  if (phase.value === 'true') return '真正發生的事'
  if (phase.value === 'discover') return '被發現的那一天'
  return outcome.value === 'alive' ? '如果大家都有關心阿誠' : `如果只有${pickedMends.value.map((m) => m.who).join('、')}沒有等下次`
})

// 橫式螢幕時，底部的文字列會蓋住畫面，請場景把構圖往上讓
const win = reactive({ w: window.innerWidth, h: window.innerHeight })
const onResize = () => Object.assign(win, { w: window.innerWidth, h: window.innerHeight })
window.addEventListener('resize', onResize)
const safeBottom = computed(() =>
  win.w > 760 && phase.value !== 'intro' ? Math.round(Math.min(250, win.h * (phase.value === 'epilogue' ? 0.2 : 0.27))) : 0,
)

// 時間軸：一條按實際天數比例畫的線，分成三段。左邊是退休那天，右邊是遊戲開場。
const SPAN = LISTING_DAY + BEFORE_DAYS
const pos = (d) => ((Math.max(-BEFORE_DAYS, Math.min(LISTING_DAY, d)) + BEFORE_DAYS) / SPAN) * 100
const markerPos = computed(() => pos(day.value))
const bandNow = computed(() => bands.findIndex((b, i) => day.value >= b.from && (day.value < b.to || i === bands.length - 1)))

// 開發用，不用每次從頭玩：
//   #mend  直接跳到「把下次改成這次」
//   #ch=5  直接跳到第 6 個章節（從 0 算；電鈴那一章是 5）
//   #true  從「時間順著走一次」開始　#open  被發現那天的門口　#final、#final=2  最後一個畫面
const jump = location.hash.match(/^#ch=(\d+)$/)
const fin = location.hash.match(/^#final(?:=(\d))?(!)?$/) // 結尾加 ! 會停在他開門的畫面，不出片名
if (fin) {
  // #final 直接到最後一個畫面（四句都改了）；#final=2 只改了前兩句
  mends.slice(0, fin[1] ? Number(fin[1]) : mends.length).forEach((m) => picked.add(m.id))
  ci.value = chapters.length - 1
  toFinal()
} else if (location.hash === '#open') {
  // 直接到被發現那天的門口
  chapters.forEach((c, i) => c.hotspots.forEach((h) => seen.add(`${i}:${h.id}`)))
  ci.value = chapters.length - 1
  trueKind.value = 'hall'
  day.value = FOUND_DAY
  caption.value = discovery.arrive
  arrived.value = true
  phase.value = 'discover'
} else if (location.hash === '#true') {
  // 直接從「時間順著走一次」開始，會一路播到開門
  chapters.forEach((c, i) => c.hotspots.forEach((h) => seen.add(`${i}:${h.id}`)))
  ci.value = chapters.length - 1
  startTrue()
} else if (location.hash === '#mend' || jump) {
  const to = jump ? Math.min(chapters.length - 1, Number(jump[1])) : chapters.length - 1
  chapters.forEach((c, i) => i < to + (jump ? 0 : 1) && c.hotspots.forEach((h) => seen.add(`${i}:${h.id}`)))
  ci.value = to
  day.value = chapters[to].day
  phase.value = jump ? 'play' : 'mend'
  if (jump) startClock()
}

onBeforeUnmount(() => {
  cancelAnimationFrame(raf)
  cancelAnimationFrame(animRaf)
  clearInterval(clock)
  window.removeEventListener('resize', onResize)
})
</script>

<template>
  <!-- 3D 場景永遠在最底層，封面、遊戲、尾聲都在同一間屋子裡 -->
  <Scene :kind="sceneKind" :next-kind="nextKind" :progress="p" :day="sceneDay" :time="sceneTime"
         :mends="sceneMends" :alive="sceneAlive"
         :view="phase === 'intro' ? 'intro' : null" :shot="phase === 'epilogue' ? 'paper' : shot" :ringing="pressing" :calling="calling" :opening="opening || openP > 0.2" :arrived="arrived" :greet="greet" :focus="focus" :gap="phase === 'final' ? outcome === 'alive' : null"
         :tv="phase === 'play' && !!note?.tv" :paper="phase === 'ending' || phase === 'epilogue'" :safe-bottom="safeBottom"
         :hotspots="hotspots" :interactive="interactive" @pick="pick" />

  <!-- 切鏡頭用的黑幕 -->
  <div class="cut" :class="{ on: dark }" aria-hidden="true" />

  <!-- ═════ 封面 ═════ -->
  <main v-if="phase === 'intro'" class="intro">
    <div class="intro-card">
      <p class="listing">
        <strong>東區近市場，2 樓，1 房 1 廳</strong>
        月租 6,500 元<span class="listing-was">行情 9,000</span>
        <span class="listing-remark">屋況說明：前一位房客在屋內過世。</span>
      </p>
      <div class="intro-title">
        <!-- 停在那一天的日曆：9 月 15 日，他最後撕的那一張 -->
        <DayPage :day="0" size="lg" />
        <div>
          <h1>他在家</h1>
          <p class="intro-lead">燈亮了九十個晚上。看見的人，都這樣想。</p>
        </div>
      </div>
      <p class="intro-sub">他倒下後第 90 天才被發現。今天，是這間屋子空下來的第 47 天。</p>
      <button class="btn primary big" @click="start">開始遊戲</button>
      <p class="intro-fine">
        這個故事談的是獨自離世。畫面裡會看到過世的長者，以風格化的方式呈現，沒有驚嚇或血腥。人物是虛構的，情節參考公開報導。大約 10 分鐘，有聲音。
      </p>
    </div>
  </main>

  <!-- ═════ 遊戲 ═════ -->
  <main v-else-if="phase !== 'epilogue' && phase !== 'final'" class="stage">
    <header class="hud">
      <DayPage :day="day" :blur="hold || moving" />
      <div class="hud-head">
        <p class="kicker">{{ kicker }}</p>
        <h1>{{ heading }}</h1>
      </div>
      <button class="chip" :aria-pressed="soundOn" @click="toggleSound">聲音{{ soundOn ? '開著' : '關了' }}</button>
    </header>

    <!-- 圓點帶出來的東西：他的手機、一疊信 -->
    <aside v-if="phase === 'play' && note && (note.phone || note.cards) && !ringing" class="prop" :class="note.side">
      <PhoneScreen v-if="note.phone" :data="note.phone" />
      <CardDeck v-else :cards="note.cards" />
    </aside>
    <!-- 結局：這一通由玩家親手撥出去 -->
    <aside v-if="aliveCall" class="prop center">
      <PhoneScreen :data="aliveText.call" @done="answered()" />
    </aside>

    <!-- 把下次改成這次 -->
    <section v-if="phase === 'mend'" class="panel" aria-labelledby="mend-title">
      <h2 id="mend-title" ref="mendFocus" tabindex="-1">如果，大家都沒有等「下次」。</h2>
      <p>你不能讓胸悶不要來。你能改的，是那之前的每一句「下次」。可以只改一個，也可以每一個都改。</p>
      <ul class="mend-list">
        <li v-for="m in mends" :key="m.id">
          <button class="mend-btn" :class="{ on: picked.has(m.id) }" :aria-pressed="picked.has(m.id)" @click="toggleMend(m)">
            <span class="mend-who">{{ m.who }}</span>
            <span class="mend-label">{{ m.label }}</span>
            <span class="mend-link">{{ m.link }}</span>
            <span class="mend-state">{{ picked.has(m.id) ? '這次' : '下次' }}</span>
          </button>
        </li>
      </ul>
      <div class="row">
        <button class="btn primary" :disabled="!picked.size" @click="playForward">讓時間往前走</button>
        <span class="fine">改了 {{ picked.size }} 個，共 {{ mends.length }} 個。</span>
      </div>
    </section>

    <!-- 結局：他活下來了 -->
    <section v-if="phase === 'ending' && outcome === 'alive'" class="panel ending" aria-labelledby="end-title">
      <div class="ending-days">
        <DayPage :day="FOUND_DAY" size="lg" />
        <p class="ending-was">原本，這是他被發現的日子。</p>
      </div>
      <div>
        <h2 id="end-title">那一晚之後第 90 天，他在家。</h2>
        <p>這間屋子沒有空下來。門上沒有貼過那張紅紙。它還是阿誠的家。</p>
        <ul class="chain" aria-label="那天晚上的四個環節">
          <li v-for="m in mends" :key="m.id" class="ok">{{ m.link }}</li>
        </ul>
        <p class="fine">不是每一次都來得及。但四個環節都在，才有機會。</p>
        <div class="row">
          <button class="btn primary" @click="toEpilogue">看桌上的報紙</button>
          <button class="btn quiet" @click="backToMend()">重新選一次</button>
        </div>
      </div>
    </section>

    <!-- 結局：鏈上少了一環。他走了，但很快就有人知道 -->
    <section v-else-if="phase === 'ending'" class="panel ending" aria-labelledby="end-title">
      <div class="ending-days">
        <DayPage v-if="foundDay > 0" :day="foundDay" mode="count" size="lg" />
        <DayPage v-else :day="0" size="lg" />
        <p class="ending-was">原本是倒下後第 90 天。</p>
      </div>
      <div>
        <h2 id="end-title">{{ foundDay > 0 ? `倒下後第 ${foundDay} 天，有人知道。` : '那天晚上，就有人趕來。' }}</h2>
        <p>他還是走了。但他沒有一個人，被留在亮著的燈底下九十天。這間屋子，不會有人繞著走。</p>
        <ul class="chain" aria-label="那天晚上的四個環節">
          <li v-for="m in mends" :key="m.id" :class="{ ok: picked.has(m.id) }">
            <span class="visually-hidden">{{ picked.has(m.id) ? '有' : '沒有' }}：</span>{{ m.link }}
          </li>
        </ul>
        <p class="fine">要接住一個人，四個環節都要在。這一次少了「{{ broken.link }}」。</p>
        <div class="row">
          <button class="btn primary" @click="backToMend(true)">如果，每一個人都沒有等下次</button>
          <button class="btn quiet" @click="toEpilogue">看桌上的報紙</button>
        </div>
      </div>
    </section>

    <footer class="bar">
      <div class="bar-main">
        <div class="narration" aria-live="polite">
          <template v-if="note">
            <h2>{{ note.label }}</h2>
            <p>{{ note.text }}</p>
            <button class="btn quiet" @click="note = null">回到屋子裡</button>
          </template>
          <template v-else-if="phase === 'play'">
            <p>{{ chapter.narration }}</p>
            <p v-if="allSeen && chapter.after" class="after">{{ chapter.after }}</p>
            <p v-if="!allSeen" class="hint">點畫面上的圓點，還有 {{ chapter.hotspots.length - seenCount }} 個沒看。</p>
          </template>
          <p v-else-if="phase === 'mend'">{{ discovery.after }}</p>
          <p v-else>{{ caption }}</p>
        </div>

        <div class="action">
          <template v-if="phase === 'play' && allSeen">
            <button v-if="!isLast" class="rewind" :class="{ holding: hold }"
                    @pointerdown.prevent="startHold" @pointerup="endHold" @pointerleave="endHold" @pointercancel="endHold"
                    @keydown="onKeyHold" @keyup="endHold" @blur="endHold" @contextmenu.prevent>
              <svg viewBox="0 0 64 64" aria-hidden="true">
                <circle cx="32" cy="32" r="28" class="rewind-track" />
                <circle cx="32" cy="32" r="28" class="rewind-prog" :stroke-dasharray="176" :stroke-dashoffset="176 * (1 - p)" />
                <g :transform="`rotate(${-p * 720} 32 32)`"><path d="M32 32V14M32 32h10" class="rewind-hand" /></g>
              </svg>
              <span>按住，往回走</span>
            </button>
            <button v-else class="btn primary" @click="startTrue">讓時間照原來的方向，走一次</button>
          </template>
          <!-- 被發現：按住，把門打開 -->
          <button v-if="phase === 'discover' && !discovering" class="rewind" :class="{ holding: openHold }"
                  @pointerdown.prevent="startOpen" @pointerup="endOpen" @pointerleave="endOpen" @pointercancel="endOpen"
                  @keydown="onKeyOpen" @keyup="endOpen" @blur="endOpen" @contextmenu.prevent>
            <svg viewBox="0 0 64 64" aria-hidden="true">
              <circle cx="32" cy="32" r="28" class="rewind-track" />
              <circle cx="32" cy="32" r="28" class="rewind-prog" :stroke-dasharray="176" :stroke-dashoffset="176 * (1 - openP)" />
              <g :transform="`rotate(${openP * 90} 32 32)`"><path d="M32 20a6 6 0 100 12 6 6 0 000-12zm0 12v14m0-5h6m-6 5h4" class="rewind-hand" /></g>
            </svg>
            <span>按住，把門打開</span>
          </button>
        </div>
      </div>

      <nav class="timeline" aria-label="時間軸">
        <div class="bands">
          <div v-for="(b, i) in bands" :key="b.label" class="band" :class="{ on: i === bandNow }" :style="{ flexGrow: b.to - b.from }">
            {{ b.label }}
          </div>
        </div>
        <div class="ticks">
          <span v-for="c in chapters" :key="c.day" class="tick" :class="{ on: Math.round(day) === c.day }" :style="{ left: pos(c.day) + '%' }" />
          <span class="timeline-marker" :style="{ left: markerPos + '%' }" />
        </div>
      </nav>
    </footer>
  </main>

  <!-- ═════ 結尾：桌上的報紙 ═════ -->
  <main v-else-if="phase === 'epilogue'" class="stage">
    <footer class="bar">
      <div class="bar-main">
        <div class="narration">
          <p>{{ outcome === 'alive' ? '早上的報紙，他看到一半。老花眼鏡壓在上面。' : '桌上還留著一份報紙。老花眼鏡壓在上面。' }}</p>
          <p class="hint">{{ paperRead ? '報紙可以再拿起來看。' : '點桌上的報紙，把它拿起來看。' }}</p>
        </div>
        <div class="action row">
          <button class="btn primary" @click="toFinal">放下報紙，走出門</button>
          <button class="btn quiet" @click="backToMend()">回去重新選一次</button>
        </div>
      </div>
    </footer>
    <Newspaper v-if="paperOpen" @close="paperOpen = false" />
  </main>

  <!-- ═════ 最後一個畫面：晚上，門外 ═════ -->
  <main v-if="phase === 'final'" class="stage">
    <section v-if="finalStage === 'card'" class="panel closing" aria-labelledby="closing-title">
      <h1 id="closing-title">他在家</h1>
      <!-- 四句「下次」，各自變成了什麼 -->
      <ul class="echo">
        <li v-for="m in mends" :key="m.id" :class="{ kept: picked.has(m.id) }">
          <span class="echo-was">{{ m.label }}</span>
          <span class="echo-now">{{ picked.has(m.id) ? m.echo : '還是下次。' }}</span>
        </li>
      </ul>
      <p class="closing-call">{{ finale.call }}</p>
      <div class="row">
        <button class="btn primary" @click="restart">再玩一次</button>
        <button class="btn quiet" @click="backToMend()">回去重新選一次</button>
      </div>
      <p class="fine">人物與情節是虛構的。報紙上的數字不是。</p>
    </section>
    <footer v-if="finalStage !== 'card'" class="bar">
      <div class="bar-main">
        <div class="narration" aria-live="polite">
          <p>{{ finalLine }}</p>
          <p v-if="finalStage === 'bell'" class="hint">點門邊的電鈴。</p>
        </div>
      </div>
    </footer>
  </main>
</template>

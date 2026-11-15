<script setup>
// 阿誠的手機。內容來自 story.js 裡圓點的 phone 欄位。
//   list：鎖定畫面上一則一則跳出來的通知
//   call：通訊錄停在某個人，撥號鍵按了也撥不出去；data.connect 為 true 時是結局用的，這次撥得出去
//   chat：對話。有 drafts 的話，會看到他打了又刪，最後才送出最後一句
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import * as audio from '../audio.js'

const props = defineProps({ data: { type: Object, required: true } })
const emit = defineEmits(['done'])
const dial = ref('') // 結局：撥出去之後的狀態
const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches

const shown = ref(0) // list / chat：已經出現幾則
const draft = ref('') // chat：輸入框裡的字
const sent = ref('') // chat：最後送出的那一句
const ended = ref(false)
const tries = ref(0) // call：按了幾次撥號
const body = ref(null)

let timers = []
const later = (fn, ms) => timers.push(setTimeout(fn, reduce ? Math.min(ms, 60) + ms / 20 : ms))
const clear = () => (timers.forEach(clearTimeout), (timers = []))
const toBottom = () => requestAnimationFrame(() => body.value && (body.value.scrollTop = body.value.scrollHeight))

function play() {
  clear()
  shown.value = 0
  draft.value = ''
  sent.value = ''
  ended.value = false
  tries.value = 0
  const d = props.data
  const n = (d.items || d.bubbles || []).length
  let t = 350
  for (let i = 1; i <= n; i++) {
    later(() => ((shown.value = i), d.mode !== 'list' && toBottom()), t) // 通知列表最新的在上面，不用往下捲
    t += 520
  }
  if (d.drafts) {
    // 打字、停一下、刪掉；最後一句才送出去
    d.drafts.forEach((text, k) => {
      const last = k === d.drafts.length - 1
      t += 700
      for (let c = 1; c <= text.length; c++) {
        later(() => ((draft.value = text.slice(0, c)), audio.tick(true)), t)
        t += 85
      }
      t += last ? 900 : 1100
      if (last) {
        later(() => ((sent.value = text), (draft.value = ''), audio.chime(1), toBottom()), t)
      } else {
        for (let c = text.length - 1; c >= 0; c--) {
          later(() => (draft.value = text.slice(0, c)), t)
          t += 45
        }
      }
    })
  }
  if (d.end) later(() => ((ended.value = true), toBottom()), t + 900)
}

function tryCall() {
  if (props.data.connect) {
    // 這一次撥得出去
    if (dial.value) return
    dial.value = '撥號中⋯⋯'
    audio.dialTone()
    later(() => audio.dialTone(), 1700)
    later(() => (dial.value = props.data.answer), 3400)
    later(() => emit('done'), 6800)
    return
  }
  if (tries.value < props.data.refuse.length) tries.value++
}

watch(() => props.data, play)
onMounted(play)
onBeforeUnmount(clear)
</script>

<template>
  <div class="phone" role="group" aria-label="阿誠的手機">
    <div class="phone-screen" :class="[data.mode, { locked: data.mode === 'call' && !data.connect && tries >= data.refuse.length }]">
      <div class="phone-status">
        <span>{{ data.time }}</span>
        <span class="phone-batt" aria-hidden="true" />
      </div>

      <!-- 通知列表 -->
      <template v-if="data.mode === 'list'">
        <p class="phone-clock">{{ data.time }}</p>
        <p class="phone-date">{{ data.date }}</p>
        <ul ref="body" class="phone-list">
          <li v-for="(it, i) in data.items.slice(0, shown)" :key="i">
            <span class="phone-from">{{ it.from }}</span>
            <span class="phone-when">{{ it.when }}</span>
            <span class="phone-text">{{ it.text }}</span>
          </li>
          <li v-if="data.more && shown >= data.items.length" class="phone-more">{{ data.more }}</li>
        </ul>
      </template>

      <!-- 撥不出去的電話 -->
      <template v-else-if="data.mode === 'call'">
        <div class="phone-contact">
          <div class="phone-avatar" aria-hidden="true">{{ data.name.slice(-1) }}</div>
          <p class="phone-name">{{ data.name }}</p>
          <p class="phone-sub">{{ data.sub }}</p>
        </div>
        <p class="phone-refuse" aria-live="polite">
          <template v-if="data.connect">{{ dial || data.hint }}</template>
          <template v-else>{{ tries >= data.refuse.length ? data.locked : tries ? data.refuse[tries - 1] : '\u00a0' }}</template>
        </p>
        <button class="phone-call" :disabled="data.connect ? !!dial : tries >= data.refuse.length" @click="tryCall">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.6 10.8a15 15 0 006.6 6.6l2.2-2.2a1 1 0 011-.25 11.4 11.4 0 003.6.6 1 1 0 011 1V20a1 1 0 01-1 1A17 17 0 013 4a1 1 0 011-1h3.5a1 1 0 011 1 11.4 11.4 0 00.6 3.6 1 1 0 01-.25 1z" /></svg>
          <span>撥給{{ data.name }}</span>
        </button>
      </template>

      <!-- 對話 -->
      <template v-else>
        <p class="phone-title">{{ data.title }}</p>
        <div ref="body" class="phone-chat">
          <template v-for="(b, i) in data.bubbles.slice(0, shown)" :key="i">
            <p v-if="b.system" class="phone-system">{{ b.system }}</p>
            <div v-else class="bubble" :class="{ me: b.me }">
              <span v-if="b.who" class="bubble-who">{{ b.who }}</span>
              <span v-if="b.photo" class="bubble-photo" aria-label="照片：清晨的公車站牌" role="img" />
              {{ b.text }}
            </div>
          </template>
          <div v-if="sent" class="bubble me">{{ sent }}</div>
          <p v-if="ended" class="phone-system end">{{ data.end }}</p>
        </div>
        <div v-if="data.drafts" class="phone-input" :class="{ empty: !draft }">
          <span>{{ draft || (sent ? '' : '輸入訊息') }}</span><i v-if="!sent" aria-hidden="true" />
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
// 一疊可以翻的紙：租屋網的紀錄、信箱裡的信。內容來自 story.js 裡圓點的 cards 欄位。
import { ref, watch } from 'vue'
import * as audio from '../audio.js'

const props = defineProps({ cards: { type: Array, required: true } })
const i = ref(0)
watch(() => props.cards, () => (i.value = 0))

function next() {
  i.value = (i.value + 1) % props.cards.length
  audio.tick(false)
}
</script>

<template>
  <div class="deck" :class="{ stack: cards.length > 1 }">
    <article :key="i" class="deck-card">
      <p class="deck-kicker">{{ cards[i].kicker }}</p>
      <h2>{{ cards[i].title }}</h2>
      <table v-if="cards[i].rows">
        <tr v-for="(r, k) in cards[i].rows" :key="k" :class="{ now: k === cards[i].rows.length - 1 }">
          <td v-for="(c, m) in r" :key="m">{{ c }}</td>
        </tr>
      </table>
      <p v-for="l in cards[i].lines" :key="l">{{ l }}</p>
    </article>
    <button v-if="cards.length > 1" class="deck-next" @click="next">
      {{ i === cards.length - 1 ? '從第一封再看' : '下一封' }}<span>{{ i + 1 }} / {{ cards.length }}</span>
    </button>
  </div>
</template>

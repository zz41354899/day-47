<script setup>
// 一張日曆紙。整個遊戲的時間，都用它來顯示。
import { computed } from 'vue'
import { dateOf, relLabel } from '../story.js'

const props = defineProps({
  day: { type: Number, required: true },
  // 'date'：大字是日期（遊戲中）；'count'：大字是第幾天（封面與結局）
  mode: { type: String, default: 'date' },
  size: { type: String, default: 'md' },
  blur: { type: Boolean, default: false },
})

const d = computed(() => dateOf(props.day))
const big = computed(() => (props.mode === 'count' ? Math.abs(Math.round(props.day)) : d.value.date))
const red = computed(() => props.mode === 'count' || d.value.weekend)
</script>

<template>
  <div class="daypage" :class="[size, { blur }]" aria-hidden="true">
    <div class="daypage-head">
      <template v-if="mode === 'count'">第</template>
      <template v-else>{{ d.month }} 月</template>
    </div>
    <div class="daypage-num" :class="{ red }">{{ big }}</div>
    <div class="daypage-foot">
      <template v-if="mode === 'count'">天</template>
      <template v-else>星期{{ d.weekday }}</template>
    </div>
  </div>
  <span class="visually-hidden">{{ relLabel(day) }}</span>
</template>

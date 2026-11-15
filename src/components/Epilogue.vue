<script setup>
import { ref, computed } from 'vue'

defineEmits(['replay', 'restart'])

const name = ref('')
const copied = ref(false)
const draft = computed(() => {
  const who = name.value.trim()
  return `${who ? who + '，' : ''}最近好嗎？突然想到你。沒什麼事，就是想問問。`
})
async function copy() {
  try {
    await navigator.clipboard.writeText(draft.value)
    copied.value = true
    setTimeout(() => (copied.value = false), 2400)
  } catch {
    copied.value = false
  }
}

// 數字都來自公開報導，連結在頁面最下面。更新數字時請一起更新來源。
const facts = [
  {
    num: '21,856 人',
    text: '日本 2024 年，獨自在家過世、8 天以上才被發現的人數。其中 6,945 人超過一個月，253 人超過一年。這是日本內閣府第一次公布的推估。',
    src: 1,
  },
  {
    num: '4 成',
    text: '台北市每年有超過一百位長者獨自在家過世，其中約四成，是第三天以後才被發現。',
    src: 2,
  },
  {
    num: '118 萬與 5.5 萬',
    text: '台灣 65 歲以上、一個人住的長者約 118 萬人；被政府列冊關懷的，約 5.5 萬人。',
    src: 3,
  },
  {
    num: '74 件變 730 件',
    text: '《報導者》盤點政府的死亡公告：有親屬、卻沒有人出面認領的案件，2020 年 74 件，2025 年 730 件。',
    src: 4,
  },
]

const sources = [
  { n: 1, title: '工商時報〈日本1年2萬1,856人「孤立死」 253人1年後才被發現〉', url: 'https://www.ctee.com.tw/news/20250412700451-430701' },
  { n: 2, title: 'TVBS〈台北市4成「獨老死」3天後才被發現〉', url: 'https://news.tvbs.com.tw/health/3042538' },
  { n: 3, title: 'TVBS〈百萬獨老「僅5.5萬人列冊」〉', url: 'https://news.tvbs.com.tw/politics/3223830' },
  { n: 4, title: '報導者〈消失以前：家人變少、關係變遠的「無緣時代」〉', url: 'https://www.twreporter.org/a/age-of-disconnection-before-dying-alone' },
  { n: 5, title: '元氣網／50+〈有錢有孩子，仍可能孤獨死？〉', url: 'https://health.udn.com/health/story/10429/5135968' },
  { n: 6, title: '鉅亨網〈凶宅的定義〉（內政部 97 年函釋）', url: 'https://news.cnyes.com/news/id/4059734' },
  { n: 7, title: 'TVBS 健康〈關懷獨老一起來〉（弘道老人福利基金會的觀察）', url: 'https://health.tvbs.com.tw/life/360725' },
  { n: 8, title: '衛生福利部〈1966 長照服務專線〉', url: 'https://mohw.gov.tw/cp-16-38621-1.html' },
]
</script>

<template>
  <main class="epilogue">
    <h1>孤獨死說的，不是怎麼死的</h1>
    <p class="definition">
      它指的是：一個人和外界、和家人都缺乏互動，離世之後過了一段時間，沒有人察覺，才被發現。
    </p>
    <p>
      所以重點不在「一個人住」，也不在「怎麼走的」，而在中間那段沒有人知道的時間。一個人住不等於孤立，有家人也不等於有人接得住。清理現場的業者也看到，中壯年、經濟無虞、甚至和家人同住的案例愈來愈多<sup>5</sup>。
    </p>

    <h2>現實裡的數字</h2>
    <dl class="facts">
      <div v-for="f in facts" :key="f.num">
        <dt>{{ f.num }}</dt>
        <dd>{{ f.text }}<sup>{{ f.src }}</sup></dd>
      </div>
    </dl>

    <h2>關於「事故物件」這四個字</h2>
    <p>
      依內政部 2008 年的函釋，凶宅指的是屋內曾經發生凶殺或自殺，因病過世並不算<sup>6</sup>。讓一間屋子被貼上標籤的，往往不是死亡本身，而是太晚被發現。那段時間，是可以縮短的。
    </p>

    <h2>現在可以做的事</h2>

    <h3>傳一則訊息給剛剛想到的那個人</h3>
    <div class="msg">
      <label for="who">你想到誰？</label>
      <input id="who" v-model="name" type="text" autocomplete="off" placeholder="爸、阿嬤、老同學的名字" />
      <p class="msg-draft">{{ draft }}</p>
      <button class="btn primary" @click="copy">{{ copied ? '複製好了，去貼上吧' : '複製這則訊息' }}</button>
      <p class="fine">名字只留在你的畫面上，不會被儲存或傳出去。</p>
    </div>

    <h3>留意身邊的訊號</h3>
    <p>
      信箱滿了沒有人收。燈連續好幾天都亮著，或都沒亮。好幾天沒看到人。遇到了，就敲個門；沒有回應，就告訴里長或派出所。
    </p>
    <p>
      長期服務獨居長輩的弘道老人福利基金會提醒，風險常常不是生活不能自理，而是這三件事：越來越少跟人互動、不想麻煩別人所以不求救、有家人但臨時接不上<sup>7</sup>。
    </p>

    <h3>幫家人接上資源</h3>
    <p>
      撥 <strong>1966</strong> 長照服務專線，可以替住在其他縣市的家人申請當地的長照服務<sup>8</sup>。各地的社區關懷據點多半有共餐和問安，里長知道最近的一個在哪裡。
    </p>

    <h3>如果一個人住的是你自己</h3>
    <p>跟一個人約好固定報平安的方式。像每天早上，一張日曆的照片。</p>

    <p class="care">
      如果這個故事讓你很難受，或你自己正覺得很孤單，可以撥 <strong>1925</strong> 安心專線，24 小時都有人接。
    </p>

    <div class="row">
      <button class="btn primary" @click="$emit('replay')">回去重新選一次</button>
      <button class="btn quiet" @click="$emit('restart')">從頭開始</button>
    </div>

    <h2 class="src-title">資料來源</h2>
    <ol class="sources">
      <li v-for="s in sources" :key="s.n">
        <a :href="s.url" target="_blank" rel="noopener">{{ s.title }}</a>
      </li>
    </ol>
    <p class="fine">《他在家》的人物與情節是虛構的。</p>
  </main>
</template>

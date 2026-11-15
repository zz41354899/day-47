<script setup>
// 結尾：桌上那份報紙。點桌上的報紙會把它拿起來，每一塊都可以點。
// 現實裡的數字、可以做的事、資料來源都在這裡。更新數字時請一起更新來源。
import { ref, computed, onMounted } from 'vue'
import * as audio from '../audio.js'

defineEmits(['close'])

const open = ref(null) // 哪一則數字被點開
const done = ref(new Set()) // 「今天可以做的事」裡打勾的
const name = ref('')
const copied = ref(false)
const sheet = ref(null)
onMounted(() => sheet.value?.focus())

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
function toggle(i) {
  open.value = open.value === i ? null : i
  audio.tick(false)
}
function check(i) {
  const s = new Set(done.value)
  s.has(i) ? s.delete(i) : (s.add(i), audio.chime(s.size))
  done.value = s
}

const facts = [
  {
    num: '21,856',
    unit: '人',
    head: '日本一年，獨自在家過世、8 天以上才被發現',
    more: '2024 年的數字，日本內閣府第一次公布這項推估。其中 6,945 人超過一個月，253 人超過一年。',
    src: 1,
  },
  {
    num: '4',
    unit: '成',
    head: '台北市獨自在家過世的長者，第三天以後才被發現',
    more: '台北市每年有超過一百位長者獨自在家過世，其中約四成，是第三天以後才有人知道。',
    src: 2,
  },
  {
    num: '118',
    unit: '萬',
    head: '台灣 65 歲以上、一個人住的長者',
    more: '被政府列冊關懷的，約 5.5 萬人。有子女的長輩，多半不在名單上。',
    src: 3,
  },
  {
    num: '730',
    unit: '件',
    head: '2025 年，有親屬卻沒有人出面認領的死亡公告',
    more: '《報導者》盤點政府公告：2020 年是 74 件，五年後是 730 件。',
    src: 4,
  },
]

const todo = [
  { head: '傳一則訊息給剛剛想到的那個人', body: '不用有事。下面那一格可以幫你起個頭。' },
  { head: '留意身邊的訊號', body: '信箱滿了沒有人收。燈連續好幾天都亮著，或都沒亮。好幾天沒看到人。遇到了，就敲個門；沒有回應，就告訴里長或派出所。' },
  { head: '幫家人接上資源', body: '撥 1966 長照服務專線，可以替住在其他縣市的家人申請當地的服務。社區關懷據點多半有共餐和問安，里長知道最近的一個在哪裡。' },
  { head: '如果一個人住的是你自己', body: '跟一個人約好固定報平安的方式。像每天早上，一張日曆的照片。再放一把備用鑰匙在信得過的人那裡。' },
]

const sources = [
  { n: 1, title: '工商時報〈日本1年2萬1,856人「孤立死」 253人1年後才被發現〉', url: 'https://www.ctee.com.tw/news/20250412700451-430701' },
  { n: 2, title: 'TVBS〈台北市4成「獨老死」3天後才被發現〉', url: 'https://news.tvbs.com.tw/health/3042538' },
  { n: 3, title: 'TVBS〈百萬獨老「僅5.5萬人列冊」〉', url: 'https://news.tvbs.com.tw/politics/3223830' },
  { n: 4, title: '報導者〈消失以前：家人變少、關係變遠的「無緣時代」〉', url: 'https://www.twreporter.org/a/age-of-disconnection-before-dying-alone' },
  { n: 5, title: '元氣網／50+〈有錢有孩子，仍可能孤獨死？〉', url: 'https://health.udn.com/health/story/10429/5135968' },
  { n: 6, title: '鉅亨網（內政部 97 年函釋的說明）', url: 'https://news.cnyes.com/news/id/4059734' },
  { n: 7, title: 'TVBS 健康〈關懷獨老一起來〉（弘道老人福利基金會的觀察）', url: 'https://health.tvbs.com.tw/life/360725' },
  { n: 8, title: '衛生福利部〈1966 長照服務專線〉', url: 'https://mohw.gov.tw/cp-16-38621-1.html' },
]
</script>

<template>
  <div class="paper-wrap" @click.self="$emit('close')">
    <article ref="sheet" class="newspaper" tabindex="-1" aria-label="桌上的報紙">
      <header class="np-mast">
        <p class="np-meta"><span>星期一</span><span>第 12,418 號</span><span>今日 2 大張</span></p>
        <p class="np-name">晨　間　日　報</p>
        <button class="np-close" @click="$emit('close')">放下報紙</button>
      </header>

      <div class="np-main">
      <section class="np-lead">
        <p class="np-kicker">社會｜專題</p>
        <h1>一個人走了，要過多久才會有人知道</h1>
        <p class="np-def">
          孤獨死，指的是一個人和外界、和家人都缺乏互動，離世之後過了一段時間，沒有人察覺，才被發現。
        </p>
        <div class="np-cols">
          <p>
            它說的不是「怎麼走的」，也不是「一個人住」，而是中間那段沒有人知道的時間。一個人住不等於孤立，有家人也不等於有人接得住。
          </p>
          <p>
            清理現場的業者觀察，這不只發生在長輩身上：中壯年、經濟無虞，甚至和家人同住的案例，都愈來愈多<sup>5</sup>。
          </p>
          <p>
            長期陪伴獨居長輩的弘道老人福利基金會提醒，風險常常不是生活不能自理，而是三件事：越來越少跟人互動、不想麻煩別人所以不求救、有家人但臨時接不上<sup>7</sup>。
          </p>
        </div>
      </section>

      <section class="np-todo">
        <h2>今天可以做的事</h2>
        <ul>
          <li v-for="(t, i) in todo" :key="t.head">
            <button class="np-check" :class="{ on: done.has(i) }" :aria-pressed="done.has(i)" @click="check(i)">
              <i aria-hidden="true" />
              <span><strong>{{ t.head }}</strong>{{ t.body }}</span>
            </button>
          </li>
        </ul>
      </section>

      </div>
      <div class="np-aside">
      <section class="np-facts" aria-label="現實裡的數字">
        <h2>數字</h2>
        <button v-for="(f, i) in facts" :key="f.num" class="np-fact" :class="{ on: open === i }" :aria-expanded="open === i" @click="toggle(i)">
          <span class="np-num">{{ f.num }}<small>{{ f.unit }}</small></span>
          <span class="np-fhead">{{ f.head }}</span>
          <span v-if="open === i" class="np-more">{{ f.more }}<sup>{{ f.src }}</sup></span>
          <span v-else class="np-tap">點開看</span>
        </button>
      </section>

      <section class="np-side">
        <h2>屋子沒有做錯什麼</h2>
        <p>
          依內政部 2008 年的函釋，屋裡有人因病過世，並不屬於買賣時必須特別告知的那一類<sup>6</sup>。讓一間屋子被另眼看待的，往往不是死亡本身，而是太晚被發現。
        </p>
        <p>那段時間，是可以縮短的。</p>
      </section>

      <section class="np-coupon" aria-label="寫一則訊息">
        <p class="np-cut" aria-hidden="true">沿虛線剪下</p>
        <label for="np-who">你剛剛想到誰？</label>
        <input id="np-who" v-model="name" type="text" autocomplete="off" placeholder="爸、阿嬤、老同學的名字" />
        <p class="np-draft">{{ draft }}</p>
        <button class="btn primary" @click="copy">{{ copied ? '複製好了，去貼上吧' : '複製這則訊息' }}</button>
        <p class="np-small">名字只留在你的畫面上，不會被儲存或傳出去。</p>
      </section>

      </div>

      <section class="np-care">
        <p>如果這個故事讓你很難受，或你自己正覺得很孤單：<strong>1925</strong> 安心專線，24 小時都有人接。</p>
      </section>

      <footer class="np-foot">
        <h2>資料來源</h2>
        <ol>
          <li v-for="s in sources" :key="s.n"><a :href="s.url" target="_blank" rel="noopener">{{ s.title }}</a></li>
        </ol>
        <p>《他在家》的人物與情節是虛構的，這份報紙也是。上面的數字不是。</p>
      </footer>
    </article>
  </div>
</template>

<script setup>
// 3D 場景。整間屋子是「時間的函數」：給它一個 day，它就擺出那一天的樣子。
// 倒帶時 day 連續變化：信一封一封縮回信箱、葉子挺起來、日曆一張一張貼回去。
// 單位是公尺。客廳在 x 0~6、z -5~3；樓梯間在客廳右牆（x = 6.2）的外面。
import { ref, onMounted, onBeforeUnmount } from 'vue'
import * as THREE from 'three'
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { clone as cloneSkinned } from 'three/examples/jsm/utils/SkeletonUtils.js'
import peopleGlb from '../assets/people.glb?inline'
import { dateOf, FOUND_DAY } from '../story.js'

const props = defineProps({
  kind: { type: String, default: 'room' }, // 這一章在哪裡：'room' | 'hall'
  view: { type: String, default: null }, // 'intro'：封面用的鏡位
  shot: { type: String, default: null }, // 橋段切過去的鏡頭：'inside' 門後｜'street' 從對面看這扇窗｜'porch' 門外
  ringing: { type: Boolean, default: false }, // 門口的人正在按電鈴
  calling: { type: Boolean, default: false }, // 桌上的手機正在響
  opening: { type: Boolean, default: false }, // 房東正在開門
  gap: { type: Boolean, default: null }, // 最後一個畫面：指定門縫有沒有光（null 表示照時間算）
  tv: { type: Boolean, default: false }, // 電視開著
  arrived: { type: Boolean, default: false }, // 被發現那天：員警和里長到了門口
  greet: { type: Boolean, default: false }, // 結尾：他來開門
  paper: { type: Boolean, default: false }, // 結尾：桌上放著一份報紙
  focus: { type: Array, default: null }, // 玩家正在看的那個圓點，鏡頭會往它靠近一點
  safeBottom: { type: Number, default: 0 }, // 畫面底部被介面蓋住的高度（px），構圖會往上讓
  nextKind: { type: String, default: null }, // 倒帶要去的地方
  progress: { type: Number, default: 0 }, // 倒帶進度 0~1
  day: { type: Number, required: true },
  time: { type: String, default: 'day' }, // 'morning' | 'day' | 'dusk' | 'night'
  mends: { type: Array, default: () => [] }, // 改成「這次」的那幾個人（id）
  alive: { type: Boolean, default: false }, // 大家都關心他的時間線：他活下來了
  hotspots: { type: Array, default: () => [] },
  interactive: { type: Boolean, default: false },
})
const emit = defineEmits(['pick'])

const host = ref(null)
const failed = ref(false)
const hotEls = new Map()
const setHot = (id) => (el) => (el ? hotEls.set(id, el) : hotEls.delete(id))

const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v))
const lerp = (a, b, t) => a + (b - a) * t
const smooth = (v, a, b) => {
  const t = clamp((v - a) / (b - a))
  return t * t * (3 - 2 * t)
}
const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2)
const V = (x, y, z) => new THREE.Vector3(x, y, z)

const SERIF = "'Noto Serif TC','Songti TC','Noto Serif CJK TC',serif"
const NUM = "Anton,Impact,'Arial Narrow',sans-serif"

// ── 鏡頭 ─────────────────────────────────────────
const CAM = {
  intro: { pos: V(12.0, 1.5, -1.25), look: V(6.2, 1.38, -1.5), fov: 30 },
  // 按電鈴時切到門後：從門口往屋裡看，他就在五步之外
  inside: { pos: V(5.82, 1.5, -3.25), look: V(3.95, 1.18, -2.5), fov: 52 },
  // 從對面的公寓看過來：鐵窗後面那盞燈
  street: { pos: V(0.25, 2.15, -8.7), look: V(1.85, 1.58, -5.1), fov: 33 },
  porch: { pos: V(12.6, 1.45, -2.75), look: V(6.2, 1.4, -2.75), fov: 30 },
  // 樓下：救護車和圍觀的人，抬頭看二樓那扇亮著的窗
  crowd: { pos: V(0.6, -0.35, -16.2), look: V(3.3, -1.05, -5.3), fov: 38 },
  hall: { pos: V(12.6, 1.45, -2.75), look: V(6.2, 1.4, -2.75), fov: 30 },
  // 客廳鏡位要同時看得到左邊的窗和右牆上的門
  room: { pos: V(2.6, 1.5, 1.6), look: V(3.25, 1.3, -5), fov: 52 },
  // 結尾：桌上的報紙
  paper: { pos: V(2.55, 1.5, -1.25), look: V(3.14, 0.8, -2.4), fov: 38 },
}
// 從樓梯間穿過門、走進客廳的路線
const pathPos = new THREE.CatmullRomCurve3([CAM.hall.pos, V(9, 1.45, -2.95), V(6.3, 1.45, -3), V(4.6, 1.5, -2.4), V(3.2, 1.5, -0.5), CAM.room.pos])
const pathLook = new THREE.CatmullRomCurve3([CAM.hall.look, V(6.2, 1.4, -3), V(2, 1.3, -3.6), V(2.6, 1.3, -5), CAM.room.look, V(3.25, 1.3, -5.02)])

// ── 光線：每個時段的目標值，畫面會慢慢靠過去 ────────────
const LIGHT = {
  morning: { bg: '#cfe3e4', hemi: '#fff1d6', hemiI: 2.2, sun: '#ffe0ad', sunI: 4.6, sunY: 4.4 },
  day: { bg: '#d6e3df', hemi: '#ffffff', hemiI: 2.3, sun: '#fff6e6', sunI: 4.0, sunY: 6.5 },
  dusk: { bg: '#e7b184', hemi: '#ffeadb', hemiI: 2.1, sun: '#ffc79e', sunI: 2.6, sunY: 6.5 },
  night: { bg: '#14232b', hemi: '#8fa9b8', hemiI: 0.55, sun: '#8fb0c8', sunI: 0, sunY: 6.5 },
}

let renderer, scene, camera, hemi, sun, lamp, gapLight, hallBulb
let raf = 0
let ro = null
const cur = { bg: new THREE.Color(), hemi: new THREE.Color(), hemiI: 2, sun: new THREE.Color(), sunI: 3, sunY: 6.5, lampI: 0 }
const tmpColor = new THREE.Color()
const pointer = { x: 0, y: 0, sx: 0, sy: 0 }
const o = {} // 會動的東西都掛在這裡
const mats = new Map()

// ── 表面的細節 ─────────────────────────────────────
// 方塊的貼圖座標以公尺為單位（見 box），所以這些貼圖可以直接平鋪在任何大小的東西上：
// 木頭有木紋、舊牆的油漆不均勻、其他東西表面都有一點細顆粒，邊角是圓的。
const seeded = (s) => () => ((s = (s * 16807) % 2147483647) / 2147483647)
function tile(size, metres, draw, color) {
  const c = document.createElement('canvas')
  c.width = c.height = size
  draw(c.getContext('2d'), size)
  const t = new THREE.CanvasTexture(c)
  t.wrapS = t.wrapT = THREE.RepeatWrapping
  t.repeat.set(1 / metres, 1 / metres)
  t.anisotropy = 4
  if (color) t.colorSpace = THREE.SRGBColorSpace
  return t
}
// PBR：每一種表面都有顏色、法線、粗糙度三張貼圖。
// 法線貼圖由高度圖算出來（磁磚的溝縫、木紋的凹凸、油漆的橘皮）。
function normalFrom(height, strength) {
  const s = height.width
  const src = height.getContext('2d').getImageData(0, 0, s, s).data
  const c = document.createElement('canvas')
  c.width = c.height = s
  const g = c.getContext('2d')
  const img = g.createImageData(s, s)
  const H = (x, y) => src[(((y + s) % s) * s + ((x + s) % s)) * 4] / 255
  for (let y = 0; y < s; y++) for (let x = 0; x < s; x++) {
    const dx = (H(x + 1, y) - H(x - 1, y)) * strength, dy = (H(x, y + 1) - H(x, y - 1)) * strength
    const l = Math.hypot(dx, dy, 1), i = (y * s + x) * 4
    img.data[i] = (-dx / l * 0.5 + 0.5) * 255
    img.data[i + 1] = (dy / l * 0.5 + 0.5) * 255
    img.data[i + 2] = (1 / l * 0.5 + 0.5) * 255
    img.data[i + 3] = 255
  }
  g.putImageData(img, 0, 0)
  return c
}
function pbr(size, metres, draw, strength) {
  const mk = () => Object.assign(document.createElement('canvas'), { width: size, height: size })
  const a = mk(), h = mk(), r = mk()
  draw(a.getContext('2d'), h.getContext('2d'), r.getContext('2d'), size)
  const tex = (c, color) => {
    const t = new THREE.CanvasTexture(c)
    t.wrapS = t.wrapT = THREE.RepeatWrapping
    t.repeat.set(1 / metres, 1 / metres)
    t.anisotropy = 8
    if (color) t.colorSpace = THREE.SRGBColorSpace
    return t
  }
  return { map: tex(a, true), normalMap: tex(normalFrom(h, strength)), roughnessMap: tex(r) }
}
const grey = (v) => `rgb(${v},${v},${v})`
// 磁磚：n×n 片，溝縫比較深、比較粗糙，磚面是亮的
function tileSet(size, n, tile, groutPx, grout, seed) {
  return pbr(size, n * tile, (a, h, r, s) => {
    const rnd = seeded(seed), c = s / n
    a.fillStyle = grout; a.fillRect(0, 0, s, s)
    h.fillStyle = grey(70); h.fillRect(0, 0, s, s)
    r.fillStyle = grey(225); r.fillRect(0, 0, s, s)
    for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) {
      const v = 238 + rnd() * 14
      a.fillStyle = `rgb(${v},${v},${v - 2})`
      a.fillRect(x * c + groutPx, y * c + groutPx, c - groutPx * 2, c - groutPx * 2)
      // 磚的邊緣有一點倒角
      for (let k = 0; k < 3; k++) {
        h.fillStyle = grey(150 + k * 30)
        h.fillRect(x * c + groutPx + k, y * c + groutPx + k, c - (groutPx + k) * 2, c - (groutPx + k) * 2)
      }
      r.fillStyle = grey(38 + rnd() * 26)
      r.fillRect(x * c + groutPx, y * c + groutPx, c - groutPx * 2, c - groutPx * 2)
    }
    // 沒擦乾淨的地方比較霧
    for (let i = 0; i < 14; i++) {
      const x = rnd() * s, y = rnd() * s, rad = 20 + rnd() * 70
      const gr = r.createRadialGradient(x, y, 0, x, y, rad)
      gr.addColorStop(0, 'rgba(150,150,150,0.3)'); gr.addColorStop(1, 'rgba(150,150,150,0)')
      r.fillStyle = gr; r.fillRect(x - rad, y - rad, rad * 2, rad * 2)
    }
  }, 2.2)
}
let TEX = null
function makeTextures() {
  TEX = {
    grain: tile(256, 0.5, (g, s) => {
      const r = seeded(11)
      const img = g.createImageData(s, s)
      for (let i = 0; i < s * s; i++) {
        const v = 116 + r() * 22 + (r() < 0.02 ? 34 : 0)
        img.data.set([v, v, v, 255], i * 4)
      }
      g.putImageData(img, 0, 0)
    }),
    // 樓梯間的腰牆：十二公分半的方磚
    tile: tileSet(512, 4, 0.125, 3, '#8a8d84', 31),
    // 公寓外牆：小口磚
    facade: tileSet(512, 8, 0.075, 2, '#7c7a70', 47),
    // 木頭：木紋順著 U 的方向，上過漆
    wood: pbr(512, 0.9, (a, h, r, s) => {
      a.fillStyle = '#f3eee6'; a.fillRect(0, 0, s, s)
      h.fillStyle = grey(128); h.fillRect(0, 0, s, s)
      r.fillStyle = grey(120); r.fillRect(0, 0, s, s)
      const rnd = seeded(5)
      for (let i = 0; i < 180; i++) {
        const y = rnd() * s, wob = (rnd() - 0.5) * 12, w = 0.6 + rnd() * 2.6, al = 0.05 + rnd() * 0.17
        ;[[a, `rgba(${70 + rnd() * 40},${45 + rnd() * 25},${25 + rnd() * 20},${al})`], [h, `rgba(40,40,40,${al * 1.6})`], [r, `rgba(200,200,200,${al})`]].forEach(([g, c]) => {
          g.strokeStyle = c
          g.lineWidth = w
          g.beginPath()
          g.moveTo(0, y)
          g.bezierCurveTo(s * 0.3, y + wob, s * 0.7, y - wob, s, y)
          g.stroke()
        })
      }
    }, 1.2),
    // 舊牆：油漆有橘皮，顏色只有很淡的深淺
    plaster: pbr(512, 2.6, (a, h, r, s) => {
      a.fillStyle = '#fbfaf5'; a.fillRect(0, 0, s, s)
      r.fillStyle = grey(222); r.fillRect(0, 0, s, s)
      const rnd = seeded(23)
      for (let i = 0; i < 36; i++) {
        const x = rnd() * s, y = rnd() * s, rad = 40 + rnd() * 120, al = 0.012 + rnd() * 0.022
        for (const dx of [-s, 0, s]) for (const dy of [-s, 0, s]) {
          const gr = a.createRadialGradient(x + dx, y + dy, 0, x + dx, y + dy, rad)
          gr.addColorStop(0, `rgba(118,108,88,${al})`); gr.addColorStop(1, 'rgba(118,108,88,0)')
          a.fillStyle = gr
          a.fillRect(x + dx - rad, y + dy - rad, rad * 2, rad * 2)
        }
      }
      const img = h.createImageData(s, s)
      for (let i = 0; i < s * s; i++) { const v = 110 + rnd() * 36; img.data.set([v, v, v, 255], i * 4) }
      h.putImageData(img, 0, 0)
    }, 0.9),
    // 磨石子地：磨過、打過蠟，走得多的地方比較霧
    terrazzo: pbr(1024, 1.6, (a, h, r, s) => {
      a.fillStyle = '#b9bdb0'; a.fillRect(0, 0, s, s)
      h.fillStyle = grey(128); h.fillRect(0, 0, s, s)
      r.fillStyle = grey(88); r.fillRect(0, 0, s, s)
      const rnd = seeded(7)
      for (let i = 0; i < 2600; i++) {
        const x = rnd() * s, y = rnd() * s, rad = 2 + rnd() * 6, ang = rnd() * 6
        a.fillStyle = ['#8f978c', '#dcdfd2', '#a3a99c', '#7f887d', '#c9b9a0', '#5f6862'][i % 6]
        a.beginPath()
        a.moveTo(x + Math.cos(ang) * rad, y + Math.sin(ang) * rad)
        a.lineTo(x + Math.cos(ang + 2.2) * rad, y + Math.sin(ang + 2.2) * rad)
        a.lineTo(x + Math.cos(ang + 4.1) * rad * 0.8, y + Math.sin(ang + 4.1) * rad * 0.8)
        a.fill()
      }
      for (let i = 0; i < 30; i++) {
        const x = rnd() * s, y = rnd() * s, rad = 60 + rnd() * 160
        for (const dx of [-s, 0, s]) for (const dy of [-s, 0, s]) {
          const gr = r.createRadialGradient(x + dx, y + dy, 0, x + dx, y + dy, rad)
          gr.addColorStop(0, 'rgba(165,165,165,0.35)'); gr.addColorStop(1, 'rgba(165,165,165,0)')
          r.fillStyle = gr
          r.fillRect(x + dx - rad, y + dy - rad, rad * 2, rad * 2)
        }
      }
      // 銅條分格
      a.fillStyle = '#9a8552'; a.fillRect(0, 0, s, 3); a.fillRect(0, 0, 3, s)
      h.fillStyle = grey(110); h.fillRect(0, 0, s, 3); h.fillRect(0, 0, 3, s)
      r.fillStyle = grey(60); r.fillRect(0, 0, s, 3); r.fillRect(0, 0, 3, s)
    }, 0.6),
  }
}
const WALLS = new Set(['#dedfd3', '#c5d2c6', '#e9e9df', '#9dbbaa', '#e3e3d8', '#b7b4a4'])
const TILED = { '#9dbbaa': 'tile', '#b7b4a4': 'facade' } // 貼磁磚的牆
const hsl = {}
function isWood(c) {
  tmpColor.set(c).getHSL(hsl)
  return hsl.h > 0.04 && hsl.h < 0.13 && hsl.s > 0.2 && hsl.s < 0.65 && hsl.l > 0.16 && hsl.l < 0.5
}
// extra.plain：不要貼圖（人物、發光的東西）
function mat(color, extra) {
  const key = color + JSON.stringify(extra || {})
  if (!mats.has(key)) {
    const { plain, ...rest } = extra || {}
    const m = new THREE.MeshStandardMaterial({ color, roughness: 0.95, metalness: 0, ...rest })
    if (TEX && !plain && !rest.map && !rest.transparent && !rest.emissive) {
      const set = TILED[color] ? TEX[TILED[color]] : WALLS.has(color) ? TEX.plaster : isWood(color) ? TEX.wood : null
      if (set) {
        Object.assign(m, set)
        m.roughness = 1 // 粗糙度交給貼圖
        if (TILED[color]) m.envMapIntensity = 2.2
      } else {
        m.bumpMap = TEX.grain
        m.bumpScale = 0.5
      }
    }
    mats.set(key, m)
  }
  return mats.get(key)
}
// 把貼圖座標換成公尺，並讓紋路順著最長的那一邊
function metreUV(geo, w, h, d) {
  const uv = geo.attributes.uv, n = uv.count / 6
  const dims = [[d, h], [d, h], [w, d], [w, d], [w, h], [w, h]]
  const long = Math.max(w, h, d)
  for (let f = 0; f < 6; f++) {
    const [su, sv] = dims[f]
    const swap = sv === long && su !== long
    for (let i = f * n; i < (f + 1) * n; i++) {
      const u = uv.getX(i) * su, v = uv.getY(i) * sv
      uv.setXY(i, swap ? v : u, swap ? u : v)
    }
  }
}
function box(parent, w, h, d, color, x, y, z, extra) {
  const str = typeof color === 'string'
  const lo = Math.min(w, h, d), hi = Math.max(w, h, d)
  // 牆和很薄的紙不倒角，其他東西的邊角都磨圓一點，光才會在邊上亮起來
  const round = lo >= 0.016 && hi <= 3.2 && !(str && WALLS.has(color))
  const geo = round ? new RoundedBoxGeometry(w, h, d, 2, Math.min(0.014, lo * 0.3)) : new THREE.BoxGeometry(w, h, d)
  if (str) metreUV(geo, w, h, d)
  const m = new THREE.Mesh(geo, str ? mat(color, extra) : color)
  m.position.set(x, y, z)
  m.castShadow = m.receiveShadow = true
  parent.add(m)
  return m
}
function canvasTex(w, h, draw) {
  const c = document.createElement('canvas')
  c.width = w
  c.height = h
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  t.anisotropy = 4
  const redraw = (...a) => {
    const g = c.getContext('2d')
    g.clearRect(0, 0, w, h)
    draw(g, w, h, ...a)
    t.needsUpdate = true
  }
  return { t, redraw }
}
function plane(parent, w, h, material, x, y, z, ry = 0) {
  const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), material)
  m.position.set(x, y, z)
  m.rotation.y = ry
  m.receiveShadow = true
  parent.add(m)
  return m
}
function lines(g, w, h, color, rows) {
  g.strokeStyle = color
  g.lineWidth = h * 0.045
  g.lineCap = 'round'
  rows.forEach(([y, len]) => {
    g.beginPath()
    g.moveTo(w * 0.14, h * y)
    g.lineTo(w * (0.14 + len), h * y)
    g.stroke()
  })
}

// ── 蓋房子 ────────────────────────────────────────
function build() {
  makeTextures()
  scene = new THREE.Scene()
  scene.background = cur.bg
  camera = new THREE.PerspectiveCamera(42, 5 / 3, 0.08, 80)

  hemi = new THREE.HemisphereLight('#ffffff', '#cfd2c5', 2.8)
  sun = new THREE.DirectionalLight('#ffffff', 3.6)
  sun.castShadow = true
  sun.shadow.mapSize.set(2048, 2048)
  Object.assign(sun.shadow.camera, { left: -7, right: 7, top: 7, bottom: -7, near: 1, far: 40 })
  sun.shadow.bias = -0.0006
  sun.shadow.normalBias = 0.02
  sun.shadow.radius = 3
  sun.shadow.camera.updateProjectionMatrix()
  scene.add(hemi, sun, sun.target)

  // 地板（磨石子）
  const fg = new THREE.PlaneGeometry(20, 16)
  const fuv = fg.attributes.uv
  for (let i = 0; i < fuv.count; i++) fuv.setXY(i, fuv.getX(i) * 20, fuv.getY(i) * 16) // 貼圖座標換成公尺
  const floor = new THREE.Mesh(fg, new THREE.MeshStandardMaterial({ ...TEX.terrazzo, roughness: 1, envMapIntensity: 1.3 }))
  floor.rotation.x = -Math.PI / 2
  floor.position.set(6, 0, -2.5)
  floor.receiveShadow = true
  scene.add(floor)

  o.redrawLabels = [] // 畫了字的貼圖，字型載入後要重畫
  buildRoom()
  buildHall()
  buildStreet()
  buildStains()
}

function buildRoom() {
  const g = new THREE.Group()
  scene.add(g)
  const WALL = '#dedfd3'
  const BAND = '#c5d2c6'

  // 後牆（留一個窗洞：x 0.8~2.6、y 1.0~2.3）
  box(g, 0.8, 3, 0.2, WALL, 0.4, 1.5, -5.1)
  box(g, 3.4, 3, 0.2, WALL, 4.3, 1.5, -5.1)
  box(g, 1.8, 1.0, 0.2, WALL, 1.7, 0.5, -5.1)
  box(g, 1.8, 0.7, 0.2, WALL, 1.7, 2.65, -5.1)
  // 左牆、天花板
  box(g, 0.2, 3, 8.4, WALL, -0.1, 1.5, -1)
  box(g, 6.4, 0.12, 8.4, '#e9e9df', 3, 3.06, -1)
  // 右牆（門洞：z -3.45 ~ -2.55、高 2.05），一路延伸成樓梯間的牆
  box(g, 0.2, 3, 5.55, WALL, 6.1, 1.5, -6.225)
  box(g, 0.2, 3, 6.55, WALL, 6.1, 1.5, 0.725)
  box(g, 0.2, 0.95, 0.9, WALL, 6.1, 2.525, -3)
  // 腰牆
  box(g, 0.8, 1.0, 0.012, BAND, 0.4, 0.5, -4.994)
  box(g, 3.4, 1.0, 0.012, BAND, 4.3, 0.5, -4.994)
  box(g, 1.8, 1.0, 0.012, BAND, 1.7, 0.5, -4.994)
  box(g, 0.012, 1.0, 8, BAND, 0.006, 0.5, -1)
  box(g, 0.012, 1.0, 1.55, BAND, 5.994, 0.5, -4.225)
  box(g, 0.012, 1.0, 5.55, BAND, 5.994, 0.5, 0.225)

  // 窗框、鐵窗、窗台
  const FR = '#8b9c93'
  box(g, 1.9, 0.07, 0.24, FR, 1.7, 2.3, -5.1)
  box(g, 0.07, 1.3, 0.24, FR, 0.8, 1.65, -5.1)
  box(g, 0.07, 1.3, 0.24, FR, 2.6, 1.65, -5.1)
  for (let i = 1; i < 8; i++) box(g, 0.028, 1.3, 0.028, '#6f8580', 0.8 + i * 0.225, 1.65, -5.16)
  box(g, 1.8, 0.028, 0.028, '#6f8580', 1.7, 1.65, -5.16)
  box(g, 2.0, 0.05, 0.36, '#b3bfb3', 1.7, 1.0, -4.94)

  // 窗外：天空和對面的公寓
  o.sky = new THREE.Mesh(new THREE.PlaneGeometry(30, 16), new THREE.MeshBasicMaterial({ color: '#d6e3df' }))
  o.sky.position.set(2, 3, -14)
  g.add(o.sky)
  o.bldg = new THREE.MeshStandardMaterial({ color: '#a9bcc0', roughness: 1 })
  o.winMat = new THREE.MeshStandardMaterial({ color: '#8fa5a8', emissive: '#f3c56b', emissiveIntensity: 0 })
  ;[[0.2, 5.2, 2.6], [3.3, 4.0, 2.2]].forEach(([x, h, w], bi) => {
    const b = box(g, w, h, 2, o.bldg, x, h / 2 - 1, -10)
    b.castShadow = false
    ;(o.far ||= []).push(b)
    for (let r = 0; r < 3; r++)
      for (let c = 0; c < 3; c++) {
        const lit = (r * 3 + c + bi) % 3 === 0
        const wm = plane(g, 0.34, 0.42, lit ? o.winMat : mat('#8fa5a8'), x - w / 2 + 0.5 + c * 0.75, 1.0 + r * 0.8, -8.99)
        wm.receiveShadow = false
        o.far.push(wm)
      }
  })

  // 黃金葛
  const plant = new THREE.Group()
  plant.position.set(1.25, 1.025, -4.86)
  plant.scale.setScalar(1.5)
  g.add(plant)
  const pot = new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.075, 0.15, 16), mat('#6e8fa3'))
  pot.position.y = 0.075
  pot.castShadow = true
  plant.add(pot)
  o.leafMat = new THREE.MeshStandardMaterial({ color: '#3f8a5f', roughness: 0.9, side: THREE.DoubleSide })
  const leafShape = new THREE.Shape()
  leafShape.moveTo(0, 0)
  leafShape.bezierCurveTo(-0.075, 0.03, -0.075, 0.13, 0, 0.18)
  leafShape.bezierCurveTo(0.075, 0.13, 0.075, 0.03, 0, 0)
  const leafGeo = new THREE.ShapeGeometry(leafShape, 8)
  o.leaves = [-80, -44, -10, 26, 62, 96].map((az, i) => {
    const yaw = new THREE.Group()
    yaw.position.y = 0.14
    yaw.rotation.y = (az * Math.PI) / 180
    const tilt = new THREE.Group()
    yaw.add(tilt)
    const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.006, 0.006, 0.14 + (i % 3) * 0.03, 5), o.leafMat)
    stem.position.y = stem.geometry.parameters.height / 2
    const leaf = new THREE.Mesh(leafGeo, o.leafMat)
    leaf.position.y = stem.geometry.parameters.height
    leaf.rotation.x = 0.35
    leaf.castShadow = stem.castShadow = true
    tilt.add(stem, leaf)
    plant.add(yaw)
    return { tilt, base: 0.45 + (i % 3) * 0.18 }
  })

  // 日曆
  box(g, 0.48, 0.68, 0.02, '#b9a480', 3.2, 1.85, -4.985)
  o.cal = canvasTex(256, 368, (c, w, h, d) => {
    c.fillStyle = '#f6f4ea'
    c.fillRect(0, 0, w, h)
    c.fillStyle = '#c4322b'
    c.fillRect(0, 0, w, 70)
    c.textAlign = 'center'
    c.fillStyle = '#fff'
    c.font = `600 38px ${SERIF}`
    c.fillText(`${d.month} 月`, w / 2, 50)
    c.fillStyle = d.weekend ? '#c4322b' : '#2c7a5a'
    c.font = `190px ${NUM}`
    c.fillText(String(d.date), w / 2, 262)
    c.fillStyle = '#1d3336'
    c.font = `34px ${SERIF}`
    c.fillText(`星期${d.weekday}`, w / 2, 326)
    c.strokeStyle = '#d6d3c4'
    c.strokeRect(0, h - 14, w, 6)
  })
  const calPage = box(g, 0.44, 0.63, 0.03, new THREE.MeshStandardMaterial({ map: o.cal.t, roughness: 0.9 }), 3.2, 1.85, -4.965)
  calPage.castShadow = false

  // 行事曆
  o.planner = canvasTex(512, 344, (c, w, h, marks, mended) => {
    c.fillStyle = '#f6f4ea'
    c.fillRect(0, 0, w, h)
    c.fillStyle = '#2c7a5a'
    c.fillRect(0, 0, w, 48)
    c.strokeStyle = '#d0d4c6'
    c.lineWidth = 2
    const cw = w / 7, ch = (h - 48) / 4
    for (let i = 1; i < 7; i++) { c.beginPath(); c.moveTo(i * cw, 48); c.lineTo(i * cw, h); c.stroke() }
    for (let i = 1; i < 4; i++) { c.beginPath(); c.moveTo(0, 48 + i * ch); c.lineTo(w, 48 + i * ch); c.stroke() }
    marks.forEach((m) => {
      const x = (m % 7) * cw, y = 48 + Math.floor(m / 7) * ch
      if (mended && WEEKLY.includes(m)) {
        c.strokeStyle = '#c4322b'
        c.lineWidth = 7
        c.beginPath()
        c.arc(x + cw / 2, y + ch / 2, ch * 0.32, 0, 7)
        c.stroke()
      } else {
        c.strokeStyle = 'rgba(29,51,54,.7)'
        c.lineWidth = 8
        c.lineCap = 'round'
        c.beginPath()
        c.moveTo(x + cw * 0.2, y + ch * 0.55)
        c.lineTo(x + cw * 0.8, y + ch * 0.55)
        c.stroke()
      }
    })
  })
  plane(g, 0.78, 0.53, new THREE.MeshStandardMaterial({ map: o.planner.t, roughness: 0.9 }), 4.2, 1.85, -4.985)

  // 合照
  box(g, 0.6, 0.44, 0.03, '#8a6a48', 5.2, 1.93, -4.985)
  const photo = canvasTex(256, 184, (c, w, h) => {
    c.fillStyle = '#cfe0e2'; c.fillRect(0, 0, w, h)
    c.fillStyle = '#9fb3a4'; c.fillRect(0, 112, w, 72)
    c.fillStyle = '#e8e3cf'; c.fillRect(18, 34, 160, 84)
    c.fillStyle = '#2c7a5a'; c.fillRect(18, 84, 160, 16)
    c.fillStyle = '#8fb0b8'
    ;[34, 74, 114].forEach((x) => c.fillRect(x, 46, 28, 28))
    c.fillStyle = '#1d3336'
    for (let i = 0; i < 5; i++) {
      const x = 66 + i * 38, y = 132 - (i % 2) * 6
      c.beginPath(); c.arc(x, y, 14, 0, 7); c.fill()
      c.fillRect(x - 20, y + 14, 40, 60)
    }
  })
  photo.redraw()
  plane(g, 0.52, 0.37, new THREE.MeshStandardMaterial({ map: photo.t, roughness: 0.6 }), 5.2, 1.93, -4.968)

  // 冰箱和上面的共餐單
  box(g, 0.62, 1.55, 0.6, '#a9c0ba', 5.5, 0.775, -4.68, { roughness: 0.6 })
  box(g, 0.625, 0.012, 0.605, '#7f9a93', 5.5, 1.14, -4.68)
  box(g, 0.025, 0.2, 0.03, '#6f8983', 5.24, 1.3, -4.365)
  box(g, 0.025, 0.34, 0.03, '#6f8983', 5.24, 0.9, -4.365)
  const noteT = canvasTex(128, 160, (c, w, h) => {
    c.fillStyle = '#f6efc6'; c.fillRect(0, 0, w, h)
    lines(c, w, h, '#8d8763', [[0.3, 0.7], [0.45, 0.7], [0.6, 0.5], [0.75, 0.62]])
  })
  noteT.redraw()
  o.note = new THREE.Group()
  o.note.position.set(5.58, 1.34, -4.374)
  g.add(o.note)
  o.noteMat = new THREE.MeshStandardMaterial({ map: noteT.t, transparent: true })
  const np = plane(o.note, 0.17, 0.21, o.noteMat, 0, 0, 0)
  np.rotation.z = -0.05
  const magnet = new THREE.Mesh(new THREE.CylinderGeometry(0.018, 0.018, 0.012, 12), mat('#c4322b'))
  magnet.rotation.x = Math.PI / 2
  magnet.position.set(0, 0.085, 0.008)
  o.note.add(magnet)

  // 門（鉸鍊在 z = -3.45，往屋裡開；裡面是木色，外面是紅鐵門）
  o.door = new THREE.Group()
  o.door.position.set(6.1, 0, -3.45)
  g.add(o.door)
  const wood = mat('#9a6b4f'), red = mat('#a8473f', { roughness: 0.7 }), edge = mat('#6b4a38')
  const leaf = new THREE.Mesh(new THREE.BoxGeometry(0.05, 2.05, 0.9), [red, wood, edge, edge, edge, edge])
  leaf.position.set(0, 1.025, 0.45)
  leaf.castShadow = leaf.receiveShadow = true
  o.door.add(leaf)
  ;[[1.5, 0.7], [0.6, 0.85]].forEach(([y, h]) => {
    box(o.door, 0.012, h, 0.66, '#8c5f45', -0.03, y, 0.45)
    box(o.door, 0.012, h, 0.66, '#96392f', 0.03, y, 0.45)
  })
  const knob = new THREE.Mesh(new THREE.SphereGeometry(0.035, 12, 10), mat('#d8c48a', { roughness: 0.4, metalness: 0.4 }))
  knob.position.set(-0.06, 1.0, 0.8)
  o.door.add(knob)
  box(o.door, 0.03, 0.2, 0.035, '#d8c48a', 0.045, 1.02, 0.8, { roughness: 0.4, metalness: 0.4 })
  const peep = new THREE.Mesh(new THREE.SphereGeometry(0.018, 10, 8), mat('#d8c48a'))
  peep.position.set(0.03, 1.55, 0.45)
  o.door.add(peep)
  // 門框
  ;[5.985, 6.215].forEach((x, i) => {
    const c = i ? '#6b7c80' : '#7d8f8a'
    box(g, 0.03, 2.13, 0.08, c, x, 1.065, -3.49)
    box(g, 0.03, 2.13, 0.08, c, x, 1.065, -2.51)
    box(g, 0.03, 0.08, 1.06, c, x, 2.09, -3)
  })
  // 門裡的拖鞋
  slippers(g, 5.55, -2.15, 0.5)

  // 桌子、椅子
  const TW = '#a77b53', TL = '#8f6744'
  box(g, 1.5, 0.05, 0.8, TW, 3.2, 0.74, -2.6)
  ;[[2.52, -2.92], [3.88, -2.92], [2.52, -2.28], [3.88, -2.28]].forEach(([x, z]) => box(g, 0.06, 0.72, 0.06, TL, x, 0.36, z))
  const chair = new THREE.Group()
  chair.position.set(4.34, 0, -2.5)
  chair.rotation.y = 0.04
  g.add(chair)
  box(chair, 0.42, 0.04, 0.42, '#8a6a48', 0, 0.45, 0)
  ;[[-0.18, -0.18], [0.18, -0.18], [-0.18, 0.18]].forEach(([x, z]) => box(chair, 0.04, 0.45, 0.04, '#7a5c3e', x, 0.225, z))
  box(chair, 0.04, 0.98, 0.04, '#7a5c3e', 0.19, 0.49, 0.18)
  box(chair, 0.04, 0.98, 0.04, '#7a5c3e', 0.19, 0.49, -0.18)
  box(chair, 0.03, 0.07, 0.36, '#8a6a48', 0.19, 0.9, 0)
  box(chair, 0.03, 0.07, 0.36, '#8a6a48', 0.19, 0.72, 0)

  // 阿誠：坐著的和站著的各一個，用 day 決定誰出現、擺什麼姿勢
  o.seated = makeFigure(false, { eyes: 'closed' })
  o.seated.root.position.set(4.3, 0.535, -2.5)
  g.add(o.seated.root)
  o.standing = makeFigure(true)
  o.standing.root.position.set(1.62, 0.82, -4.3)
  o.standing.root.rotation.y = -Math.PI / 2 // 面向窗戶
  g.add(o.standing.root)

  // 改變之後才會出現的東西：陳太太的柚子、阿坤留下的釣竿
  o.pomelo = new THREE.Group()
  ;[[3.12, -2.82, 0.085], [3.3, -2.76, 0.075]].forEach(([x, z, r]) => {
    const f = new THREE.Mesh(new THREE.SphereGeometry(r, 12, 10), mat('#cfc866'))
    f.scale.y = 1.12
    f.position.set(x, 0.765 + r * 1.1, z)
    f.castShadow = true
    o.pomelo.add(f)
  })
  g.add(o.pomelo)
  o.rod = new THREE.Group()
  const rodStick = new THREE.Mesh(new THREE.CylinderGeometry(0.006, 0.014, 1.9, 6), mat('#2f3d3a'))
  rodStick.position.y = 0.95
  const reel = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 0.03, 12), mat('#c4322b'))
  reel.rotation.x = Math.PI / 2
  reel.position.set(0, 0.32, 0.03)
  o.rod.add(rodStick, reel)
  o.rod.position.set(5.9, 0, -1.9)
  o.rod.rotation.z = -0.07
  o.rod.traverse((m) => (m.castShadow = true))
  g.add(o.rod)

  // 里長從門縫塞進來的紙條（倒下後第 1 天起就躺在這裡）
  o.doorNote = box(g, 0.2, 0.004, 0.14, '#f6efc6', 5.72, 0.004, -2.95)
  o.doorNote.rotation.y = 0.35
  // 陳太太：大家都關心他的那條時間線裡，她拿著備用鑰匙開門進來
  o.neighbor = makeFigure(true, { shirt: '#b9a6c9', pants: '#5a5560', long: true, hair: '#cfcac4', shoe: '#7a6a6a', female: true, style: 'perm', old: true })
  o.neighbor.root.position.set(5.72, 0.82, -2.92)
  g.add(o.neighbor.root)
  // 她手上那袋柚子（只有她站在門外的橋段會出現）
  o.bag = new THREE.Group()
  box(o.bag, 0.12, 0.2, 0.17, '#f2f1e8', 0, -0.1, 0)
  ;[-0.04, 0.045].forEach((z, i) => {
    const f = new THREE.Mesh(new THREE.SphereGeometry(0.06, 10, 8), mat('#cfc866'))
    f.position.set(0, 0.0 + i * 0.01, z)
    o.bag.add(f)
  })
  o.bag.position.set(0, -0.38, 0)
  o.neighbor.L.el.add(o.bag)

  // 手機（立在充電座上）
  const phone = new THREE.Group()
  phone.position.set(2.85, 0.765, -2.52)
  phone.rotation.y = 0.12
  phone.scale.setScalar(1.35)
  g.add(phone)
  box(phone, 0.1, 0.02, 0.07, '#59635f', 0, 0.01, 0)
  const body = box(phone, 0.085, 0.17, 0.012, '#1d3336', 0, 0.1, -0.012)
  body.rotation.x = -0.28
  o.screen = canvasTex(128, 256, (c, w, h, n) => {
    c.fillStyle = n < 0 ? '#2b4044' : '#cfe3e6'
    c.fillRect(0, 0, w, h)
    if (n > 0) {
      c.fillStyle = '#fff'
      ;[40, 90, 140].forEach((y, i) => c.fillRect(14, y, i === 2 ? 70 : 100, 34))
    }
  })
  o.screenMat = new THREE.MeshStandardMaterial({ map: o.screen.t, emissive: '#cfe3e6', emissiveMap: o.screen.t, emissiveIntensity: 0.6 })
  const scr = plane(phone, 0.07, 0.15, o.screenMat, 0, 0.1, -0.004)
  scr.rotation.x = -0.28
  o.badge = canvasTex(128, 128, (c, w, h, n) => {
    c.fillStyle = '#c4322b'
    c.beginPath(); c.arc(64, 64, 60, 0, 7); c.fill()
    c.fillStyle = '#fff'
    c.textAlign = 'center'
    c.font = `${n > 99 ? 50 : 62}px ${NUM}`
    c.fillText(n > 99 ? '99+' : String(n), 64, n > 99 ? 82 : 86)
  })
  o.badgeSprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: o.badge.t }))
  o.badgeSprite.scale.set(0.11, 0.11, 1)
  o.badgeSprite.position.set(0.055, 0.21, 0.03)
  phone.add(o.badgeSprite)

  // 麵
  o.bowl = new THREE.Group()
  o.bowl.position.set(3.55, 0.765, -2.48)
  g.add(o.bowl)
  const prof = [[0.045, 0], [0.06, 0.012], [0.105, 0.05], [0.12, 0.085]].map(([x, y]) => new THREE.Vector2(x, y))
  const bowl = new THREE.Mesh(new THREE.LatheGeometry(prof, 24), mat('#f4f1e6', { side: THREE.DoubleSide, roughness: 0.5 }))
  bowl.castShadow = true
  const rim = new THREE.Mesh(new THREE.TorusGeometry(0.12, 0.005, 6, 32), mat('#3d6c9a'))
  rim.rotation.x = Math.PI / 2
  rim.position.y = 0.085
  const soup = new THREE.Mesh(new THREE.CircleGeometry(0.1, 24), mat('#e7dcb6', { roughness: 0.4 }))
  soup.rotation.x = -Math.PI / 2
  soup.position.y = 0.06
  o.bowl.add(bowl, rim, soup)
  ;[-0.012, 0.012].forEach((dz) => {
    const st = new THREE.Mesh(new THREE.CylinderGeometry(0.004, 0.004, 0.26, 5), mat('#6b5a3e'))
    st.rotation.z = 1.25
    st.position.set(0.09, 0.1, dz)
    st.castShadow = true
    o.bowl.add(st)
  })
  const steamT = canvasTex(64, 64, (c) => {
    const gr = c.createRadialGradient(32, 32, 0, 32, 32, 32)
    gr.addColorStop(0, 'rgba(255,255,255,.75)')
    gr.addColorStop(1, 'rgba(255,255,255,0)')
    c.fillStyle = gr
    c.fillRect(0, 0, 64, 64)
  })
  steamT.redraw()
  o.steam = [0, 1, 2].map((i) => {
    const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: steamT.t, transparent: true, depthWrite: false, opacity: 0 }))
    s.userData.phase = i / 3
    o.bowl.add(s)
    return s
  })

  // 那盞燈
  box(g, 0.012, 0.86, 0.012, '#59635f', 3.2, 2.57, -2.6).castShadow = false
  const shadeGeo = new THREE.CylinderGeometry(0.07, 0.25, 0.2, 24, 1, true)
  const shade = new THREE.Mesh(shadeGeo, mat('#5d7a73'))
  shade.position.set(3.2, 2.1, -2.6)
  shade.castShadow = true
  const shadeIn = new THREE.Mesh(shadeGeo, mat('#f1ead0', { side: THREE.BackSide }))
  shadeIn.position.copy(shade.position)
  g.add(shade, shadeIn)
  o.bulbMat = new THREE.MeshStandardMaterial({ color: '#c9cbbe', emissive: '#ffd98a', emissiveIntensity: 0 })
  const bulb = new THREE.Mesh(new THREE.SphereGeometry(0.05, 16, 12), o.bulbMat)
  bulb.position.set(3.2, 2.03, -2.6)
  g.add(bulb)
  lamp = new THREE.PointLight('#ffd28a', 0, 14, 2)
  lamp.position.set(3.2, 1.96, -2.6)
  lamp.castShadow = true
  lamp.shadow.mapSize.set(512, 512)
  lamp.shadow.bias = -0.003
  lamp.shadow.radius = 4
  g.add(lamp)

  // 光束裡的灰塵
  const N = 70
  const pts = new Float32Array(N * 3)
  for (let i = 0; i < N; i++) {
    pts[i * 3] = 1 + Math.random() * 2.6
    pts[i * 3 + 1] = 0.3 + Math.random() * 1.9
    pts[i * 3 + 2] = -4.8 + Math.random() * 3.2
  }
  const pg = new THREE.BufferGeometry()
  pg.setAttribute('position', new THREE.BufferAttribute(pts, 3))
  o.dustMat = new THREE.PointsMaterial({ color: '#fff6dc', size: 0.012, transparent: true, opacity: 0, depthWrite: false })
  o.dust = new THREE.Points(pg, o.dustMat)
  g.add(o.dust)
  buildHome(g)
}


// ── 樓下：公寓的正面、救護車、圍觀的人。只有被發現那天的橋段會看到 ──────────
function buildStreet() {
  const g = (o.street = new THREE.Group())
  scene.add(g)
  const WALL = '#b7b4a4', TRIM = '#8f8c7e'
  // 馬路、人行道
  const road = new THREE.Mesh(new THREE.PlaneGeometry(30, 14), mat('#4b5153'))
  road.rotation.x = -Math.PI / 2
  road.position.set(3, -3, -11.5)
  road.receiveShadow = true
  g.add(road)
  box(g, 16, 0.12, 1.3, '#9a9d94', 3, -2.94, -5.95)
  box(g, 16, 0.02, 0.12, '#e9e6d8', 3, -2.985, -10.4).castShadow = false
  // 公寓正面：一樓、二樓兩側、三樓，樓板的線
  box(g, 14, 3, 0.2, WALL, 3, -1.5, -5.3)
  box(g, 4, 3, 0.2, WALL, -2, 1.5, -5.3)
  box(g, 4, 3, 0.2, WALL, 8, 1.5, -5.3)
  box(g, 14, 2.4, 0.2, WALL, 3, 4.2, -5.3)
  ;[0, 3].forEach((y) => box(g, 14, 0.14, 0.34, TRIM, 3, y, -5.36))
  // 一樓：鐵捲門、樓梯口
  box(g, 2.8, 2.5, 0.06, '#8d9a98', 0.9, -1.75, -5.42)
  for (let k = 0; k < 9; k++) box(g, 2.8, 0.02, 0.07, '#75827f', 0.9, -2.8 + k * 0.27, -5.43).castShadow = false
  box(g, 1.15, 2.35, 0.06, '#2a3336', 4.7, -1.82, -5.42)
  box(g, 1.3, 0.1, 0.1, TRIM, 4.7, -0.6, -5.44)
  // 隔壁陳太太的窗（亮著）、三樓暗著的窗
  box(g, 1.3, 1.1, 0.05, mat('#f3d79a', { emissive: '#f3c56b', emissiveIntensity: 0.9 }), 7.7, 1.65, -5.42).castShadow = false
  ;[0.2, 3.2, 7.4].forEach((x) => (box(g, 1.3, 1.0, 0.05, '#55676c', x, 4.3, -5.42).castShadow = false))
  // 封鎖線
  box(g, 3.4, 0.07, 0.01, '#e8c15a', 4.7, -2.05, -6.7).castShadow = false

  // 救護車
  const amb = new THREE.Group()
  amb.position.set(5.0, -3, -8.1)
  amb.rotation.y = 0.12
  g.add(amb)
  box(amb, 2.3, 1.3, 1.2, '#f2f2ee', 0.3, 1.0, 0, { roughness: 0.6 })
  box(amb, 0.95, 0.95, 1.2, '#f2f2ee', -1.3, 0.82, 0, { roughness: 0.6 })
  box(amb, 3.26, 0.15, 1.22, '#c4322b', -0.18, 0.78, 0)
  box(amb, 0.5, 0.42, 1.21, '#2a3336', -1.42, 1.02, 0)
  ;[[-1.2, 0.56], [-1.2, -0.56], [0.9, 0.56], [0.9, -0.56]].forEach(([x, z]) => {
    const w = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.3, 0.16, 14), mat('#1f2426'))
    w.rotation.x = Math.PI / 2
    w.position.set(x, 0.3, z)
    amb.add(w)
  })
  o.sirenMat = new THREE.MeshStandardMaterial({ color: '#c4322b', emissive: '#ff3b2f', emissiveIntensity: 1 })
  box(amb, 0.5, 0.12, 0.95, o.sirenMat, -0.5, 1.72, 0).castShadow = false
  o.sirenLight = new THREE.PointLight('#ff4a3a', 0, 14, 2)
  o.sirenLight.position.set(-0.5, 2.1, 0)
  amb.add(o.sirenLight)

  // 圍觀的人：背對鏡頭，抬頭看二樓
  const looks = [
    { shirt: '#c98a63', pants: '#4d5a66', long: true, sleeve: 'long', hair: '#2c2a28', shoe: '#2c2f30' },
    { shirt: '#7f9bb0', pants: '#3a4448', long: true, sleeve: 'long', hair: '#cfcac4', shoe: '#3a3330', female: true, style: 'perm', old: true },
    { shirt: '#e3d9c0', pants: '#6a6f72', long: true, hair: '#3b3836', shoe: '#2c2f30', belly: true },
    { shirt: '#b9a6c9', pants: '#5a5560', long: true, sleeve: 'long', hair: '#cfcac4', shoe: '#7a6a6a', female: true, style: 'perm', old: true },
    { shirt: '#6fae8b', pants: '#3f4a50', long: true, sleeve: 'long', hair: '#2c2a28', shoe: '#1f2426', female: true, style: 'bun' },
    { shirt: '#d9c27a', pants: '#4d6470', long: true, hair: '#e9e8e0', shoe: '#5a4a3c', style: 'thin', old: true, belly: true },
    { shirt: '#8f6f6a', pants: '#2f3a40', long: true, sleeve: 'long', hair: '#4a4a48', shoe: '#2c2f30', female: true, style: 'bob' },
    { shirt: '#f2f1e8', pants: '#4d5a66', long: true, sleeve: 'long', hair: '#2c2a28', shoe: '#3a3330' },
    { shirt: '#5f7c88', pants: '#39424a', long: true, sleeve: 'long', hair: '#cfcac4', shoe: '#2c2f30', style: 'thin', old: true },
  ]
  const spots = [[-0.6, -9.7], [0.5, -9.2], [1.4, -9.9], [2.2, -9.1], [3.0, -10.1], [1.0, -10.8], [3.9, -10.6], [-1.4, -10.6], [2.6, -11.2]]
  o.crowd = looks.map((look, k) => {
    const f = makeFigure(true, look)
    f.root.position.set(spots[k][0], -3 + 0.82, spots[k][1])
    f.root.rotation.y = Math.PI / 2 + ((k * 37) % 9 - 4) * 0.07 // 面向公寓
    f.root.scale.setScalar(0.94 + ((k * 13) % 7) * 0.02)
    g.add(f.root)
    return f
  })
}

// ── 屋裡的擺設：一個八十五歲的人，住了很多年的客廳 ──────────────
// 電視櫃和蕾絲布、太太的照片、大同電鍋和熱水瓶、木頭長椅、茶几和茶具、
// 電風扇、掛鐘、優良駕駛的獎牌、窗簾、藥盒、每天的報紙。
// o.mess 是「越來越亂」的東西：退休那天一樣都沒有，到倒下那天全部出現。
function buildHome(g) {
  const WOOD = '#7a5a3c', WOOD2 = '#8a6a48', LACE = '#f4f1e6'
  const cyl = (parent, r1, r2, h, color, x, y, z, extra) => {
    const m = new THREE.Mesh(new THREE.CylinderGeometry(r1, r2, h, 16), typeof color === 'string' ? mat(color, extra) : color)
    m.position.set(x, y, z)
    m.castShadow = m.receiveShadow = true
    parent.add(m)
    return m
  }

  // 電視櫃、蕾絲布、電視
  box(g, 1.6, 0.55, 0.42, WOOD, 3.65, 0.275, -4.77)
  box(g, 0.74, 0.4, 0.012, '#6b4d33', 3.26, 0.29, -4.555)
  box(g, 0.74, 0.4, 0.012, '#6b4d33', 4.04, 0.29, -4.555)
  box(g, 1.68, 0.012, 0.46, LACE, 3.65, 0.557, -4.77)
  box(g, 1.68, 0.09, 0.006, LACE, 3.65, 0.505, -4.542)
  box(g, 0.3, 0.025, 0.18, '#22282a', 3.45, 0.578, -4.78)
  box(g, 0.06, 0.08, 0.05, '#22282a', 3.45, 0.62, -4.78)
  box(g, 0.98, 0.58, 0.045, '#1b2022', 3.45, 0.94, -4.8)
  o.tvMat = new THREE.MeshStandardMaterial({ color: '#0c1113', emissive: '#a9cbd9', emissiveIntensity: 0, roughness: 0.3 })
  plane(g, 0.92, 0.52, o.tvMat, 3.45, 0.94, -4.776)
  box(g, 0.05, 0.016, 0.16, '#c9cec8', 2.98, 0.572, -4.66) // 包著塑膠袋的遙控器

  // 太太的照片，前面一個小茶杯
  const wife = canvasTex(128, 168, (c, w, h) => {
    c.fillStyle = '#e9dfc9'; c.fillRect(0, 0, w, h)
    c.fillStyle = '#6b6a66'; c.beginPath(); c.arc(64, 62, 34, 0, 7); c.fill()
    c.fillStyle = '#d9b99a'; c.beginPath(); c.arc(64, 70, 26, 0, 7); c.fill()
    c.fillStyle = '#8c5f6a'; c.beginPath(); c.ellipse(64, 150, 50, 44, 0, 0, 7); c.fill()
  })
  wife.redraw()
  const frame = box(g, 0.2, 0.26, 0.02, '#5a3f2a', 4.22, 0.7, -4.82)
  frame.rotation.x = -0.14
  const portrait = plane(g, 0.16, 0.21, new THREE.MeshStandardMaterial({ map: wife.t, roughness: 0.6 }), 4.22, 0.7, -4.807)
  portrait.rotation.x = -0.14
  cyl(g, 0.022, 0.018, 0.04, '#f2f1e8', 4.22, 0.583, -4.67)
  cyl(g, 0.025, 0.03, 0.1, '#3d6c9a', 4.4, 0.613, -4.72) // 小花瓶
  const flower = new THREE.Mesh(new THREE.IcosahedronGeometry(0.03, 0), mat('#e8c15a', { flatShading: true }))
  flower.position.set(4.4, 0.72, -4.72)
  g.add(flower)

  // 矮櫃：大同電鍋、熱水瓶
  box(g, 0.6, 0.8, 0.42, WOOD2, 4.83, 0.4, -4.77)
  box(g, 0.5, 0.3, 0.012, '#7a5c3e', 4.83, 0.56, -4.555)
  cyl(g, 0.14, 0.14, 0.19, '#6fae8b', 4.72, 0.895, -4.76, { roughness: 0.5 })
  const lid = new THREE.Mesh(new THREE.SphereGeometry(0.14, 16, 8, 0, Math.PI * 2, 0, Math.PI / 2), mat('#c9cec8', { roughness: 0.3, metalness: 0.3 }))
  lid.scale.y = 0.35
  lid.position.set(4.72, 0.99, -4.76)
  g.add(lid)
  cyl(g, 0.018, 0.018, 0.03, '#22282a', 4.72, 1.05, -4.76)
  cyl(g, 0.075, 0.08, 0.3, '#f1e9dd', 5.0, 0.95, -4.8, { roughness: 0.5 })
  cyl(g, 0.078, 0.078, 0.05, '#d98a8a', 5.0, 0.95, -4.8)
  cyl(g, 0.05, 0.07, 0.05, '#8a8f8c', 5.0, 1.125, -4.8)

  // 冰箱上那盒沒拆的雞精
  o.gift = new THREE.Group()
  box(o.gift, 0.34, 0.1, 0.24, '#b23a34', 0, 0, 0)
  box(o.gift, 0.345, 0.102, 0.03, '#e7c873', 0, 0, 0)
  box(o.gift, 0.03, 0.102, 0.245, '#e7c873', 0, 0, 0)
  o.gift.position.set(5.5, 1.6, -4.66)
  o.gift.rotation.y = 0.12
  g.add(o.gift)

  // 窗簾
  box(g, 2.3, 0.03, 0.03, '#6b5a3e', 1.7, 2.42, -4.93).castShadow = false
  ;[0.64, 2.76].forEach((x) => box(g, 0.24, 1.5, 0.05, '#cdbf9f', x, 1.66, -4.93))

  // 靠牆的木頭長椅，三塊紅坐墊
  box(g, 0.62, 0.06, 1.7, WOOD2, 0.37, 0.42, -3.7)
  box(g, 0.06, 0.52, 1.7, WOOD2, 0.09, 0.72, -3.7)
  ;[-4.52, -2.88].forEach((z) => {
    box(g, 0.62, 0.06, 0.06, WOOD, 0.37, 0.62, z)
    box(g, 0.06, 0.62, 0.06, WOOD, 0.65, 0.31, z)
    box(g, 0.06, 0.62, 0.06, WOOD, 0.09, 0.31, z)
  })
  ;[-4.25, -3.7, -3.15].forEach((z) => box(g, 0.5, 0.07, 0.5, '#b5483e', 0.39, 0.485, z))

  // 茶几、茶盤、茶壺和兩個杯子
  box(g, 0.55, 0.04, 0.42, WOOD, 1.2, 0.4, -3.78)
  ;[[0.96, -3.95], [1.44, -3.95], [0.96, -3.61], [1.44, -3.61]].forEach(([x, z]) => box(g, 0.04, 0.38, 0.04, WOOD, x, 0.19, z))
  box(g, 0.3, 0.02, 0.2, '#5a3f2a', 1.22, 0.43, -3.8)
  const pot = new THREE.Mesh(new THREE.SphereGeometry(0.05, 12, 10), mat('#7a3b2e', { roughness: 0.5 }))
  pot.position.set(1.16, 0.485, -3.8)
  pot.castShadow = true
  g.add(pot)
  cyl(g, 0.02, 0.016, 0.03, '#f2f1e8', 1.3, 0.455, -3.76)
  cyl(g, 0.02, 0.016, 0.03, '#f2f1e8', 1.33, 0.455, -3.85)

  // 電風扇：會轉、會搖頭
  const fan = new THREE.Group()
  fan.position.set(0.85, 0, -2.35)
  g.add(fan)
  cyl(fan, 0.17, 0.19, 0.035, '#dfe3dc', 0, 0.018, 0)
  cyl(fan, 0.016, 0.016, 1.0, '#c9cec8', 0, 0.53, 0)
  o.fanHead = new THREE.Group()
  o.fanHead.position.y = 1.08
  fan.add(o.fanHead)
  box(o.fanHead, 0.1, 0.1, 0.14, '#dfe3dc', 0, 0, -0.06)
  ;[0.03, 0.09].forEach((z) => {
    const ring = new THREE.Mesh(new THREE.TorusGeometry(0.21, 0.006, 6, 28), mat('#c9cec8'))
    ring.position.z = z
    o.fanHead.add(ring)
  })
  o.fanBlades = new THREE.Group()
  o.fanBlades.position.z = 0.06
  o.fanHead.add(o.fanBlades)
  for (let k = 0; k < 3; k++) {
    const arm = new THREE.Group()
    arm.rotation.z = (k * Math.PI * 2) / 3
    box(arm, 0.07, 0.17, 0.006, '#8fbfd0', 0, 0.1, 0).rotation.y = 0.3
    o.fanBlades.add(arm)
  }

  // 掛鐘（左牆）：鐘擺會擺，電池用完就停了
  const clock = new THREE.Group()
  clock.position.set(0.012, 2.02, -3.78)
  clock.rotation.y = Math.PI / 2
  g.add(clock)
  box(clock, 0.3, 0.64, 0.09, WOOD, 0, 0, 0.045)
  const face = canvasTex(128, 128, (c) => {
    c.fillStyle = '#f6f4ea'; c.beginPath(); c.arc(64, 64, 60, 0, 7); c.fill()
    c.strokeStyle = '#1d3336'; c.lineWidth = 5; c.lineCap = 'round'
    for (let k = 0; k < 12; k++) { const a = (k * Math.PI) / 6; c.beginPath(); c.moveTo(64 + Math.sin(a) * 50, 64 - Math.cos(a) * 50); c.lineTo(64 + Math.sin(a) * 56, 64 - Math.cos(a) * 56); c.stroke() }
    c.beginPath(); c.moveTo(64, 64); c.lineTo(86, 40); c.stroke()
    c.lineWidth = 3; c.beginPath(); c.moveTo(64, 64); c.lineTo(42, 22); c.stroke()
  })
  face.redraw()
  plane(clock, 0.22, 0.22, new THREE.MeshStandardMaterial({ map: face.t, transparent: true }), 0, 0.17, 0.092)
  o.pendulum = new THREE.Group()
  o.pendulum.position.set(0, 0.02, 0.1)
  box(o.pendulum, 0.01, 0.22, 0.006, '#d8c48a', 0, -0.11, 0)
  cyl(o.pendulum, 0.04, 0.04, 0.008, '#d8c48a', 0, -0.23, 0, { metalness: 0.5, roughness: 0.4 }).rotation.x = Math.PI / 2
  clock.add(o.pendulum)

  // 優良駕駛的獎牌（左牆）
  const plaqueT = canvasTex(256, 176, (c, w, h) => {
    c.fillStyle = '#d8c48a'; c.fillRect(0, 0, w, h)
    c.strokeStyle = '#8a6a28'; c.lineWidth = 6; c.strokeRect(8, 8, w - 16, h - 16)
    c.fillStyle = '#4a3516'; c.textAlign = 'center'
    c.font = `900 54px ${SERIF}`; c.fillText('優良駕駛', w / 2, 84)
    c.font = `600 26px ${SERIF}`; c.fillText('服務滿三十年', w / 2, 132)
  })
  plaqueT.redraw()
  o.redrawLabels.push(plaqueT.redraw)
  const plaque = new THREE.Group()
  plaque.position.set(0.012, 1.62, -3.08)
  plaque.rotation.y = Math.PI / 2
  g.add(plaque)
  box(plaque, 0.38, 0.28, 0.02, '#5a3f2a', 0, 0, 0.01)
  plane(plaque, 0.3, 0.2, new THREE.MeshStandardMaterial({ map: plaqueT.t, roughness: 0.4, metalness: 0.3 }), 0, 0, 0.022)

  // 門口的地墊
  box(g, 0.5, 0.012, 0.4, '#8a5a44', 5.6, 0.006, -3.0).castShadow = false

  // 餐桌上：藥盒、藥袋
  box(g, 0.25, 0.022, 0.05, '#9fc4d6', 2.62, 0.776, -2.88, { transparent: true, opacity: 0.85 })
  for (let k = 0; k < 7; k++) box(g, 0.03, 0.006, 0.045, k < 2 ? '#dfe9ee' : '#6f9fb8', 2.515 + k * 0.035, 0.79, -2.88)
  const bag = box(g, 0.1, 0.15, 0.02, '#f6f4ea', 2.58, 0.84, -2.96)
  bag.rotation.x = -0.2
  box(g, 0.1, 0.03, 0.022, '#3fae6a', 2.58, 0.87, -2.953).rotation.x = -0.2

  // 報紙的貼圖：報頭、標題、一欄一欄的灰字
  const news = canvasTex(256, 360, (c, w, h) => {
    c.fillStyle = '#ece8da'; c.fillRect(0, 0, w, h)
    c.fillStyle = '#1d3336'; c.fillRect(14, 14, w - 28, 26); c.fillRect(14, 48, w - 28, 3)
    c.fillRect(14, 64, 150, 16); c.fillRect(14, 86, 110, 16)
    c.fillStyle = '#9aa39c'
    for (let col = 0; col < 3; col++) for (let r = 0; r < 28; r++) if ((r + col) % 9) c.fillRect(14 + col * 78, 118 + r * 8, 68 - ((r * 7 + col) % 5) * 4, 3)
    c.fillStyle = '#b9c0b8'; c.fillRect(170, 60, 72, 46)
  })
  news.redraw()
  const newsMat = new THREE.MeshStandardMaterial({ map: news.t, roughness: 0.95 })
  const paper = (parent, x, y, z, ry) => {
    const m = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.008, 0.42), [mat('#e0dccd'), mat('#e0dccd'), newsMat, mat('#e0dccd'), mat('#e0dccd'), mat('#e0dccd')])
    m.position.set(x, y, z)
    m.rotation.y = ry
    m.castShadow = m.receiveShadow = true
    parent.add(m)
    return m
  }
  o.dailyPaper = paper(g, 0.4, 0.526, -3.15, 0.25) // 長椅上，今天的報紙
  // 結尾：餐桌上的那一份，上面壓著他的老花眼鏡
  o.endPaper = new THREE.Group()
  paper(o.endPaper, 0, 0, 0, 0)
  ;[-0.035, 0.035].forEach((x) => {
    const lens = new THREE.Mesh(new THREE.TorusGeometry(0.024, 0.003, 6, 18), mat('#3a3330'))
    lens.rotation.x = Math.PI / 2
    lens.position.set(x + 0.02, 0.01, 0.12)
    o.endPaper.add(lens)
  })
  o.endPaper.position.set(3.14, 0.772, -2.36)
  o.endPaper.rotation.y = 0.22
  g.add(o.endPaper)

  // ── 越來越亂 ──
  o.mess = []
  const mess = (at, obj) => (o.mess.push({ at, obj }), obj)
  const blob = (x, y, z, r, color, sy = 0.8) => {
    const m = new THREE.Mesh(new THREE.IcosahedronGeometry(r, 1), mat(color, { flatShading: true }))
    m.position.set(x, y, z)
    m.scale.set(1, sy, 1)
    m.castShadow = true
    g.add(m)
    return m
  }
  // 捨不得丟的舊報紙，一份一份疊在長椅旁邊
  ;[0.1, 0.26, 0.42, 0.58, 0.74, 0.88].forEach((at, k) => {
    const st = box(g, 0.32, 0.05, 0.44, k % 2 ? '#dcd8c6' : '#e9e6d8', 0.42, 0.025 + k * 0.051, -2.55)
    st.rotation.y = ((k * 37) % 20) / 100 - 0.1
    mess(at, st)
  })
  const shirt = mess(0.2, box(g, 0.46, 0.035, 0.38, '#9aa7b0', 0.4, 0.54, -4.2))
  shirt.rotation.z = 0.08
  const towel = mess(0.6, box(g, 0.05, 0.3, 0.42, '#d9c9a8', 0.135, 0.86, -3.6))
  towel.rotation.z = 0.06
  const bento = new THREE.Group() // 茶几上的便當盒
  box(bento, 0.2, 0.05, 0.14, '#f2f1e8', 0, 0, 0)
  box(bento, 0.2, 0.01, 0.14, '#e3e0d2', 0.03, 0.035, 0.02).rotation.z = 0.25
  bento.position.set(1.06, 0.445, -3.66)
  g.add(bento)
  mess(0.32, bento)
  mess(0.4, blob(5.28, 0.11, -4.15, 0.14, '#e9ecea', 0.75)) // 冰箱前的塑膠袋
  const cup = new THREE.Group() // 電視櫃上的泡麵碗
  cyl(cup, 0.07, 0.05, 0.08, '#c4322b', 0, 0, 0)
  box(cup, 0.006, 0.006, 0.2, '#b9a480', 0.02, 0.05, 0).rotation.y = 0.5
  cup.position.set(3.98, 0.605, -4.64)
  g.add(cup)
  mess(0.48, cup)
  ;[[4.62, -4.42, 0.54], [4.74, -4.36, 0.62], [4.9, -4.44, 0.7]].forEach(([x, z, at]) => {
    const b = new THREE.Group() // 空寶特瓶
    cyl(b, 0.035, 0.035, 0.2, '#b9d6dd', 0, 0.1, 0, { transparent: true, opacity: 0.7 })
    cyl(b, 0.014, 0.02, 0.05, '#3d6c9a', 0, 0.225, 0)
    b.position.set(x, 0, z)
    g.add(b)
    mess(at, b)
  })
  mess(0.66, blob(5.66, 0.2, -3.98, 0.22, '#5f7c88', 0.85)) // 門邊綁好卻沒倒的垃圾
  mess(0.84, blob(5.36, 0.17, -3.84, 0.19, '#6b8793', 0.85))
  const dishes = new THREE.Group() // 餐桌角落疊著沒洗的碗
  cyl(dishes, 0.09, 0.05, 0.05, '#f4f1e6', 0, 0, 0)
  cyl(dishes, 0.085, 0.05, 0.05, '#e9e6d8', 0.01, 0.035, 0)
  dishes.position.set(2.62, 0.79, -2.34)
  g.add(dishes)
  mess(0.76, dishes)
  const bags = new THREE.Group() // 越積越多、沒拆的藥袋
  ;[0, 1, 2].forEach((k) => {
    const b = box(bags, 0.11, 0.012, 0.16, '#f6f4ea', k * 0.03, k * 0.013, k * 0.02)
    b.rotation.y = k * 0.3
  })
  bags.position.set(4.02, 0.57, -4.86)
  g.add(bags)
  mess(0.9, bags)

  // 被發現之後：清潔公司的紙箱
  o.boxes = new THREE.Group()
  box(o.boxes, 0.5, 0.36, 0.4, '#c2a274', 0, 0.18, 0)
  box(o.boxes, 0.5, 0.02, 0.2, '#b3935f', 0, 0.37, -0.12).rotation.x = -0.5
  box(o.boxes, 0.44, 0.32, 0.36, '#c9ab7e', 0.55, 0.16, 0.3).rotation.y = 0.3
  box(o.boxes, 0.36, 0.26, 0.3, '#bb9a6a', 0.5, 0.46, 0.28).rotation.y = -0.15
  o.boxes.position.set(1.75, 0, -2.5)
  g.add(o.boxes)
}

// 牆上的水痕、門邊的手印：老公寓的牆不會是乾淨的
function buildStains() {
  const stain = (seed, tone) => {
    const c = document.createElement('canvas')
    c.width = c.height = 256
    const g = c.getContext('2d')
    const r = seeded(seed)
    for (let i = 0; i < 26; i++) {
      const x = 70 + r() * 116, y = 70 + r() * 116, rad = 40 + r() * 30
      const gr = g.createRadialGradient(x, y, 0, x, y, rad)
      gr.addColorStop(0, `rgba(${tone},${0.018 + r() * 0.03})`)
      gr.addColorStop(1, `rgba(${tone},0)`)
      g.fillStyle = gr
      g.fillRect(0, 0, 256, 256)
    }
    const t = new THREE.CanvasTexture(c)
    t.colorSpace = THREE.SRGBColorSpace
    return new THREE.MeshStandardMaterial({ map: t, transparent: true, depthWrite: false, roughness: 1 })
  }
  const damp = stain(3, '96,84,62'), grey = stain(9, '70,74,70'), hand = stain(17, '88,78,66')
  const put = (m, w, h, x, y, z, ry) => (plane(scene, w, h, m, x, y, z, ry).renderOrder = 1)
  // 客廳：天花板角落的水痕、窗台下、左牆牆腳
  put(damp, 2.2, 1.0, 4.9, 2.5, -4.994, 0)
  put(grey, 1.6, 0.8, 1.7, 0.45, -4.994, 0)
  put(grey, 2.4, 0.7, 0.006, 0.38, -2.2, Math.PI / 2)
  // 樓梯間：信箱上方、牆腳、電鈴旁邊摸了幾十年的地方
  put(damp, 2.0, 1.1, 6.214, 2.45, -0.9, Math.PI / 2)
  put(grey, 3.0, 0.7, 6.214, 0.36, -5.2, Math.PI / 2)
  put(hand, 0.5, 0.5, 6.214, 1.3, -3.72, Math.PI / 2)
}

// ── 人物 ──────────────────────────────────────────
// 比例照真人（約七頭身）：圓的關節、有五官的臉、有手指的手、合身的衣服。
// 臉朝 -x。關節都繞 z 軸轉：正的是往前彎（軀幹、頭），手臂負的是往前抬。
// look（都不給就是阿誠：白汗衫、短褲、藍白拖）：
//   shirt 上衣　pants 褲子　long 長褲　sleeve:'long' 長袖　vest 背心　belt 皮帶　belly 肚子
//   hair 髮色　style 髮型 thin｜short｜bob｜perm｜bun　female 女性的身形　skin 膚色　shoe 鞋子　eyes:'closed'
const UNIT_BALL = new THREE.SphereGeometry(1, 22, 16)
function ball(parent, rx, ry, rz, material, x, y, z) {
  const m = new THREE.Mesh(UNIT_BALL, material)
  m.scale.set(rx, ry, rz)
  m.position.set(x, y, z)
  m.castShadow = true
  parent.add(m)
  return m
}
function tube(parent, r1, r2, len, material, x, y, z) {
  const m = new THREE.Mesh(new THREE.CylinderGeometry(r1, r2, len, 16, 1, true), material)
  m.position.set(x, y - len / 2, z)
  m.castShadow = true
  parent.add(m)
  return m
}
// 一段肢體：從 (x, y, z) 往下長 len，上粗下細，兩頭是圓的
function limb(parent, r1, r2, len, material, x, y, z) {
  const g = new THREE.Group()
  g.position.set(x, y, z)
  parent.add(g)
  tube(g, r1, r2, len, material, 0, 0, 0)
  ball(g, r1, r1, r1, material, 0, 0, 0)
  ball(g, r2, r2, r2, material, 0, -len, 0)
  return g
}
// 人物模型：tools/build_people.py 用 Blender 建的三個人（acheng、man、woman），綁好骨架、有 UV 和 AO 貼圖。
// 載入失敗時退回下面用程式拼的人（makeFigureProc）。
let PEOPLE = null
async function loadPeople() {
  try {
    const buf = await (await fetch(peopleGlb)).arrayBuffer()
    const gltf = await new GLTFLoader().parseAsync(buf, '')
    PEOPLE = {}
    // 三個人是場景最上層的三個節點，順序和腳本裡一樣（載入器會幫重複的名字加編號，所以不靠名字找）
    ;['acheng', 'man', 'woman'].forEach((n, i) => (PEOPLE[n] = gltf.scene.children[i]))
    if (gltf.scene.children.length < 3) PEOPLE = null
    // AO 貼圖是很多小塊拼起來的，縮小取樣會把隔壁的顏色混進來，在衣服邊緣變成小黑點
    gltf.scene.traverse((m) => {
      const t = m.material?.map
      if (!t) return
      t.generateMipmaps = false
      t.minFilter = THREE.LinearFilter
      t.needsUpdate = true
    })
  } catch (e) {
    console.warn('人物模型載入失敗，改用程式拼的人', e)
    PEOPLE = null
  }
}
const FIG = { skin: '#d2a280', shirt: '#f1efe6', pants: '#4d6470', hair: '#dddbd3', shoe: '#2c2f30' }
const qa = new THREE.Quaternion()
// 回傳的 torso／head／sh／el 是「控制桿」：照舊設 rotation（繞 z 是前後擺），每格由 syncFigure 轉成骨頭的旋轉；
// 對它們 add() 的東西（澆水壺、帽子、袋子）會掛在對應的骨頭上，座標軸和以前一樣。
function makeFigure(standing, look = {}) {
  const own = !look.shirt
  // 阿誠用程式做的模型（白頭髮、頭形比較好認）；其他人用 Blender 的
  if (!PEOPLE || own) return makeFigureProc(standing, look)
  const model = cloneSkinned(PEOPLE[own ? 'acheng' : look.female ? 'woman' : 'man'])
  const root = new THREE.Group()
  const turn = new THREE.Group()
  turn.rotation.y = -Math.PI / 2 // 模型面向 +Z，遊戲裡的人面向 -X
  turn.add(model)
  root.add(turn)
  const bones = {}
  const tint = { Skin: look.skin || FIG.skin, Shirt: look.vest || look.shirt || FIG.shirt, Pants: look.pants || FIG.pants, Hair: look.hair || FIG.hair, Shoe: look.shoe || FIG.shoe }
  model.traverse((m) => {
    if (m.isBone) bones[m.name.replace(/_\d+$/, '')] = m
    if (!m.isMesh) return
    m.castShadow = true
    m.frustumCulled = false // 骨架動了以後包圍球不準
    const kind = m.material.name.split('.').pop()
    m.material = m.material.clone()
    if (tint[kind]) m.material.color.set(tint[kind])
    if (kind === 'Hair' && own) m.material.color.set('#e4e2dc')
    if (look.eyes === 'closed' && (kind === 'Eye' || kind === 'White')) m.visible = false
  })
  // 坐著的人：髖關節在原點；站著的人：腳底在 -0.8175
  root.updateMatrixWorld(true)
  const hipY = bones.ThighL.getWorldPosition(new THREE.Vector3()).y
  turn.position.y = standing ? -0.8175 : -hipY - 0.02
  root.updateMatrixWorld(true)
  const rig = []
  const joint = (name, lift = 0) => {
    const bone = bones[name]
    const W0 = bone.getWorldQuaternion(new THREE.Quaternion())
    const W0i = W0.clone().invert()
    const att = new THREE.Group()
    att.quaternion.copy(W0i)
    att.position.set(0, lift, 0).applyQuaternion(W0i)
    bone.add(att)
    const ctl = new THREE.Object3D()
    ctl.add = (...c) => (att.add(...c), ctl)
    rig.push({ ctl, bone, rest: bone.quaternion.clone(), W0, W0i })
    return ctl
  }
  const fixed = (name, angle) => {
    const bone = bones[name]
    const W0 = bone.getWorldQuaternion(new THREE.Quaternion())
    bone.quaternion.multiply(W0.clone().invert()).multiply(qa.setFromAxisAngle(V(0, 0, 1), angle)).multiply(W0)
    root.updateMatrixWorld(true)
  }
  if (!standing) {
    // 大腿往前平放，小腿垂下來
    for (const k of 'LR') {
      fixed('Thigh' + k, -Math.PI / 2)
      fixed('Shin' + k, Math.PI / 2)
    }
  }
  const torso = joint('Spine')
  const head = joint('Head', -0.039)
  const arm = (k) => ({ sh: joint('UpperArm' + k), el: joint('ForeArm' + k) })
  const L = arm('L'), R = arm('R')
  // 模型的手臂是張開的 A 字，平常要收回身體兩側
  L.sh.rotation.x = 0.2
  R.sh.rotation.x = -0.2
  if (look.vest) {
    // 里長的背心穿在外面，裡面的袖子是襯衫的顏色
    model.traverse((m) => m.isMesh && m.material.name.endsWith('.Shirt') && m.material.color.set(look.vest))
  }
  if (standing && own) {
    const can = new THREE.Group()
    const body = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.055, 0.1, 16), mat('#5c8f86', { roughness: 0.5 }))
    const spout = new THREE.Mesh(new THREE.CylinderGeometry(0.008, 0.012, 0.14, 8), mat('#5c8f86', { roughness: 0.5 }))
    spout.rotation.z = 0.9
    spout.position.set(-0.09, 0.03, 0)
    can.add(body, spout)
    can.position.set(-0.03, -0.31, 0)
    can.traverse((m) => (m.castShadow = true))
    R.el.add(can)
    o.can = can
  }
  const f = { root, torso, head, L, R, rig }
  ;(o.figures ||= []).push(f)
  return f
}
function syncFigure(f) {
  for (const j of f.rig) j.bone.quaternion.copy(j.rest).multiply(j.W0i).multiply(j.ctl.quaternion).multiply(j.W0)
}

function makeFigureProc(standing, look = {}) {
  const own = !look.shirt
  const P = { plain: 1 }
  const skin = mat(look.skin || '#d2a280', { roughness: 0.6, ...P })
  const cloth = (c) => mat(c, { roughness: 0.92, ...P })
  const SHIRT = cloth(look.shirt || '#f1efe6'), PANTS = cloth(look.pants || '#4d6470')
  const HAIR = mat(look.hair || '#dddbd3', { roughness: 0.85, ...P })
  const BROW = mat(own ? '#b9b6ae' : look.hair || '#3a3836', P)
  const style = look.style || (own ? 'thin' : look.female ? 'bob' : 'short')
  const belly = look.belly ?? own
  const longSleeve = look.sleeve === 'long'
  const W = look.female ? 0.165 : 0.19 // 肩膀的半寬
  const root = new THREE.Group()

  // 腳：藍白拖，或是鞋子。y0 是地面
  const foot = (x, y0, z, at = root) => {
    if (look.shoe) {
      ball(at, 0.125, 0.046, 0.05, mat(look.shoe, { roughness: 0.55, ...P }), x - 0.045, y0 + 0.046, z)
      box(at, 0.25, 0.018, 0.092, mat('#1d1f20', P), x - 0.045, y0 + 0.009, z)
    } else {
      box(at, 0.25, 0.022, 0.1, mat('#f2f2ea', P), x - 0.05, y0 + 0.011, z)
      ball(at, 0.1, 0.03, 0.041, skin, x - 0.04, y0 + 0.048, z)
      ball(at, 0.032, 0.02, 0.046, skin, x - 0.135, y0 + 0.04, z)
      const strap = new THREE.Mesh(new THREE.TorusGeometry(0.045, 0.011, 8, 14, Math.PI), mat('#3d6c9a', P))
      strap.rotation.y = Math.PI / 2
      strap.position.set(x - 0.1, y0 + 0.03, z)
      at.add(strap)
    }
  }
  // 下半身
  ball(root, 0.116, 0.112, W * 0.9, PANTS, 0, 0.0, 0)
  const legs = []
  ;[-0.088, 0.088].forEach((z) => {
    if (standing) {
      // 大腿掛在髖、小腿掛在膝蓋，走路的時候才擺得動
      const hip = new THREE.Group()
      hip.position.z = z
      root.add(hip)
      const knee = new THREE.Group()
      knee.position.y = -0.42
      hip.add(knee)
      if (look.long) {
        limb(hip, 0.082, 0.064, 0.4, PANTS, 0, -0.02, 0)
        limb(knee, 0.064, 0.056, 0.36, PANTS, 0, 0, 0)
      } else {
        limb(hip, 0.07, 0.053, 0.4, skin, 0, -0.02, 0)
        tube(hip, 0.09, 0.088, 0.21, PANTS, 0, 0, 0) // 短褲的褲管
        limb(knee, 0.053, 0.037, 0.35, skin, 0, 0, 0)
      }
      foot(0, -0.3975, 0, knee)
      legs.push({ hip, knee })
    } else {
      // 坐著：大腿往前平放，小腿垂下來
      const thigh = limb(root, 0.076, 0.058, 0.42, look.long ? PANTS : skin, 0, 0, z)
      thigh.rotation.z = -Math.PI / 2
      if (!look.long) tube(thigh, 0.09, 0.086, 0.26, PANTS, 0, 0.02, 0)
      limb(root, 0.055, 0.037, 0.43, look.long ? PANTS : skin, -0.42, 0, z)
      foot(-0.41, -0.5275, z)
    }
  })

  // 軀幹：用一條輪廓線旋轉出來，再壓扁成人的厚度
  const torso = new THREE.Group()
  torso.position.y = 0.06
  root.add(torso)
  const prof = [[0.11, -0.05], [0.148, 0.02], [0.152, 0.1], [0.147, 0.19], [0.16, 0.28], [0.167, 0.36], [0.15, 0.415], [0.092, 0.452], [0.05, 0.468]]
  const trunk = (k, a, b, material) => {
    const m = new THREE.Mesh(new THREE.LatheGeometry(prof.slice(a, b).map(([r, y]) => new THREE.Vector2(r * k, y)), 24), material)
    m.scale.set(0.66, 1, (W / 0.167) * 0.97)
    m.castShadow = true
    torso.add(m)
    return m
  }
  trunk(1, 0, 9, SHIRT)
  if (belly) ball(torso, 0.118, 0.135, 0.145, SHIRT, -0.03, 0.115, 0)
  if (own) ball(torso, 0.09, 0.11, 0.15, SHIRT, 0.035, 0.33, 0) // 年紀大了，背有一點駝
  if (look.vest) trunk(1.08, 1, 7, cloth(look.vest)) // 里長的背心
  if (look.belt) {
    const b = new THREE.Mesh(new THREE.CylinderGeometry(0.152, 0.152, 0.04, 24), mat(look.belt, { roughness: 0.5, ...P }))
    b.scale.set(0.68, 1, (W / 0.167) * 0.99)
    b.position.y = 0.03
    torso.add(b)
  }
  // 脖子、領口
  const neck = new THREE.Mesh(new THREE.CylinderGeometry(0.041, 0.047, 0.11, 14), skin)
  neck.position.set(-0.006, 0.5, 0)
  neck.castShadow = true
  torso.add(neck)
  const collar = new THREE.Mesh(new THREE.TorusGeometry(0.052, own ? 0.008 : 0.014, 8, 20), SHIRT)
  collar.rotation.x = Math.PI / 2
  collar.position.set(-0.004, 0.462, 0)
  torso.add(collar)

  // 頭
  const head = new THREE.Group()
  head.position.y = 0.5
  torso.add(head)
  ball(head, 0.104, 0.116, 0.09, skin, 0, 0.132, 0) // 頭顱
  ball(head, 0.082, 0.084, 0.076, skin, -0.026, 0.078, 0) // 臉頰到下巴
  ball(head, 0.016, 0.027, 0.014, skin, -0.108, 0.112, 0) // 鼻樑
  ball(head, 0.014, 0.012, 0.018, skin, -0.113, 0.093, 0) // 鼻頭
  ball(head, 0.005, 0.0038, 0.024, mat('#a4685c', P), -0.104, 0.057, 0) // 嘴
  const LID = mat('#5a4338', P)
  ;[-1, 1].forEach((k) => {
    ball(head, 0.014, 0.03, 0.01, skin, 0.004, 0.118, k * 0.092) // 耳朵
    if (look.eyes === 'closed') ball(head, 0.004, 0.003, 0.015, LID, -0.0955, 0.131, k * 0.037)
    else {
      ball(head, 0.007, 0.0085, 0.014, mat('#f1ede6', P), -0.091, 0.134, k * 0.037)
      ball(head, 0.0055, 0.0065, 0.0065, mat('#2a2220', P), -0.096, 0.134, k * 0.037)
      ball(head, 0.006, 0.003, 0.016, skin, -0.094, 0.1425, k * 0.037) // 眼皮
    }
    ball(head, 0.006, 0.0042, 0.019, BROW, -0.0925, 0.155, k * 0.038).rotation.x = k * 0.12 // 眉毛
  })
  if (own || look.old) {
    // 法令紋、額頭的紋路：遠看只是一點陰影
    const LINE = mat('#b98a6c', P)
    ;[-1, 1].forEach((k) => (ball(head, 0.003, 0.02, 0.003, LINE, -0.099, 0.075, k * 0.032).rotation.x = k * 0.35))
    ball(head, 0.003, 0.002, 0.03, LINE, -0.094, 0.183, 0)
  }
  // 頭髮
  const cap = (rx, ry, rz, theta, tilt) => {
    const m = new THREE.Mesh(new THREE.SphereGeometry(1, 22, 12, 0, Math.PI * 2, 0, theta), HAIR)
    m.scale.set(rx, ry, rz)
    m.position.set(0.003, 0.134, 0)
    m.rotation.z = -tilt
    m.castShadow = true
    head.add(m)
  }
  if (style === 'thin') {
    // 頭頂稀疏，只剩後腦和兩側
    cap(0.108, 0.12, 0.094, Math.PI * 0.37, 1.3)
    ;[-1, 1].forEach((k) => ball(head, 0.05, 0.03, 0.012, HAIR, 0.03, 0.155, k * 0.084))
  } else if (style === 'short') cap(0.109, 0.122, 0.095, Math.PI * 0.53, 0.45)
  else {
    cap(0.114, 0.126, 0.102, Math.PI * 0.56, 0.32)
    if (style === 'bob') ball(head, 0.082, 0.1, 0.104, HAIR, 0.036, 0.09, 0)
    if (style === 'perm') {
      ball(head, 0.085, 0.085, 0.108, HAIR, 0.034, 0.11, 0)
      ball(head, 0.09, 0.05, 0.1, HAIR, -0.01, 0.215, 0)
    }
    if (style === 'bun') ball(head, 0.04, 0.04, 0.04, HAIR, 0.1, 0.2, 0)
  }

  // 手臂
  const arm = (k) => {
    const sh = new THREE.Group()
    sh.position.set(0, 0.415, k * (W + 0.022))
    torso.add(sh)
    ball(sh, 0.054, 0.05, 0.052, SHIRT, 0, 0.004, -k * 0.012) // 肩膀
    if (longSleeve) limb(sh, 0.054, 0.047, 0.27, SHIRT, 0, 0, 0)
    else {
      limb(sh, 0.046, 0.04, 0.27, skin, 0, 0, 0)
      tube(sh, 0.058, 0.057, 0.14, SHIRT, 0, 0.005, 0) // 短袖
    }
    const el = new THREE.Group()
    el.position.y = -0.27
    sh.add(el)
    if (longSleeve) limb(el, 0.046, 0.04, 0.215, SHIRT, 0, 0, 0)
    else limb(el, 0.04, 0.03, 0.225, skin, 0, 0, 0)
    const hand = new THREE.Group()
    hand.position.y = -0.25
    el.add(hand)
    ball(hand, 0.02, 0.044, 0.036, skin, 0, -0.028, 0) // 手掌
    ball(hand, 0.016, 0.034, 0.031, skin, -0.012, -0.082, 0) // 四根手指，微微彎著
    ball(hand, 0.012, 0.027, 0.011, skin, -0.02, -0.04, -k * 0.03) // 拇指
    return { sh, el, hand }
  }
  const L = arm(1)
  const R = arm(-1)
  if (standing && own) {
    // 右手的澆水壺
    const can = new THREE.Group()
    const body = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.055, 0.1, 16), mat('#5c8f86', { roughness: 0.5 }))
    const spout = new THREE.Mesh(new THREE.CylinderGeometry(0.008, 0.012, 0.14, 8), mat('#5c8f86', { roughness: 0.5 }))
    spout.rotation.z = 0.9
    spout.position.set(-0.09, 0.03, 0)
    can.add(body, spout)
    can.position.set(-0.02, -0.36, 0)
    can.traverse((m) => (m.castShadow = true))
    R.el.add(can)
    o.can = can
  }
  return { root, torso, head, L, R, legs }
}

// 姿勢：[軀幹, 頭, 左肩, 左肘, 右肩, 右肘]
const POSE = {
  doze: [-0.1, 0.52, -0.3, -1.05, -0.36, -1.0], // 靠著椅背打瞌睡，手放腿上
  slump: [0.95, 0.5, -2.2, -0.35, -2.0, -0.62], // 趴在桌上：手臂平放在桌面，額頭靠在手臂上
  call: [0.06, 0.08, -0.3, -1.05, -0.95, -2.25], // 手機貼著耳朵
  water: [0.12, 0.3, -0.12, -0.25, -0.75, -0.7], // 站著澆水
  wait: [0.04, 0.12, -0.05, -0.15, -0.08, -0.2], // 站在門口等
  ring: [0.06, 0.05, -0.05, -0.15, -1.5, -0.12], // 伸手按電鈴
  reach: [0.1, 0.12, -0.05, -0.15, -1.0, -0.3], // 伸手轉鑰匙
  wave: [0.03, -0.04, -0.05, -0.15, -0.1, -0.25], // 打招呼：右手往旁邊抬、小手臂舉到臉旁邊（側抬在 walkIn 裡加）
}
function setPose(f, a, b = a, k = 0, breathe = 0) {
  const v = a.map((x, i) => lerp(x, b[i], k))
  f.torso.rotation.z = v[0] + breathe
  f.head.rotation.z = v[1]
  f.L.sh.rotation.z = v[2]
  f.L.el.rotation.z = v[3]
  f.R.sh.rotation.z = v[4]
  f.R.el.rotation.z = v[5]
}

function slippers(parent, x, z, ry) {
  const s = new THREE.Group()
  s.position.set(x, 0, z)
  s.rotation.y = ry
  parent.add(s)
  ;[-0.07, 0.07].forEach((dx, i) => {
    box(s, 0.09, 0.02, 0.24, '#f2f2ea', dx, 0.01, i * 0.04)
    box(s, 0.1, 0.03, 0.035, '#3d6c9a', dx, 0.035, i * 0.04 - 0.05)
  })
  return s
}

function buildHall() {
  const g = new THREE.Group()
  scene.add(g)
  // 樓梯間牆面下半截的綠漆、天花板
  box(g, 0.012, 1.25, 5.5, '#9dbbaa', 6.206, 0.625, -6.25)
  box(g, 0.012, 1.25, 6.5, '#9dbbaa', 6.206, 0.625, 0.75)
  box(g, 3.4, 0.12, 13, '#e3e3d8', 7.9, 3.06, -2.5).castShadow = false

  // 門牌、春聯
  const plate = canvasTex(256, 96, (c, w, h) => {
    c.fillStyle = '#f6f4ea'; c.fillRect(0, 0, w, h)
    c.fillStyle = '#1d3336'; c.textAlign = 'center'
    c.font = `600 56px ${SERIF}`
    c.fillText('2F-1', w / 2, 68)
  })
  plate.redraw()
  o.redrawLabels.push(plate.redraw)
  plane(g, 0.32, 0.12, new THREE.MeshStandardMaterial({ map: plate.t }), 6.214, 2.33, -3, Math.PI / 2)
  const couplet = canvasTex(64, 512, (c, w, h) => {
    c.fillStyle = '#c4322b'; c.fillRect(0, 0, w, h)
    c.fillStyle = '#e7c873'; c.textAlign = 'center'
    c.font = `600 44px ${SERIF}`
    ;['出', '入', '平', '安'].forEach((ch, i) => c.fillText(ch, w / 2, 100 + i * 100))
  })
  couplet.redraw()
  o.redrawLabels.push(couplet.redraw)
  o.coupletMat = new THREE.MeshStandardMaterial({ map: couplet.t, transparent: true, opacity: 0.72 })
  plane(g, 0.1, 0.8, o.coupletMat, 6.214, 1.5, -2.33, Math.PI / 2)

  // 信箱
  const mb = new THREE.Group()
  mb.position.set(6.2, 1.15, -1.3)
  g.add(mb)
  box(mb, 0.14, 0.4, 0.56, '#2f6b55', 0.07, 0.2, 0, { roughness: 0.6 })
  box(mb, 0.01, 0.03, 0.42, '#173d30', 0.142, 0.33, 0)
  const lbl = canvasTex(160, 72, (c, w, h) => {
    c.fillStyle = '#f6f4ea'; c.fillRect(0, 0, w, h)
    c.fillStyle = '#1d3336'; c.textAlign = 'center'
    c.font = `600 40px ${SERIF}`
    c.fillText('2F 周', w / 2, 50)
  })
  lbl.redraw()
  o.redrawLabels.push(lbl.redraw)
  plane(mb, 0.2, 0.09, new THREE.MeshStandardMaterial({ map: lbl.t }), 0.146, 0.16, 0, Math.PI / 2)
  const LC = ['#f6f4ea', '#f0d9cf', '#f6f4ea', '#efe6b8', '#f6f4ea', '#dfe9e2', '#f0d9cf']
  o.letters = LC.map((c, i) => {
    const h = 0.2 + (i % 3) * 0.04
    const m = box(mb, 0.004, h, 0.15, c, 0.03 + i * 0.014, 0, -0.17 + ((i * 5) % 7) * 0.055)
    m.rotation.x = ((i * 37) % 50) / 100 - 0.25
    m.userData.h = h
    return m
  })
  o.fallen = [[6.55, -1.1, 0.4, '#f0d9cf'], [6.42, -1.55, -0.3, '#f6f4ea']].map(([x, z, r, c]) => {
    const m = box(g, 0.22, 0.004, 0.14, c, x, 0.004, z)
    m.rotation.y = r
    return m
  })

  // 招領通知單（貼在門外側，跟著門一起動）
  const SC = [['#f6f4ea', '#9aa59c'], ['#f0d9cf', '#b58f84'], ['#efe6b8', '#a39a62']]
  o.slips = SC.map(([bg, ink], i) => {
    const t = canvasTex(128, 84, (c, w, h) => {
      c.fillStyle = bg; c.fillRect(0, 0, w, h)
      lines(c, w, h, ink, [[0.3, 0.6], [0.52, 0.72], [0.74, 0.42]])
    })
    t.redraw()
    const m = plane(o.door, 0.2, 0.13, new THREE.MeshStandardMaterial({ map: t.t, transparent: true }), 0.04 + i * 0.002, 1.5 - i * 0.13, 0.36 + (i % 2) * 0.16, Math.PI / 2)
    m.rotation.z = [-0.07, 0.09, -0.03][i]
    return m
  })

  // 封面用：門上貼的「租」
  const rent = canvasTex(192, 256, (c, w, h) => {
    c.fillStyle = '#c4322b'; c.fillRect(0, 0, w, h)
    c.strokeStyle = '#f1dc9a'; c.lineWidth = 6; c.strokeRect(10, 10, w - 20, h - 20)
    c.fillStyle = '#f6ecc4'; c.textAlign = 'center'
    c.font = `900 150px ${SERIF}`
    c.fillText('租', w / 2, 178)
  })
  rent.redraw()
  o.redrawLabels.push(rent.redraw)
  o.rent = plane(o.door, 0.27, 0.36, new THREE.MeshStandardMaterial({ map: rent.t, transparent: true }), 0.04, 1.5, 0.45, Math.PI / 2)
  o.rent.rotation.z = 0.03

  // 門縫的光
  o.gapMat = new THREE.MeshStandardMaterial({ color: '#ffe2a0', emissive: '#ffd98a', emissiveIntensity: 0 })
  box(g, 0.03, 0.012, 0.88, o.gapMat, 6.2, 0.008, -3).castShadow = false
  gapLight = new THREE.PointLight('#ffd28a', 0, 2.6, 2)
  gapLight.position.set(6.42, 0.1, -3)
  g.add(gapLight)

  // 電表（還在轉）
  const meter = new THREE.Group()
  meter.position.set(6.2, 2.0, -1.3)
  g.add(meter)
  box(meter, 0.1, 0.36, 0.26, '#8d9a98', 0.05, 0.18, 0)
  box(meter, 0.012, 0.2, 0.2, '#dfe6e2', 0.104, 0.22, 0, { roughness: 0.3 })
  box(meter, 0.014, 0.012, 0.16, '#c4322b', 0.106, 0.2, 0)
  box(meter, 0.03, 0.62, 0.03, '#6f7b79', 0.03, 0.67, 0.06).castShadow = false

  // 陳太太放在自己門口的除臭劑
  o.deo = new THREE.Group()
  o.deo.position.set(7.0, 0, -0.3)
  box(o.deo, 0.13, 0.12, 0.13, '#dfe9e2', 0, 0.06, 0)
  box(o.deo, 0.1, 0.05, 0.1, '#7fb79a', 0, 0.145, 0)
  g.add(o.deo)

  // 電鈴（在門的右邊）
  box(g, 0.02, 0.13, 0.085, '#e9e6d6', 6.21, 1.3, -3.62)
  o.bellBtn = new THREE.MeshStandardMaterial({ color: '#c4322b', emissive: '#ff6a4a', emissiveIntensity: 0.15 })
  const btn = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.012, 14), o.bellBtn)
  btn.rotation.z = Math.PI / 2
  btn.position.set(6.225, 1.3, -3.62)
  g.add(btn)

  // 里長：倒下後第 1 天，他站在門口按電鈴
  o.chief = makeFigure(true, { shirt: '#eeeade', vest: '#c4322b', pants: '#3a4448', long: true, hair: '#4a4a48', shoe: '#2c2f30', belly: true })
  o.chief.root.position.set(6.78, 0.82, -3.395)
  g.add(o.chief.root)

  // 員警：被發現那天，房東不敢自己開門，打了一一〇
  o.police = makeFigure(true, { shirt: '#2f4563', pants: '#22303f', long: true, sleeve: 'long', belt: '#15181b', hair: '#1c2226', shoe: '#161616' })
  const capTop = new THREE.Mesh(new THREE.CylinderGeometry(0.118, 0.106, 0.07, 22), mat('#22303f', { plain: 1 }))
  capTop.scale.z = 0.9
  capTop.position.set(0.002, 0.243, 0)
  capTop.castShadow = true
  o.police.head.add(capTop)
  ball(o.police.head, 0.06, 0.007, 0.082, mat('#161c22', { roughness: 0.4, plain: 1 }), -0.11, 0.214, 0)
  o.police.root.position.set(7.1, 0.82, -1.75)
  g.add(o.police.root)

  // 結尾：門口多了一雙小妤的鞋
  o.guestShoes = new THREE.Group()
  ;[-0.06, 0.06].forEach((dz) => box(o.guestShoes, 0.22, 0.07, 0.085, '#d98a8a', 0, 0.035, dz))
  o.guestShoes.position.set(6.72, 0, -1.92)
  o.guestShoes.rotation.y = 0.2
  g.add(o.guestShoes)

  // 房東：倒下後第 90 天，他站在門前，手上有備用鑰匙
  o.landlord = makeFigure(true, { shirt: '#c9b68a', pants: '#6a6f72', long: true, sleeve: 'long', hair: '#8f8b84', shoe: '#3a3330', belly: true, style: 'thin', old: true })
  o.landlord.root.position.set(6.78, 0.82, -2.5)
  g.add(o.landlord.root)

  // 屋子外牆上的冷氣室外機和水管（只有從對面看過來的鏡頭看得到）
  const ac = box(g, 0.72, 0.5, 0.3, '#c5cbc4', 3.45, 1.15, -5.36)
  ac.castShadow = false
  box(g, 0.5, 0.36, 0.02, '#8f9a94', 3.45, 1.15, -5.52).castShadow = false
  box(g, 0.05, 3, 0.05, '#9aa39d', 2.92, 1.5, -5.24).castShadow = false

  // 門外的藍白拖
  o.hallSlippers = slippers(g, 6.75, -2.15, 1.3)

  // 門邊的鞋櫃：老公寓家家戶戶都把鞋櫃擺在門外，百葉門、木紋貼皮，上面放一雙出門穿的皮鞋
  const sc = new THREE.Group()
  sc.position.set(6.2, 0, -1.95)
  g.add(sc)
  box(sc, 0.32, 0.06, 0.68, '#4e4034', 0.17, 0.03, 0)
  box(sc, 0.34, 0.78, 0.72, '#c7b089', 0.17, 0.45, 0, { roughness: 0.7 })
  box(sc, 0.37, 0.025, 0.76, '#a98b61', 0.185, 0.852, 0, { roughness: 0.55 })
  ;[-0.175, 0.175].forEach((dz) => {
    box(sc, 0.012, 0.7, 0.335, '#d6c39d', 0.346, 0.45, dz, { roughness: 0.65 })
    for (let k = 0; k < 9; k++) box(sc, 0.008, 0.012, 0.27, '#9c8160', 0.354, 0.52 + k * 0.03, dz)
    box(sc, 0.016, 0.07, 0.016, '#c9c2b0', 0.36, 0.42, dz > 0 ? -0.02 : 0.02, { roughness: 0.35, metalness: 0.6 })
  })
  const shoe = mat('#2b2522', { roughness: 0.4 })
  ;[-0.06, 0.06].forEach((dz, i) => {
    box(sc, 0.25, 0.06, 0.085, shoe, 0.2 + i * 0.012, 0.895, 0.12 + dz)
    box(sc, 0.1, 0.04, 0.08, shoe, 0.13 + i * 0.012, 0.94, 0.12 + dz)
  })
  // 摺好的雨傘，靠在鞋櫃側邊
  const umb = new THREE.Mesh(new THREE.CylinderGeometry(0.022, 0.012, 0.78, 10), mat('#2f4563', { roughness: 0.6 }))
  umb.position.set(0.3, 0.38, -0.39)
  umb.rotation.x = -0.12
  umb.castShadow = true
  sc.add(umb)
  box(sc, 0.02, 0.1, 0.02, '#3a2c22', 0.3, 0.8, -0.44)

  // 消防：牆腳一支滅火器，上面貼著紅底白字的牌子
  const fx = new THREE.Group()
  fx.position.set(6.31, 0, -4.02)
  g.add(fx)
  const red = mat('#c3231c', { roughness: 0.32, metalness: 0.15 })
  const can = new THREE.Mesh(new THREE.CylinderGeometry(0.075, 0.075, 0.44, 22), red)
  can.position.y = 0.22
  const dome = new THREE.Mesh(new THREE.SphereGeometry(0.075, 22, 10, 0, Math.PI * 2, 0, Math.PI / 2), red)
  dome.position.y = 0.44
  can.castShadow = dome.castShadow = true
  fx.add(can, dome)
  const steel = mat('#b9bcb8', { roughness: 0.3, metalness: 0.8 })
  const neck = new THREE.Mesh(new THREE.CylinderGeometry(0.022, 0.026, 0.05, 12), steel)
  neck.position.y = 0.535
  fx.add(neck)
  box(fx, 0.16, 0.018, 0.03, '#1c1c1c', 0.04, 0.575, 0)
  box(fx, 0.13, 0.016, 0.028, '#1c1c1c', 0.03, 0.548, 0).rotation.z = -0.25
  const gauge = new THREE.Mesh(new THREE.CylinderGeometry(0.018, 0.018, 0.012, 14), mat('#f2efe4'))
  gauge.rotation.z = Math.PI / 2
  gauge.position.set(0.035, 0.535, 0.03)
  fx.add(gauge)
  const hose = new THREE.Mesh(
    new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(-0.01, 0.55, -0.02), V(-0.05, 0.58, -0.07), V(-0.08, 0.45, -0.075), V(-0.08, 0.2, -0.06)]), 16, 0.009, 6),
    mat('#161616', { roughness: 0.5 }),
  )
  hose.castShadow = true
  fx.add(hose)
  const fxLabel = canvasTex(128, 192, (c, w, h) => {
    c.fillStyle = '#f4f1e6'; c.fillRect(0, 0, w, h)
    c.fillStyle = '#c3231c'; c.fillRect(0, 0, w, 44)
    c.fillStyle = '#f4f1e6'; c.textAlign = 'center'
    c.font = `700 30px ${SERIF}`
    c.fillText('ABC', w / 2, 33)
    c.fillStyle = '#1d3336'; c.font = `600 28px ${SERIF}`
    ;['乾粉', '滅火器'].forEach((t, i) => c.fillText(t, w / 2, 90 + i * 40))
  })
  fxLabel.redraw()
  o.redrawLabels.push(fxLabel.redraw)
  const lab = new THREE.Mesh(
    new THREE.CylinderGeometry(0.0765, 0.0765, 0.17, 22, 1, true, Math.PI / 2 - 0.55, 1.1),
    new THREE.MeshStandardMaterial({ map: fxLabel.t, roughness: 0.6 }),
  )
  lab.position.y = 0.24
  fx.add(lab)
  const sign = canvasTex(256, 96, (c, w, h) => {
    c.fillStyle = '#c3231c'; c.fillRect(0, 0, w, h)
    c.fillStyle = '#ffffff'; c.textAlign = 'center'
    c.font = `700 56px ${SERIF}`
    c.fillText('滅火器', w / 2, 68)
  })
  sign.redraw()
  o.redrawLabels.push(sign.redraw)
  plane(g, 0.3, 0.11, new THREE.MeshStandardMaterial({ map: sign.t, roughness: 0.5 }), 6.214, 1.05, -4.02, Math.PI / 2)

  // 陳太太門口的盆栽：她每天早上澆水，所以一直都很好
  const garden = new THREE.Group()
  garden.position.set(6.62, 0, -0.78)
  g.add(garden)
  let seed = 11
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647)
  const addPot = (x, y, z, r, h, color, band) => {
    const prof = [[0.6, 0], [0.68, 0.03], [0.94, 0.84], [1.1, 0.86], [1.1, 1], [0.92, 1], [0.9, 0.9]]
    const pot = new THREE.Mesh(
      new THREE.LatheGeometry(prof.map(([px, py]) => new THREE.Vector2(px * r, py * h)), 22),
      mat(color, { side: THREE.DoubleSide, roughness: 0.75 }),
    )
    pot.position.set(x, y, z)
    pot.castShadow = pot.receiveShadow = true
    const soil = new THREE.Mesh(new THREE.CircleGeometry(r * 0.9, 18), mat('#4a3b2c'))
    soil.rotation.x = -Math.PI / 2
    soil.position.set(x, y + h * 0.9, z)
    const saucer = new THREE.Mesh(new THREE.CylinderGeometry(r * 0.82, r * 0.74, 0.018, 20), mat(color, { roughness: 0.75 }))
    saucer.position.set(x, y + 0.009, z)
    saucer.receiveShadow = true
    garden.add(pot, soil, saucer)
    if (band) {
      const b = new THREE.Mesh(new THREE.CylinderGeometry(r * 0.86, r * 0.8, h * 0.16, 22, 1, true), mat(band, { side: THREE.DoubleSide }))
      b.position.set(x, y + h * 0.56, z)
      garden.add(b)
    }
  }

  // 大盆：虎尾蘭。葉子是一片一片往外彎的劍形，中間深綠帶橫紋，邊緣黃綠。
  addPot(0, 0, -0.1, 0.17, 0.3, '#b5694a')
  const bladeMat = new THREE.MeshStandardMaterial({ vertexColors: true, side: THREE.DoubleSide, roughness: 0.7 })
  const bladeGeo = (h, w, bend) => {
    const S = 7, pos = [], col = [], idx = []
    const dark = new THREE.Color('#2c6b4b'), lite = new THREE.Color('#4f9468'), edge = new THREE.Color('#cdc86a'), c = new THREE.Color()
    for (let k = 0; k <= S; k++) {
      const t = k / S
      const hw = w * Math.pow(Math.sin(Math.PI * (0.13 + 0.87 * t)), 0.8)
      const y = h * t, z = bend * h * t * t
      pos.push(-hw, y, z, 0, y, z - hw * 0.35, hw, y, z)
      c.copy(dark).lerp(lite, 0.5 + 0.5 * Math.sin(t * 21))
      col.push(edge.r, edge.g, edge.b, c.r, c.g, c.b, edge.r, edge.g, edge.b)
      if (k < S) {
        const a = k * 3
        idx.push(a, a + 1, a + 3, a + 1, a + 4, a + 3, a + 1, a + 2, a + 4, a + 2, a + 5, a + 4)
      }
    }
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3))
    geo.setAttribute('color', new THREE.Float32BufferAttribute(col, 3))
    geo.setIndex(idx)
    geo.computeVertexNormals()
    return geo
  }
  for (let k = 0; k < 12; k++) {
    const a = k * 2.4 + rnd() * 0.4
    const inner = k < 4
    const blade = new THREE.Mesh(bladeGeo(inner ? 0.82 + rnd() * 0.16 : 0.5 + rnd() * 0.28, 0.05 + rnd() * 0.018, inner ? 0.05 + rnd() * 0.08 : 0.2 + rnd() * 0.22), bladeMat)
    const r0 = inner ? 0.035 : 0.085
    blade.position.set(Math.sin(a) * r0, 0.26, -0.1 + Math.cos(a) * r0)
    blade.rotation.y = a
    blade.rotation.z = (rnd() - 0.5) * 0.16
    blade.castShadow = true
    garden.add(blade)
  }

  // 小板凳上的白瓷盆：黃金葛，葉子垂到盆外
  ;[[-0.27, 0.27], [0.03, 0.27], [-0.27, 0.49], [0.03, 0.49]].forEach(([x, z]) => box(garden, 0.035, 0.2, 0.035, '#7a5c3e', x, 0.1, z))
  box(garden, 0.38, 0.03, 0.3, '#8a6a48', -0.12, 0.215, 0.38)
  addPot(-0.12, 0.23, 0.38, 0.1, 0.15, '#f2f1e8', '#3d6c9a')
  const heart = new THREE.Shape()
  heart.moveTo(0, 0)
  heart.bezierCurveTo(-0.06, 0.02, -0.065, 0.1, 0, 0.14)
  heart.bezierCurveTo(0.065, 0.1, 0.06, 0.02, 0, 0)
  const heartGeo = new THREE.ShapeGeometry(heart, 8)
  const greens = ['#3f8a5f', '#58a172', '#74b383'].map((c) => mat(c, { side: THREE.DoubleSide, roughness: 0.8 }))
  for (let k = 0; k < 13; k++) {
    const yaw = new THREE.Group()
    yaw.position.set(-0.12, 0.37, 0.38)
    yaw.rotation.y = k * 2.4
    const tilt = new THREE.Group()
    tilt.rotation.x = 0.5 + rnd() * 1.75 // 有的挺著，有的垂到盆外
    const len = 0.07 + rnd() * 0.13
    const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.004, 0.004, len, 5), greens[0])
    stem.position.y = len / 2
    const leaf = new THREE.Mesh(heartGeo, greens[k % 3])
    leaf.position.y = len
    leaf.rotation.x = 0.4
    leaf.scale.setScalar(0.75 + rnd() * 0.5)
    leaf.castShadow = true
    tilt.add(stem, leaf)
    yaw.add(tilt)
    garden.add(yaw)
  }

  // 前面的小陶盆：一小叢葉子，開著幾朵紅花
  addPot(0.3, 0, 0.1, 0.075, 0.11, '#c98a63')
  const bush = new THREE.Mesh(new THREE.IcosahedronGeometry(0.085, 1), mat('#4c9a6c', { flatShading: true }))
  bush.scale.set(1.15, 0.8, 1.15)
  bush.position.set(0.3, 0.15, 0.1)
  bush.castShadow = true
  garden.add(bush)
  for (let k = 0; k < 6; k++) {
    const f = new THREE.Mesh(new THREE.IcosahedronGeometry(0.02, 0), mat(k % 2 ? '#d9534a' : '#e8756a', { flatShading: true }))
    f.position.set(0.3 + Math.sin(k * 2.4) * 0.06, 0.2 + rnd() * 0.03, 0.1 + Math.cos(k * 2.4) * 0.06)
    garden.add(f)
  }

  // 樓梯間天花板的日光燈：鐵殼、一支燈管
  box(g, 0.16, 0.05, 1.3, '#e6e6de', 8, 2.975, -2.2, { roughness: 0.5 })
  o.tubeMat = new THREE.MeshStandardMaterial({ color: '#f4f4ee', emissive: '#f2f6ff', emissiveIntensity: 0 })
  const tubeLamp = new THREE.Mesh(new THREE.CylinderGeometry(0.016, 0.016, 1.2, 12), o.tubeMat)
  tubeLamp.rotation.x = Math.PI / 2
  tubeLamp.position.set(8, 2.935, -2.2)
  g.add(tubeLamp)
  hallBulb = new THREE.PointLight('#f1f4f6', 0, 10, 2)
  hallBulb.position.set(8, 2.8, -2.2)
  g.add(hallBulb)
}

// ── 每一格：把 day 變成屋子的樣子 ─────────────────────
const CELLS = [0, 2, 3, 5, 8, 9, 11, 13, 16, 17, 19, 22, 24, 26]
const WEEKLY = [3, 10, 17, 24]
const last = {}

function applyDay(t, dt) {
  const d = props.day
  const night = props.time === 'night'
  const mended = props.mends.length > 0
  const has = (id) => props.mends.includes(id)
  const found = !mended && d > FOUND_DAY // 被發現之後：屋子清空了

  // 黃金葛
  const health = mended ? 1 : clamp(1 - (d - 2) / 19)
  o.leafMat.color.set('#3f8a5f').lerp(tmpColor.set('#a39a62'), 1 - health)
  o.leaves.forEach((l, i) => (l.tilt.rotation.x = lerp(2.25 + (i % 2) * 0.25, l.base, health)))

  // 日曆：過了那一天，就沒有人撕了
  const wd = dateOf(Math.min(d, 0))
  const calKey = wd.month * 100 + wd.date
  if (last.cal !== calKey) o.cal.redraw(wd), (last.cal = calKey)

  // 行事曆：退休前滿滿的，之後一格一格空下來
  const n = d <= -90 ? 14 : d < 0 ? Math.round(1 + (13 * -d) / 90) : 0
  const weekly = has('chief') && d > -14
  const pk = n + (weekly ? 100 : 0)
  if (last.planner !== pk) {
    const marks = CELLS.slice(0, n)
    o.planner.redraw(weekly ? [...new Set([...marks, ...WEEKLY])] : marks, weekly)
    last.planner = pk
  }

  // 手機
  const unread = mended || d <= 0.5 ? 0 : Math.round(d * 2.9)
  const lit = unread > 0 || d <= 0.5
  const sk = lit ? unread : -1
  if (last.screen !== sk) {
    o.screen.redraw(sk)
    if (unread) o.badge.redraw(unread)
    last.screen = sk
  }
  o.screenMat.emissiveIntensity = props.calling ? 1.5 + Math.sin(t * 22) * 0.9 : lit ? (night ? 0.9 : 0.5) : 0.05
  o.badgeSprite.visible = unread > 0

  // 冰箱上的單子、麵、熱氣
  const note = clamp((d + 20) / 2)
  o.note.visible = note > 0.01
  o.noteMat.opacity = note
  const bowl = clamp((d + 0.4) / 0.4)
  o.bowl.visible = bowl > 0.01
  o.bowl.scale.setScalar(Math.max(0.01, bowl))
  const steam = Math.abs(d) < 0.5 ? 1 - Math.abs(d) * 2 : 0
  o.steam.forEach((s) => {
    const k = (t * 0.25 + s.userData.phase) % 1
    s.position.set(Math.sin(k * 6 + s.userData.phase * 9) * 0.02, 0.1 + k * 0.3, 0)
    s.scale.setScalar(0.07 + k * 0.1)
    s.material.opacity = steam * Math.sin(k * Math.PI) * 0.55
  })

  // 灰塵
  const dust = mended ? 0 : clamp(d / FOUND_DAY)
  o.dustMat.opacity = dust * (night ? 0.25 : 0.9)
  o.dust.position.y = Math.sin(t * 0.15) * 0.06
  o.dust.rotation.y = Math.sin(t * 0.05) * 0.02

  // 信箱、通知單、門縫的光
  // 第 90 天之後清潔公司來過：信收走、通知單撕掉、燈關了，門上貼了「租」
  const cleaned = mended ? 0 : clamp((d - FOUND_DAY) / 6)
  const mail = mended ? 0 : clamp(d / FOUND_DAY) * 7 * (1 - cleaned)
  o.letters.forEach((m, i) => {
    const a = clamp(mail - i)
    m.visible = a > 0.01
    m.position.y = lerp(0.4 - m.userData.h / 2 - 0.02, 0.4 + m.userData.h * 0.18, a)
  })
  o.fallen.forEach((m, i) => (m.visible = mail > 5.5 + i * 0.7))
  o.slips.forEach((m, i) => {
    const a = mended ? 0 : clamp((d - [30, 58, 84][i]) / 2) * (1 - cleaned)
    m.visible = a > 0.01
    m.material.opacity = a
  })
  const rent = mended ? 0 : clamp((d - FOUND_DAY - 8) / 4)
  o.rent.visible = rent > 0.01
  o.rent.material.opacity = rent
  o.hallSlippers.visible = cleaned < 0.5 && !(mended && !props.alive && d > 100)
  o.guestShoes.visible = props.alive && d > 85 // 結尾：小妤回來了
  o.coupletMat.opacity = props.alive && d > 85 ? 1 : 0.72
  o.deo.visible = !mended && d > 18 && cleaned < 0.5
  const lampOn = night || (d >= 0 && cleaned < 0.5 && !(props.alive && d > 1)) || (props.alive && props.time === 'dusk')

  // 阿誠
  const breathe = Math.sin(t * 1.3) * 0.014
  let standing = d <= -52
  let slump = smooth(d, -1.2, 0) // 倒帶經過那一天時，他會慢慢坐起來
  let gone = found && cleaned > 0.3
  if (props.alive) {
    slump = 0
    standing = d <= -52 || d > 45
  }
  o.standing.root.visible = (standing && !gone) || props.greet
  // 結尾：電鈴響了，他走過來開門
  o.greetK = lerp(o.greetK || 0, props.greet ? 1 : 0, 1 - Math.exp(-dt * 2.2))
  if (props.greet) {
    // 先走過來（約一秒半，走三步），到門口停下來才舉手
    o.walkT = Math.min(1, (o.walkT || 0) + dt / 1.6)
    const u = o.walkT
    const ease = u * u * (3 - 2 * u)
    const stepK = Math.sin(Math.PI * u) ** 0.6 // 起步和停下來的時候步子小
    const ph = u * Math.PI * 3
    o.standing.root.position.set(5.05 + 0.9 * ease, 0.82 + Math.abs(Math.sin(ph)) * 0.018 * stepK, -3.0)
    o.standing.root.rotation.y = Math.PI
    o.standing.legs?.forEach(({ hip, knee }, i) => {
      const s = Math.sin(ph + i * Math.PI) * stepK
      hip.rotation.z = -0.38 * s
      knee.rotation.z = 0.55 * Math.max(0, -Math.cos(ph + i * Math.PI)) * stepK
    })
  } else {
    o.walkT = 0
    o.standing.legs?.forEach(({ hip, knee }) => (hip.rotation.z = knee.rotation.z = 0))
    o.standing.root.position.set(1.62, 0.82, -4.3)
    o.standing.root.rotation.y = -Math.PI / 2
  }
  o.seated.root.visible = !standing && !gone
  if (props.alive && d > -0.6 && d < 3) setPose(o.seated, POSE.doze, POSE.call, smooth(d, -0.6, -0.2), breathe)
  else setPose(o.seated, POSE.doze, POSE.slump, slump, breathe * (1 - slump))
  const waveK = props.greet ? smooth(o.walkT || 0, 0.75, 1) : 0 // 走到門口才舉手
  setPose(o.standing, POSE.water, POSE.wave, props.greet ? Math.max(waveK, smooth(o.walkT || 0, 0, 0.3)) : 0, breathe)
  if (props.greet && o.walkT < 0.75) {
    // 走路時兩手跟著腳反方向擺
    const ph = o.walkT * Math.PI * 3, k = Math.sin(Math.PI * o.walkT) ** 0.6
    o.standing.L.sh.rotation.z += 0.3 * Math.sin(ph + Math.PI) * k
    o.standing.R.sh.rotation.z += 0.3 * Math.sin(ph) * k
  }
  o.standing.R.sh.rotation.x = 0.55 * waveK // 右手往旁邊抬
  o.standing.R.el.rotation.x = (2.1 + Math.sin(t * 5) * 0.22) * waveK // 小手臂舉起來，輕輕地揮
  if (o.can) o.can.visible = !props.greet // 來開門的時候手上沒有澆水壺
  o.pomelo.visible = has('neighbor') && d > -14

  // 屋子越來越亂：退休那天很整齊，到倒下那天全部出現；大家都關心他的時間線裡，維持整齊
  const messK = mended ? 0.15 : clamp((Math.min(d, 0) + 88) / 80)
  o.mess.forEach(({ at, obj }) => {
    const k = clamp((messK - at) / 0.05)
    obj.visible = k > 0.02
    obj.scale.setScalar(Math.max(0.02, k))
  })
  o.gift.visible = d > -30
  o.dailyPaper.visible = d > -80 && !props.paper
  o.endPaper.visible = props.paper
  o.boxes.visible = !mended && d > FOUND_DAY + 1
  const power = mended || cleaned < 0.5 // 被發現之後，有人把電器都關了
  if (power) o.fanBlades.rotation.z += dt * 17
  o.fanHead.rotation.y = 1.25 + (power ? Math.sin(t * 0.45) * 0.55 : 0)
  o.pendulum.rotation.z = mended || d < 55 ? Math.sin(t * 3.1) * 0.22 : 0.04 // 掛鐘的電池在第五十幾天用完
  // 電視：他習慣從早開到晚。倒下那天也開著，一直開到被發現
  const tvOn = props.tv || (power && d > -50 && (night || d >= 0))
  o.tvMat.emissiveIntensity = tvOn ? 0.95 + Math.sin(t * 13) * 0.25 + Math.sin(t * 5.3) * 0.2 : 0

  // 里長只出現在倒下後第 1 天的門口；按電鈴時手會伸出去
  // 被發現那天，他和員警一起站在門口
  o.arriveK = lerp(o.arriveK || 0, props.arrived ? 1 : 0, 1 - Math.exp(-dt * 3))
  const chief = Math.max(o.arriveK, mended ? 0 : smooth(d, 0.82, 0.94) * (1 - smooth(d, 1.06, 1.18)))
  o.chief.root.visible = chief > 0.02
  o.chief.root.scale.setScalar(Math.max(0.02, chief))
  o.chief.root.position.set(o.arriveK > 0.02 ? 7.0 : 6.78, 0.82 * Math.max(0.02, chief), o.arriveK > 0.02 ? -4.05 : -3.395)
  o.police.root.visible = o.arriveK > 0.02
  o.police.root.scale.setScalar(Math.max(0.02, o.arriveK))
  o.police.root.position.y = 0.82 * Math.max(0.02, o.arriveK)
  setPose(o.police, POSE.wait, POSE.wait, 0, breathe)

  // 樓下的街景只在那個鏡頭出現；對面的公寓那時要讓開
  const crowd = props.shot === 'crowd'
  o.street.visible = crowd
  o.far.forEach((m) => (m.visible = !crowd))
  if (crowd) {
    const flash = Math.sin(t * 9) > 0 ? 1 : 0.15
    o.sirenMat.emissiveIntensity = 0.4 + flash * 2.2
    o.sirenLight.intensity = flash * 16
    o.crowd.forEach((f, k) => {
      setPose(f, POSE.wait, POSE.wait, 0, Math.sin(t * 1.1 + k) * 0.012)
      f.head.rotation.z = -0.28 + Math.sin(t * 0.5 + k * 1.7) * 0.06 // 抬頭看
      f.head.rotation.y = Math.sin(t * 0.33 + k * 2.3) * 0.35 // 偶爾轉頭跟旁邊的人說話
    })
  } else o.sirenLight.intensity = 0
  o.ringK = lerp(o.ringK || 0, props.ringing ? 1 : 0, 1 - Math.exp(-dt * 9))
  setPose(o.chief, POSE.wait, POSE.ring, o.ringK, breathe)
  o.bellBtn.emissiveIntensity = props.ringing ? 1.6 + Math.sin(t * 9) * 0.6 : 0.15
  o.doorNote.visible = !mended && d >= 0.95 && cleaned < 0.5
  // 房東只出現在被發現的那一天
  const lord = mended ? 0 : smooth(d, FOUND_DAY - 0.18, FOUND_DAY - 0.06) * (1 - smooth(d, FOUND_DAY + 0.06, FOUND_DAY + 0.18))
  o.landlord.root.visible = lord > 0.02
  o.landlord.root.scale.setScalar(Math.max(0.02, lord))
  o.landlord.root.position.y = 0.82 * Math.max(0.02, lord)
  setPose(o.landlord, POSE.wait, POSE.reach, clamp((o.openK || 0) * 3), breathe)

  // 陳太太：兩個禮拜前提著柚子站在門外；或是他活下來的那個晚上，拿備用鑰匙開門進來
  o.rescue = lerp(o.rescue || 0, props.alive && d > 0.15 && d < 1.6 ? 1 : 0, 1 - Math.exp(-dt * 5))
  const porch = props.shot === 'porch'
  const nb = porch ? 1 : Math.max(0.05, o.rescue)
  o.neighbor.root.visible = porch || o.rescue > 0.05
  o.neighbor.root.scale.setScalar(nb)
  o.neighbor.root.position.set(porch ? 6.78 : 5.72, 0.82 * nb, porch ? -3.395 : -2.92)
  o.bag.visible = porch
  o.nbRing = lerp(o.nbRing || 0, porch && props.ringing ? 1 : 0, 1 - Math.exp(-dt * 9))
  setPose(o.neighbor, POSE.wait, POSE.ring, o.nbRing, breathe)
  o.rod.visible = has('kun') && d > -85
  const gapOn = props.gap ?? lampOn
  o.gapMat.emissiveIntensity = gapOn ? 2.2 : 0
  gapLight.intensity = gapOn ? 0.9 : 0
  o.bulbMat.emissiveIntensity = lampOn ? 2.5 : 0
  cur.lampI = lerp(cur.lampI, lampOn ? (night ? 8 : 1.6) : 0, 0.08)
  lamp.intensity = cur.lampI
}

function applyLight(dt, travelDim, inHall) {
  const L = LIGHT[props.time] || LIGHT.day
  const k = 1 - Math.exp(-dt * 3.2)
  cur.bg.lerp(tmpColor.set(L.bg), k)
  cur.hemi.lerp(tmpColor.set(L.hemi), k)
  cur.sun.lerp(tmpColor.set(L.sun), k)
  cur.hemiI = lerp(cur.hemiI, L.hemiI, k)
  cur.sunI = lerp(cur.sunI, L.sunI, k)
  cur.sunY = lerp(cur.sunY, L.sunY, k)
  hemi.color.copy(cur.hemi)
  hemi.intensity = cur.hemiI
  scene.environmentIntensity = Math.max(0.012, (cur.hemiI - 0.45) * 0.085) // 環境反射跟著天光變暗，晚上幾乎沒有
  sun.color.copy(cur.sun)
  sun.intensity = cur.sunI * travelDim
  // 樓梯間：斜陽從側面掃過牆；客廳：太陽在後牆外面，光從鐵窗照進來
  if (inHall) {
    sun.position.set(15.5, 3.4, -11.5)
    sun.target.position.set(6.2, 1, -2.6)
  } else {
    sun.position.set(0.2, cur.sunY, -11)
    sun.target.position.set(2.6, 0, -2.2)
  }
  o.sky.material.color.copy(cur.bg)
  const night = props.time === 'night'
  o.bldg.color.lerp(tmpColor.set(night ? '#1f333b' : '#a9bcc0'), k)
  o.winMat.emissiveIntensity = lerp(o.winMat.emissiveIntensity, night ? 1.6 : 0, k)
  hallBulb.intensity = lerp(hallBulb.intensity, props.time === 'dusk' ? 1.2 : night ? 3.2 : 0, k)
  o.tubeMat.emissiveIntensity = hallBulb.intensity * 0.9
}

const camPos = new THREE.Vector3()
const camLook = new THREE.Vector3()
const right = new THREE.Vector3()
const proj = new THREE.Vector3()
const sm = { pos: new THREE.Vector3(), look: new THREE.Vector3(), fov: 0, key: '', e: -1 }

function applyCamera(t, dt, w, h) {
  const p = props.progress
  // 底部有介面時，把構圖放進上面沒被蓋住的那一塊
  sm.e = sm.e < 0 ? props.safeBottom : lerp(sm.e, props.safeBottom, 1 - Math.exp(-dt * 3))
  const vh = Math.max(160, h - sm.e)
  const aspect = w / vh
  const narrow = clamp((0.8 - aspect) / 0.3) // 視角已經開到上限的窄螢幕，鏡頭才需要往後退
  const travel = !!props.nextKind && props.nextKind !== props.kind
  let fov
  let doorOpen = 0
  let u = 0
  let roomness = props.kind === 'room' ? 1 : 0
  if (travel && p > 0) {
    u = ease(p)
    const dir = props.kind === 'hall' ? u : 1 - u // 路線是 hall → room
    pathPos.getPoint(dir, camPos)
    pathLook.getPoint(dir, camLook)
    fov = lerp(CAM.hall.fov, CAM.room.fov, smooth(dir, 0.15, 0.6))
    doorOpen = smooth(dir, 0.1, 0.3) * (1 - smooth(dir, 0.52, 0.7))
    roomness = smooth(dir, 0.6, 1)
  } else {
    const c = CAM[props.shot] || CAM[props.view] || CAM[props.kind] || CAM.room
    const bell = Math.sin(Math.PI * p)
    camPos.copy(c.pos)
    camLook.copy(c.look)
    fov = c.fov + bell * 3
    if (props.shot) {
      // 切過去之後，慢慢往裡推近
      sm.shotT = (sm.shotT || 0) + dt
      camPos.lerp(c.look, Math.min(0.12, sm.shotT * 0.02))
      roomness = 0
    } else if (props.kind === 'room') camPos.add(V(0.5 * bell, 0.06 * bell, 0.45 * bell))
    else camPos.add(V(0.5 * bell, 0.04 * bell, 0.5 * bell))
    // 玩家點開一個圓點時，鏡頭往那樣東西靠近一點
    if (props.focus && !props.shot && p === 0 && !props.view) {
      const f = V(props.focus[0], props.focus[1], props.focus[2])
      camLook.lerp(f, 0.32)
      camPos.lerp(f, 0.15)
    }
  }
  // 直式螢幕：客廳的鏡頭往後退，才裝得下窗和門
  camPos.z += 1.8 * narrow * roomness

  // 平常慢慢靠過去；倒帶中、或換了場景，就直接到位
  const key = props.kind + (props.view || '')
  const cut = sm.shot !== props.shot // 切進、切出門後的鏡頭都是直接跳
  if (cut) sm.shotT = 0
  sm.shot = props.shot
  const snap = cut || p > 0 || sm.key === '' || (sm.key !== key && sm.key.slice(0, 4) !== key.slice(0, 4))
  const k = snap ? 1 : 1 - Math.exp(-dt * 2.6)
  sm.key = key
  sm.pos.lerp(camPos, k)
  sm.look.lerp(camLook, k)
  sm.fov = snap ? fov : lerp(sm.fov, fov, k)

  // 滑鼠視差＋很慢的呼吸
  pointer.sx = lerp(pointer.sx, pointer.x, 0.06)
  pointer.sy = lerp(pointer.sy, pointer.y, 0.06)
  right.subVectors(sm.look, sm.pos).cross(camera.up).normalize()
  camera.position.copy(sm.pos)
  camera.position.addScaledVector(right, pointer.sx * 0.28 + Math.sin(t * 0.35) * 0.04)
  camera.position.y += -pointer.sy * 0.1 + Math.sin(t * 0.27) * 0.015

  let f = sm.fov
  if (aspect < 5 / 3) f = Math.min(88, (2 * Math.atan((Math.tan((f * Math.PI) / 360) * (5 / 3)) / aspect) * 180) / Math.PI)
  camera.fov = f
  camera.setViewOffset(w, vh, 0, 0, w, h)
  camera.lookAt(sm.look)
  o.openK = lerp(o.openK || 0, props.opening ? 1 : 0, 1 - Math.exp(-dt * (props.opening ? 0.9 : 4)))
  // 從門後看的時候，門要整個貼到牆上，不然會擋住鏡頭
  const wide = props.shot === 'inside' && props.opening ? 1 : 0
  o.door.rotation.y = -1.75 * Math.max(doorOpen, wide, (o.rescue || 0) * 0.75, o.openK * 0.62, (o.greetK || 0) * 0.8)
  const moving = travel && p > 0
  const dirNow = props.kind === 'hall' ? u : 1 - u
  return {
    travelDim: moving ? 1 - 0.85 * Math.sin(Math.PI * u) ** 2 : 1,
    inHall: props.shot ? props.shot === 'porch' : moving ? dirNow < 0.42 : props.kind === 'hall',
  }
}

// 圓點跟著 3D 位置走，但永遠留在畫面裡，不會跑到點不到的地方
function placeHotspots(w, h) {
  const m = 30
  props.hotspots.forEach((hs) => {
    const el = hotEls.get(hs.id)
    if (!el) return
    proj.set(hs.at[0], hs.at[1], hs.at[2]).project(camera)
    const x = clamp(((proj.x + 1) / 2) * w, m, w - m)
    const y = clamp(((1 - proj.y) / 2) * h, m + 40, h - sm.e - m)
    el.style.transform = `translate(${x}px, ${y}px)`
  })
}

let prev = 0
function loop(now) {
  raf = requestAnimationFrame(loop)
  const t = now / 1000
  const dt = Math.min(0.1, t - prev || 0.016)
  prev = t
  const w = host.value.clientWidth
  const h = host.value.clientHeight
  if (!w || !h) return
  const cam = applyCamera(t, dt, w, h)
  applyDay(t, dt)
  o.figures?.forEach(syncFigure)
  applyLight(dt, cam.travelDim, cam.inHall)
  renderer.render(scene, camera)
  placeHotspots(w, h)
}

function onPointer(e) {
  const r = host.value.getBoundingClientRect()
  pointer.x = clamp(((e.clientX - r.left) / r.width) * 2 - 1, -1, 1)
  pointer.y = clamp(((e.clientY - r.top) / r.height) * 2 - 1, -1, 1)
}

onMounted(async () => {
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' })
  } catch (e) {
    failed.value = true
    return
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.shadowMap.enabled = true
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  renderer.toneMappingExposure = 0.86
  host.value.prepend(renderer.domElement)

  const L = LIGHT[props.time] || LIGHT.day
  cur.bg.set(L.bg)
  cur.hemi.set(L.hemi)
  cur.sun.set(L.sun)
  Object.assign(cur, { hemiI: L.hemiI, sunI: L.sunI, sunY: L.sunY })
  await loadPeople()
  if (!host.value) return // 載入途中元件被卸載了
  build()
  // 一點環境反射，讓磨石子地、木頭、電器有光澤
  const pm = new THREE.PMREMGenerator(renderer)
  scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture
  pm.dispose()

  ro = new ResizeObserver(() => renderer.setSize(host.value.clientWidth, host.value.clientHeight, false))
  ro.observe(host.value)
  window.addEventListener('pointermove', onPointer)
  // 字型載入後，把畫了字的貼圖重畫一次
  document.fonts?.ready.then(() => {
    last.cal = last.planner = last.screen = null
    o.redrawLabels?.forEach((f) => f())
  })
  raf = requestAnimationFrame(loop)
})

onBeforeUnmount(() => {
  cancelAnimationFrame(raf)
  ro?.disconnect()
  window.removeEventListener('pointermove', onPointer)
  if (scene)
    scene.traverse((m) => {
      m.geometry?.dispose()
      ;[].concat(m.material || []).forEach((x) => (x.map?.dispose(), x.dispose()))
    })
  renderer?.dispose()
})
</script>

<template>
  <div ref="host" class="scene" :aria-label="kind === 'hall' ? '公寓二樓的樓梯間，一扇紅色鐵門' : '阿誠的客廳'" role="group">
    <p v-if="failed" class="scene-failed">這個瀏覽器沒辦法顯示 3D 場景。請換一個支援 WebGL 的瀏覽器再試一次。</p>
    <button v-for="h in hotspots" :key="h.id" :ref="setHot(h.id)" class="hot" :class="{ found: h.found, off: !interactive }"
            :tabindex="interactive ? 0 : -1" :aria-label="h.label + (h.found ? '（看過了）' : '')" :title="h.label"
            @click="interactive && emit('pick', h)">
      <span class="hot-pulse" /><span class="hot-dot" />
    </button>
  </div>
</template>

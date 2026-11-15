import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { viteSingleFile } from 'vite-plugin-singlefile'

// `npm run build:single` 會輸出一個可以直接點兩下打開的 dist-single/index.html
export default defineConfig(({ mode }) => ({
  base: './',
  assetsInclude: ['**/*.glb'], // 人物模型，用 ?inline 併進程式裡，單一檔案版才打得開
  plugins: [vue(), ...(mode === 'single' ? [viteSingleFile()] : [])],
  build: mode === 'single' ? { outDir: 'dist-single' } : {},
}))

// 主题（暗色）管理：默认跟随系统 prefers-color-scheme；手动切换后记忆到 localStorage。
// 约定：html.dark 类 + Element Plus dark css-vars；首屏由 index.html 内联脚本预热避免闪烁。
import { defineStore } from 'pinia'
import { ref } from 'vue'

const KEY = 'cr-theme'

export const useThemeStore = defineStore('theme', () => {
  const saved = typeof localStorage !== 'undefined' ? localStorage.getItem(KEY) : null
  const manual = ref(saved === 'dark' || saved === 'light')
  const media = typeof window !== 'undefined' ? window.matchMedia('(prefers-color-scheme: dark)') : null
  const dark = ref(saved ? saved === 'dark' : Boolean(media && media.matches))

  function apply() {
    document.documentElement.classList.toggle('dark', dark.value)
    document.documentElement.style.colorScheme = dark.value ? 'dark' : 'light'
  }

  function toggle() {
    dark.value = !dark.value
    manual.value = true
    localStorage.setItem(KEY, dark.value ? 'dark' : 'light')
    apply()
  }

  // 未手动选择时，持续跟随系统主题变化
  if (media) {
    media.addEventListener('change', (e) => {
      if (!manual.value) {
        dark.value = e.matches
        apply()
      }
    })
  }

  apply()
  return { dark, toggle }
})

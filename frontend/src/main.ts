import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import App from './App.vue'
import router from './router'
import { useThemeStore } from './stores/theme'
import './styles/global.css'

const app = createApp(App)
app.use(createPinia())
// 暗色初始化：pinia 装载后立即实例化主题 store（应用 html.dark 与 color-scheme）
useThemeStore()
app.use(router)
app.use(ElementPlus, { locale: zhCn })
app.mount('#app')

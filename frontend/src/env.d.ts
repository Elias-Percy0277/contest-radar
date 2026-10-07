/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<object, object, unknown>
  export default component
}

interface ImportMetaEnv {
  /** 置为 '1' 时强制使用本地 Mock 数据（SPEC §7） */
  readonly VITE_USE_MOCK?: string
}

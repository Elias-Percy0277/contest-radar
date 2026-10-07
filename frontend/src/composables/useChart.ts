// ECharts 组合式封装：主题切换时按明/暗重建实例，窗口尺寸变化自适应
import * as echarts from 'echarts'
import { onBeforeUnmount, onMounted, watch, type Ref } from 'vue'
import type { EChartsOption } from 'echarts'
import { useThemeStore } from '../stores/theme'

export function useChart(el: Ref<HTMLElement | undefined>, optionFactory: () => EChartsOption) {
  const theme = useThemeStore()
  let chart: ReturnType<typeof echarts.init> | null = null

  function render() {
    if (!el.value) return
    chart?.dispose()
    chart = echarts.init(el.value, theme.dark ? 'dark' : undefined)
    chart.setOption(optionFactory())
  }

  function resize() {
    chart?.resize()
  }

  onMounted(() => {
    render()
    window.addEventListener('resize', resize)
  })
  onBeforeUnmount(() => {
    window.removeEventListener('resize', resize)
    chart?.dispose()
    chart = null
  })
  // 主题切换（含跟随系统）时重建设计主题
  watch(
    () => theme.dark,
    () => render(),
  )
  return { rerender: render }
}

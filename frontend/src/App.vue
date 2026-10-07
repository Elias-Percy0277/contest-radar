<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useThemeStore } from './stores/theme'
import { useAppStore } from './stores/app'

const route = useRoute()
const theme = useThemeStore()
const appStore = useAppStore()

const active = computed(() => route.path)
const navs = [
  { path: '/', label: '仪表盘' },
  { path: '/list', label: '竞赛列表' },
  { path: '/calendar', label: '日历' },
  { path: '/countdown', label: '倒计时墙' },
  { path: '/schedule', label: '我的日程' },
]
</script>

<template>
  <div class="cr-shell">
    <header class="cr-header">
      <div class="cr-brand">
        <span class="cr-logo">📡</span>
        <span class="cr-title">竞赛雷达</span>
        <span class="cr-sub">ContestRadar</span>
      </div>
      <el-menu mode="horizontal" router :default-active="active" class="cr-nav" :ellipsis="false">
        <el-menu-item v-for="n in navs" :key="n.path" :index="n.path">{{ n.label }}</el-menu-item>
      </el-menu>
      <div class="cr-actions">
        <el-tag v-if="appStore.isMock" type="warning" size="small" effect="plain">Mock 演示数据</el-tag>
        <el-button size="small" text bg @click="theme.toggle()">
          {{ theme.dark ? '☀️ 浅色' : '🌙 暗色' }}
        </el-button>
      </div>
    </header>
    <main class="cr-main">
      <router-view />
    </main>
  </div>
</template>

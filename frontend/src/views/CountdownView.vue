<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { Contest } from '../types'
import MyStatusButtons from '../components/MyStatusButtons.vue'
import StatusTag from '../components/StatusTag.vue'
import { countdownText, deadlineMoment, formatRange } from '../utils/format'

type WithDeadline = Contest & { reg_deadline: string }

const contests = ref<WithDeadline[]>([])
const loading = ref(false)
const now = ref(Date.now())
let timer: number | undefined

async function load() {
  loading.value = true
  try {
    const resp = await api.getContests({ hidden: '1', sort: 'deadline' })
    contests.value = resp.items.filter((c): c is WithDeadline => typeof c.reg_deadline === 'string')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  load()
  // 每分钟刷新倒计时（SPEC §7）
  timer = window.setInterval(() => {
    now.value = Date.now()
  }, 60 * 1000)
})
onBeforeUnmount(() => {
  if (timer !== undefined) window.clearInterval(timer)
})

function remainMs(c: WithDeadline): number {
  return deadlineMoment(c.reg_deadline).getTime() - now.value
}

// 未截止：按 reg_deadline 升序
const active = computed(() =>
  contests.value
    .filter((c) => remainMs(c) > 0)
    .slice()
    .sort((a, b) => a.reg_deadline.localeCompare(b.reg_deadline)),
)
// 已截止：折叠分组内按最近截止在前
const expired = computed(() =>
  contests.value
    .filter((c) => remainMs(c) <= 0)
    .slice()
    .sort((a, b) => b.reg_deadline.localeCompare(a.reg_deadline)),
)

function urgency(c: WithDeadline): 'urgent' | 'soon' | 'ok' {
  const days = remainMs(c) / 86400000
  if (days <= 3) return 'urgent'
  if (days <= 7) return 'soon'
  return 'ok'
}
function onUpdated() {
  load()
}
</script>

<template>
  <div v-loading="loading" class="cr-page">
    <el-card shadow="never" class="cr-card">
      <template #header>
        <b>报名倒计时</b>
        <span class="cr-text-secondary" style="margin-left: 8px">按报名截止时间升序，每分钟自动刷新</span>
      </template>
      <el-empty v-if="!active.length" description="暂无进行中的报名倒计时" />
      <el-row v-else :gutter="16">
        <el-col v-for="c in active" :key="c.id" :span="8" class="cd-col">
          <div class="cd-card" :class="'border-' + urgency(c)">
            <div class="cd-head">
              <el-tag v-if="c.is_new" type="danger" size="small" effect="dark">NEW</el-tag>
              <StatusTag :status="c.status" />
              <span class="cr-text-secondary cd-cat">{{ c.category }}</span>
            </div>
            <el-link :href="c.url" target="_blank" type="primary" class="cd-title">{{ c.title }}</el-link>
            <div class="cd-time" :class="urgency(c)">{{ countdownText(c.reg_deadline, now) }}</div>
            <div class="cr-text-secondary">报名截止：{{ c.reg_deadline }}</div>
            <div class="cr-text-secondary">比赛：{{ formatRange(c.contest_start, c.contest_end) }}</div>
            <div class="cd-actions">
              <MyStatusButtons :contest="c" @updated="onUpdated" />
            </div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never" class="cr-card">
      <el-collapse>
        <el-collapse-item :title="'已截止（' + expired.length + '）'" name="expired">
          <el-empty v-if="!expired.length" description="没有已截止的报名" :image-size="70" />
          <el-row v-else :gutter="16">
            <el-col v-for="c in expired" :key="c.id" :span="8" class="cd-col">
              <div class="cd-card expired">
                <div class="cd-head">
                  <StatusTag :status="c.status" />
                  <span class="cr-text-secondary cd-cat">{{ c.category }}</span>
                </div>
                <el-link :href="c.url" target="_blank" type="info" class="cd-title">{{ c.title }}</el-link>
                <div class="cd-time muted">已截止</div>
                <div class="cr-text-secondary">报名截止：{{ c.reg_deadline }}</div>
                <div class="cd-actions">
                  <MyStatusButtons :contest="c" @updated="onUpdated" />
                </div>
              </div>
            </el-col>
          </el-row>
        </el-collapse-item>
      </el-collapse>
    </el-card>
  </div>
</template>

<style scoped>
.cd-col {
  margin-bottom: 16px;
}
.cd-card {
  height: 100%;
  box-sizing: border-box;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 14px 16px;
  background: var(--el-bg-color);
}
.cd-card.border-urgent {
  border-color: var(--el-color-danger);
}
.cd-card.border-soon {
  border-color: var(--el-color-warning);
}
.cd-card.expired {
  opacity: 0.62;
}
.cd-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}
.cd-cat {
  font-size: 12px;
}
.cd-title {
  font-weight: 600;
  font-size: 15px;
  margin-bottom: 8px;
  white-space: normal;
  line-height: 1.4;
}
.cd-time {
  font-size: 26px;
  font-weight: 700;
  margin: 6px 0 4px;
}
.cd-time.urgent {
  color: var(--el-color-danger);
}
.cd-time.soon {
  color: var(--el-color-warning);
}
.cd-time.ok {
  color: var(--el-color-success);
}
.cd-time.muted {
  color: var(--el-text-color-secondary);
}
.cd-actions {
  margin-top: 8px;
}
</style>

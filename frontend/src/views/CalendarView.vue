<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { Contest } from '../types'
import StatusTag from '../components/StatusTag.vue'
import MyStatusButtons from '../components/MyStatusButtons.vue'
import { formatRange } from '../utils/format'

interface DayInfo {
  deadlines: Contest[]
  starts: Contest[]
  joined: boolean
}
interface Cell {
  date: string
  day: number
  inMonth: boolean
  isToday: boolean
  info?: DayInfo
}

const contests = ref<Contest[]>([])
const loading = ref(false)

// 日历页需要完整数据（含 ignored，用于全面标记），hidden=1 拉取
async function load() {
  loading.value = true
  try {
    const resp = await api.getContests({ hidden: '1', sort: 'deadline' })
    contests.value = resp.items
  } finally {
    loading.value = false
  }
}
onMounted(load)

function pad(n: number): string {
  return n < 10 ? '0' + n : String(n)
}
function fmt(d: Date): string {
  return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate())
}
function monthStart(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1)
}
function shiftMonth(d: Date, delta: number): Date {
  return new Date(d.getFullYear(), d.getMonth() + delta, 1)
}

const cursor = ref(monthStart(new Date()))
const selectedDate = ref(fmt(new Date()))
const WEEK_LABELS = ['一', '二', '三', '四', '五', '六', '日']

// 按日期索引：reg_deadline → 橙点、contest_start → 蓝点；joined 竞赛钉住其相关日期
const byDate = computed(() => {
  const map = new Map<string, DayInfo>()
  const get = (k: string): DayInfo => {
    let v = map.get(k)
    if (!v) {
      v = { deadlines: [], starts: [], joined: false }
      map.set(k, v)
    }
    return v
  }
  contests.value.forEach((c) => {
    if (c.reg_deadline) get(c.reg_deadline).deadlines.push(c)
    if (c.contest_start) get(c.contest_start).starts.push(c)
    if (c.my_status === 'joined') {
      if (c.reg_deadline) get(c.reg_deadline).joined = true
      if (c.contest_start) get(c.contest_start).joined = true
    }
  })
  return map
})

// 6×7 月网格，周一为一周开始
const cells = computed<Cell[]>(() => {
  const first = cursor.value
  const offset = (first.getDay() + 6) % 7
  const start = new Date(first.getFullYear(), first.getMonth(), first.getDate() - offset)
  const todayKey = fmt(new Date())
  const list: Cell[] = []
  for (let i = 0; i < 42; i++) {
    const d = new Date(start.getFullYear(), start.getMonth(), start.getDate() + i)
    const key = fmt(d)
    list.push({
      date: key,
      day: d.getDate(),
      inMonth: d.getMonth() === first.getMonth(),
      isToday: key === todayKey,
      info: byDate.value.get(key),
    })
  }
  return list
})

const monthLabel = computed(() => cursor.value.getFullYear() + ' 年 ' + (cursor.value.getMonth() + 1) + ' 月')

function goToday() {
  cursor.value = monthStart(new Date())
  selectedDate.value = fmt(new Date())
}

// 侧栏：当日相关竞赛（报名截止 + 比赛开始）
interface SidebarItem {
  contest: Contest
  kind: 'deadline' | 'start'
}
const selectedItems = computed<SidebarItem[]>(() => {
  const info = byDate.value.get(selectedDate.value)
  if (!info) return []
  const list: SidebarItem[] = []
  info.deadlines.forEach((c) => list.push({ contest: c, kind: 'deadline' }))
  info.starts.forEach((c) => list.push({ contest: c, kind: 'start' }))
  return list
})
</script>

<template>
  <div v-loading="loading" class="cr-page">
    <el-row :gutter="16">
      <el-col :span="17">
        <el-card shadow="never" class="cr-card">
          <div class="cal-toolbar">
            <el-button size="small" @click="cursor = shiftMonth(cursor, -1)">‹ 上月</el-button>
            <span class="cal-month">{{ monthLabel }}</span>
            <el-button size="small" @click="cursor = shiftMonth(cursor, 1)">下月 ›</el-button>
            <el-button size="small" text type="primary" @click="goToday">今天</el-button>
          </div>
          <div class="cal-legend">
            <span><i class="dot dot-deadline"></i> 报名截止</span>
            <span><i class="dot dot-start"></i> 比赛开始</span>
            <span><i class="dot dot-joined"></i> 我参加的（描边高亮）</span>
          </div>
          <div class="cal-grid">
            <div v-for="w in WEEK_LABELS" :key="w" class="cal-head">{{ w }}</div>
            <div
              v-for="cell in cells"
              :key="cell.date"
              class="cal-cell"
              :class="{ out: !cell.inMonth, today: cell.isToday, joined: cell.info && cell.info.joined, selected: cell.date === selectedDate }"
              @click="selectedDate = cell.date"
            >
              <div class="cal-daynum">{{ cell.day }}</div>
              <div v-if="cell.info && cell.info.deadlines.length + cell.info.starts.length > 0" class="cal-dots">
                <i v-if="cell.info.deadlines.length" class="dot dot-deadline"></i>
                <i v-if="cell.info.starts.length" class="dot dot-start"></i>
                <span class="cal-count">{{ cell.info.deadlines.length + cell.info.starts.length }} 项</span>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="7">
        <el-card shadow="never" class="cr-card">
          <template #header><b>{{ selectedDate }}</b><span class="cr-text-secondary" style="margin-left: 6px">当日相关竞赛</span></template>
          <el-empty v-if="!selectedItems.length" description="当日暂无报名截止或开赛的竞赛" :image-size="80" />
          <div v-for="(it, i) in selectedItems" :key="i" class="cal-item">
            <div class="cal-item-head">
              <el-tag size="small" :type="it.kind === 'deadline' ? 'warning' : 'primary'">
                {{ it.kind === 'deadline' ? '报名截止' : '比赛开始' }}
              </el-tag>
              <StatusTag :status="it.contest.status" />
              <el-tag v-if="it.contest.my_status === 'joined'" type="success" size="small">我参加</el-tag>
              <el-tag v-else-if="it.contest.my_status === 'ignored'" type="info" size="small">已忽略</el-tag>
            </div>
            <el-link :href="it.contest.url" target="_blank" type="primary" class="cal-item-title">{{ it.contest.title }}</el-link>
            <div class="cr-text-secondary">{{ it.contest.category }} · {{ it.contest.source_name }}</div>
            <div class="cr-text-secondary">比赛：{{ formatRange(it.contest.contest_start, it.contest.contest_end) }}</div>
            <div class="cal-item-actions">
              <MyStatusButtons :contest="it.contest" @updated="load" />
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.cal-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}
.cal-month {
  font-size: 16px;
  font-weight: 700;
  min-width: 110px;
  text-align: center;
}
.cal-legend {
  display: flex;
  gap: 18px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 10px;
  align-items: center;
  flex-wrap: wrap;
}
.cal-legend span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.cal-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 6px;
}
.cal-head {
  text-align: center;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  padding: 2px 0;
}
.cal-cell {
  min-height: 74px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 6px 8px;
  cursor: pointer;
  background: var(--el-bg-color);
  transition: border-color 0.2s;
}
.cal-cell:hover {
  border-color: var(--el-color-primary-light-5);
}
.cal-cell.out {
  opacity: 0.4;
}
.cal-cell.today .cal-daynum {
  color: var(--el-color-primary);
  font-weight: 700;
}
.cal-cell.selected {
  border-color: var(--el-color-primary);
  box-shadow: inset 0 0 0 1px var(--el-color-primary);
}
.cal-cell.joined {
  border-color: var(--el-color-warning);
  box-shadow: inset 0 0 0 2px var(--el-color-warning-light-5);
}
.cal-daynum {
  font-size: 14px;
}
.cal-dots {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 6px;
}
.dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.dot-deadline {
  background: var(--el-color-warning);
}
.dot-start {
  background: var(--el-color-primary);
}
.dot-joined {
  background: transparent;
  border: 2px solid var(--el-color-warning);
}
.cal-count {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.cal-item {
  border-bottom: 1px dashed var(--el-border-color-lighter);
  padding: 10px 0;
}
.cal-item:last-child {
  border-bottom: none;
}
.cal-item-head {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 6px;
  flex-wrap: wrap;
}
.cal-item-title {
  font-weight: 600;
  line-height: 1.4;
  margin-bottom: 4px;
  white-space: normal;
}
.cal-item-actions {
  margin-top: 6px;
}
</style>

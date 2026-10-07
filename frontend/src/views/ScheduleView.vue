<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import type { Contest } from '../types'
import MyStatusButtons from '../components/MyStatusButtons.vue'
import { deadlineRelative, formatRange, todayStr } from '../utils/format'

type Stage = '进行中' | '未开始' | '已结束' | '待定'
const STAGE_TAG: Record<Stage, 'success' | 'primary' | 'info' | 'warning'> = {
  进行中: 'success',
  未开始: 'primary',
  已结束: 'info',
  待定: 'warning',
}

const router = useRouter()
const contests = ref<Contest[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const resp = await api.getContests({ my_status: 'joined', sort: 'deadline' })
    contests.value = resp.items
  } finally {
    loading.value = false
  }
}
onMounted(load)

// 阶段标记：进行中 / 未开始 / 已结束 / 待定（按本地时区当日推导）
function stageOf(c: Contest): Stage {
  const t = todayStr()
  if (c.contest_end && c.contest_end < t) return '已结束'
  if (c.contest_start && c.contest_start <= t && (!c.contest_end || t <= c.contest_end)) return '进行中'
  if (c.contest_start && c.contest_start > t) return '未开始'
  return '待定'
}

// 按月分组：优先按 contest_start，缺省按 reg_deadline，均无则归入“时间待定”
function monthKey(c: Contest): string {
  const base = c.contest_start || c.reg_deadline || ''
  return base ? base.slice(0, 7) : '待定'
}

interface Group {
  key: string
  label: string
  items: Contest[]
}
const groups = computed<Group[]>(() => {
  const map = new Map<string, Contest[]>()
  contests.value.forEach((c) => {
    const k = monthKey(c)
    const arr = map.get(k)
    if (arr) arr.push(c)
    else map.set(k, [c])
  })
  const keys = [...map.keys()].sort((a, b) => {
    if (a === '待定' && b !== '待定') return 1
    if (b === '待定' && a !== '待定') return -1
    return a.localeCompare(b)
  })
  return keys.map((k) => {
    const items = (map.get(k) as Contest[]).slice().sort((a, b) => {
      const ka = a.contest_start || a.reg_deadline || '9999'
      const kb = b.contest_start || b.reg_deadline || '9999'
      return ka.localeCompare(kb)
    })
    return {
      key: k,
      label: k === '待定' ? '时间待定' : k.slice(0, 4) + ' 年 ' + Number(k.slice(5, 7)) + ' 月',
      items,
    }
  })
})
</script>

<template>
  <div v-loading="loading" class="cr-page">
    <el-card shadow="never" class="cr-card">
      <template #header>
        <b>我的日程</b>
        <span class="cr-text-secondary" style="margin-left: 8px">共 {{ contests.length }} 场我参加的竞赛，按月分组</span>
      </template>
      <el-empty v-if="!contests.length" description="还没有标记「我要参加」的竞赛">
        <el-button type="primary" @click="router.push('/list')">去竞赛列表挑选</el-button>
      </el-empty>
      <div v-for="g in groups" :key="g.key" class="month-group">
        <div class="month-label">{{ g.label }}</div>
        <el-table :data="g.items" size="small">
          <el-table-column label="竞赛" min-width="300">
            <template #default="{ row }">
              <el-link :href="row.url" target="_blank" type="primary">{{ row.title }}</el-link>
              <div class="cr-text-secondary">{{ row.category }} · {{ row.source_name }}</div>
            </template>
          </el-table-column>
          <el-table-column label="阶段" width="96">
            <template #default="{ row }">
              <el-tag :type="STAGE_TAG[stageOf(row)]" size="small">{{ stageOf(row) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="比赛时间" width="190">
            <template #default="{ row }">{{ formatRange(row.contest_start, row.contest_end) }}</template>
          </el-table-column>
          <el-table-column label="报名截止" width="150">
            <template #default="{ row }">
              <span v-if="row.reg_deadline">{{ row.reg_deadline }}（{{ deadlineRelative(row.reg_deadline) }}）</span>
              <span v-else class="cr-text-secondary">—</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="130">
            <template #default="{ row }">
              <MyStatusButtons :contest="row" @updated="load" />
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.month-group {
  margin-bottom: 18px;
}
.month-label {
  font-weight: 700;
  font-size: 15px;
  margin-bottom: 8px;
  padding-left: 8px;
  border-left: 4px solid var(--el-color-primary);
}
</style>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import type { StatsResponse } from '../types'
import { useChart } from '../composables/useChart'
import StatusTag from '../components/StatusTag.vue'
import MyStatusButtons from '../components/MyStatusButtons.vue'
import { deadlineRelative, formatDateTime } from '../utils/format'

const router = useRouter()
const stats = ref<StatsResponse | null>(null)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    stats.value = await api.getStats()
  } finally {
    loading.value = false
  }
}
onMounted(load)

const registeringCount = computed(() => (stats.value && stats.value.by_status ? stats.value.by_status.registering ?? 0 : 0))
const joinedCount = computed(() => (stats.value ? stats.value.joined_count : 0))
const weeklyNewCount = computed(() => {
  const list = stats.value ? stats.value.weekly_new : []
  return list.length > 0 ? list[list.length - 1].count : 0
})

// ECharts：近 8 周新增柱状图
const barRef = ref<HTMLElement>()
const pieRef = ref<HTMLElement>()
const barChart = useChart(barRef, () => ({
  backgroundColor: 'transparent',
  title: { text: '近 8 周新增竞赛', left: 'center', textStyle: { fontSize: 14 } },
  tooltip: { trigger: 'axis' },
  grid: { left: 42, right: 12, top: 42, bottom: 30 },
  xAxis: {
    type: 'category',
    data: (stats.value ? stats.value.weekly_new : []).map((w) => w.week),
    axisLabel: { rotate: 32, fontSize: 11 },
  },
  yAxis: { type: 'value', minInterval: 1 },
  series: [
    {
      type: 'bar',
      name: '新增竞赛',
      data: (stats.value ? stats.value.weekly_new : []).map((w) => w.count),
      barMaxWidth: 34,
      itemStyle: { borderRadius: [4, 4, 0, 0] },
    },
  ],
}))
// ECharts：分类分布饼图
const pieChart = useChart(pieRef, () => ({
  backgroundColor: 'transparent',
  title: { text: '竞赛分类分布', left: 'center', textStyle: { fontSize: 14 } },
  tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
  legend: { bottom: 4, type: 'scroll' },
  series: [
    {
      type: 'pie',
      name: '分类',
      radius: ['36%', '64%'],
      center: ['50%', '46%'],
      data: Object.entries(stats.value ? stats.value.by_category : {}).map(([name, value]) => ({ name, value })),
      label: { formatter: '{b} {d}%' },
    },
  ],
}))
// 数据就绪后重绘（初次渲染时数据可能尚未返回）
watch(stats, () => {
  barChart.rerender()
  pieChart.rerender()
})

function onUpdated() {
  load()
}
</script>

<template>
  <div v-loading="loading" class="cr-page">
    <el-row :gutter="16">
      <el-col :span="8">
        <el-card shadow="hover" class="cr-card stat-card" @click="router.push({ path: '/list', query: { status: 'registering' } })">
          <div class="stat-label">报名中竞赛</div>
          <div class="stat-num">{{ registeringCount }}</div>
          <div class="cr-text-secondary">点击查看全部报名中的竞赛</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover" class="cr-card stat-card" @click="router.push('/schedule')">
          <div class="stat-label">我参加的</div>
          <div class="stat-num">{{ joinedCount }}</div>
          <div class="cr-text-secondary">进入我的日程</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover" class="cr-card stat-card" @click="router.push({ path: '/list', query: { sort: 'new' } })">
          <div class="stat-label">本周新增</div>
          <div class="stat-num">{{ weeklyNewCount }}</div>
          <div class="cr-text-secondary">按最新收录排序查看</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :span="14">
        <el-card shadow="never" class="cr-card">
          <div ref="barRef" class="chart-box"></div>
        </el-card>
      </el-col>
      <el-col :span="10">
        <el-card shadow="never" class="cr-card">
          <div ref="pieRef" class="chart-box"></div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="cr-card">
      <template #header><b>即将截止 Top 5</b><span class="cr-text-secondary" style="margin-left: 8px">我参加的优先</span></template>
      <el-table :data="stats ? stats.upcoming_deadlines : []" size="default">
        <el-table-column label="竞赛" min-width="320">
          <template #default="{ row }">
            <el-tag v-if="row.is_new" type="danger" size="small" effect="dark" class="new-badge">NEW</el-tag>
            <el-link :href="row.url" target="_blank" type="primary">{{ row.title }}</el-link>
            <span class="cr-text-secondary" style="margin-left: 8px">{{ row.source_name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="category" label="分类" width="130" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <StatusTag :status="row.status" />
          </template>
        </el-table-column>
        <el-table-column label="报名截止" width="180">
          <template #default="{ row }">
            <div>{{ row.reg_deadline || '—' }}</div>
            <div v-if="row.reg_deadline" class="cr-text-secondary">{{ deadlineRelative(row.reg_deadline) }}</div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="190">
          <template #default="{ row }">
            <MyStatusButtons :contest="row" @updated="onUpdated" />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="cr-card" header="信息源健康">
      <el-table :data="stats ? stats.sources : []" size="small">
        <el-table-column prop="name" label="源名称" width="150" />
        <el-table-column prop="method" label="抓取方式" width="110" />
        <el-table-column label="启用" width="70">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'" size="small">{{ row.enabled ? '启用' : '停用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="上次运行" width="160">
          <template #default="{ row }">{{ formatDateTime(row.last_run) }}</template>
        </el-table-column>
        <el-table-column label="上次成功" width="160">
          <template #default="{ row }">{{ formatDateTime(row.last_ok) }}</template>
        </el-table-column>
        <el-table-column label="异常原因" min-width="240">
          <template #default="{ row }">
            <span :class="row.last_error ? 'src-error' : 'cr-text-secondary'">{{ row.last_error || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="stats && stats.last_refresh" class="cr-text-secondary" style="margin-top: 10px">
        上次成功刷新：{{ formatDateTime(stats.last_refresh) }}
      </div>
    </el-card>
  </div>
</template>

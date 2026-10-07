<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { api } from '../api/client'
import type { Contest, ManualContestPayload, SourceInfo } from '../types'
import { useAppStore } from '../stores/app'
import { AI_POLICY_TEXT, CATEGORIES, deadlineRelative, errText, formatDateTime, formatRange } from '../utils/format'
import StatusTag from '../components/StatusTag.vue'
import MyStatusButtons from '../components/MyStatusButtons.vue'

const route = useRoute()
const appStore = useAppStore()

const STATUS_OPTIONS = [
  { value: 'registering', label: '报名中' },
  { value: 'ongoing', label: '进行中' },
  { value: 'ended', label: '已结束' },
  { value: 'unknown', label: '未知' },
]
const MY_STATUS_OPTIONS = [
  { value: '', label: '全部（默认不含已忽略）' },
  { value: 'none', label: '未标记' },
  { value: 'joined', label: '我参加的' },
  { value: 'ignored', label: '已忽略' },
]
const SORT_OPTIONS = [
  { value: 'deadline', label: '截止优先' },
  { value: 'new', label: '最新' },
  { value: 'title', label: '标题' },
]

const filters = reactive({
  category: '',
  status: '',
  source_id: '',
  my_status: '',
  q: '',
  sort: 'deadline' as string,
})

// 支持从仪表盘带参跳转（?status=registering / ?sort=new / ?category=… / ?q=…）
const q0 = route.query
if (typeof q0.status === 'string' && STATUS_OPTIONS.some((o) => o.value === q0.status)) filters.status = q0.status
if (typeof q0.category === 'string' && (CATEGORIES as readonly string[]).indexOf(q0.category) >= 0) filters.category = q0.category
if (typeof q0.my_status === 'string' && ['none', 'joined', 'ignored'].indexOf(q0.my_status) >= 0) filters.my_status = q0.my_status
if (typeof q0.q === 'string') filters.q = q0.q
if (typeof q0.sort === 'string' && ['deadline', 'new', 'title'].indexOf(q0.sort) >= 0) filters.sort = q0.sort

const items = ref<Contest[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = 20
const sources = ref<SourceInfo[]>([])

const queryParams = computed(() => {
  const p: Record<string, string> = { sort: filters.sort }
  if (filters.category) p.category = filters.category
  if (filters.status) p.status = filters.status
  if (filters.source_id) p.source_id = filters.source_id
  if (filters.my_status) {
    p.my_status = filters.my_status
    if (filters.my_status === 'ignored') p.hidden = '1'
  }
  const kw = filters.q.trim()
  if (kw) p.q = kw
  return p
})

async function load() {
  loading.value = true
  try {
    const resp = await api.getContests(queryParams.value)
    items.value = resp.items
    total.value = resp.total
  } finally {
    loading.value = false
  }
}

// 筛选/排序变化防抖 300ms 后重新查询（首次立即加载）
let debounceTimer: number | undefined
watch(
  queryParams,
  () => {
    if (debounceTimer !== undefined) window.clearTimeout(debounceTimer)
    debounceTimer = window.setTimeout(() => {
      page.value = 1
      load()
    }, 300)
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  if (debounceTimer !== undefined) window.clearTimeout(debounceTimer)
})

onMounted(() => {
  appStore
    .loadRefreshStatus()
    .then()
    .catch(() => undefined)
  api
    .getSources()
    .then((list) => {
      sources.value = list
    })
    .catch(() => undefined)
})

const pagedItems = computed(() => {
  const start = (page.value - 1) * pageSize
  return items.value.slice(start, start + pageSize)
})

// ---------- 立即刷新（POST /api/refresh + 轮询 /api/refresh/status） ----------
const refreshing = computed(() => appStore.refreshing)
async function refreshNow() {
  try {
    await appStore.startRefresh(() => {
      ElMessage.success('抓取完成，列表已更新')
      load()
    })
  } catch (e) {
    ElMessage.error(errText(e))
  }
}

// ---------- 手动补录（POST /api/contests/manual） ----------
const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref<FormInstance>()
const manualForm = reactive({
  title: '',
  url: '',
  category: '',
  reg_start: null as string | number | Date | null,
  reg_deadline: null as string | number | Date | null,
  contest_start: null as string | number | Date | null,
  contest_end: null as string | number | Date | null,
  organizer: '',
  tags: '',
  summary: '',
})
const manualRules: FormRules = {
  title: [{ required: true, message: '请输入竞赛名称', trigger: 'blur' }],
  url: [
    { required: true, message: '请输入详情页 URL', trigger: 'blur' },
    { pattern: /^https?:\/\//, message: 'URL 需以 http:// 或 https:// 开头', trigger: 'blur' },
  ],
  category: [{ required: true, message: '请选择分类', trigger: 'change' }],
}

function openDialog() {
  dialogVisible.value = true
}
function resetManual() {
  manualForm.title = ''
  manualForm.url = ''
  manualForm.category = ''
  manualForm.reg_start = null
  manualForm.reg_deadline = null
  manualForm.contest_start = null
  manualForm.contest_end = null
  manualForm.organizer = ''
  manualForm.tags = ''
  manualForm.summary = ''
  formRef.value?.clearValidate()
}
function normDate(v: string | number | Date | null): string | null {
  if (v === null || v === '') return null
  if (typeof v === 'string') return v
  if (typeof v === 'number') {
    const d = new Date(v)
    const p = (n: number) => (n < 10 ? '0' + n : String(n))
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate())
  }
  const p = (n: number) => (n < 10 ? '0' + n : String(n))
  return v.getFullYear() + '-' + p(v.getMonth() + 1) + '-' + p(v.getDate())
}

async function submitManual() {
  if (!formRef.value) return
  const valid = await formRef.value
    .validate()
    .then(() => true)
    .catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    const payload: ManualContestPayload = {
      title: manualForm.title.trim(),
      url: manualForm.url.trim(),
      category: manualForm.category as ManualContestPayload['category'],
      reg_start: normDate(manualForm.reg_start),
      reg_deadline: normDate(manualForm.reg_deadline),
      contest_start: normDate(manualForm.contest_start),
      contest_end: normDate(manualForm.contest_end),
      organizer: manualForm.organizer.trim() || null,
      tags: manualForm.tags.trim() ? manualForm.tags.split(/[,，;；\s]+/).filter(Boolean) : [],
      summary: manualForm.summary.trim() || null,
    }
    await api.addManualContest(payload)
    ElMessage.success('已补录：' + payload.title)
    dialogVisible.value = false
    resetManual()
    load()
  } catch (e) {
    ElMessage.error(errText(e))
  } finally {
    submitting.value = false
  }
}

function onRowUpdated() {
  load()
}
</script>

<template>
  <div class="cr-page">
    <el-card shadow="never" class="cr-card">
      <div class="cr-toolbar" style="margin-bottom: 10px">
        <el-select v-model="filters.category" placeholder="全部分类" clearable style="width: 150px">
          <el-option v-for="c in CATEGORIES" :key="c" :label="c" :value="c" />
        </el-select>
        <el-select v-model="filters.status" placeholder="全部状态" clearable style="width: 130px">
          <el-option v-for="o in STATUS_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
        <el-select v-model="filters.source_id" placeholder="全部来源" clearable style="width: 150px">
          <el-option v-for="s in sources" :key="s.id" :label="s.name" :value="s.id" />
        </el-select>
        <el-select v-model="filters.my_status" style="width: 185px">
          <el-option v-for="o in MY_STATUS_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
        <el-input v-model="filters.q" placeholder="搜索竞赛名称关键词" clearable style="width: 210px" />
        <div class="grow"></div>
        <el-button type="primary" :loading="refreshing" @click="refreshNow">{{ refreshing ? '抓取中…' : '立即刷新' }}</el-button>
        <el-button @click="openDialog">手动补录</el-button>
      </div>
      <div class="cr-toolbar" style="margin-bottom: 0">
        <span class="cr-text-secondary">排序：</span>
        <el-radio-group v-model="filters.sort">
          <el-radio-button v-for="o in SORT_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</el-radio-button>
        </el-radio-group>
        <div class="grow"></div>
        <span v-if="appStore.refreshStatus" class="cr-text-secondary">
          上次刷新：{{ formatDateTime(appStore.refreshStatus.last_run) }}
        </span>
      </div>
    </el-card>

    <el-card shadow="never" class="cr-card">
      <el-table v-loading="loading" :data="pagedItems" size="default" row-key="id">
        <el-table-column label="竞赛" min-width="320">
          <template #default="{ row }">
            <div class="list-title">
              <el-tag v-if="row.is_new" type="danger" size="small" effect="dark" class="new-badge">NEW</el-tag>
              <el-link :href="row.url" target="_blank" type="primary">{{ row.title }}</el-link>
            </div>
            <div class="cr-text-secondary list-sub">
              <span>{{ row.source_name }}</span>
              <span v-if="row.organizer"> · {{ row.organizer }}</span>
              <span> · {{ AI_POLICY_TEXT[row.ai_policy] || 'AI政策未知' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="category" label="分类" width="125" />
        <el-table-column label="状态" width="92">
          <template #default="{ row }">
            <StatusTag :status="row.status" />
          </template>
        </el-table-column>
        <el-table-column label="报名截止" width="150">
          <template #default="{ row }">
            <div>{{ row.reg_deadline || '—' }}</div>
            <div v-if="row.reg_deadline" class="cr-text-secondary">{{ deadlineRelative(row.reg_deadline) }}</div>
          </template>
        </el-table-column>
        <el-table-column label="比赛时间" width="190">
          <template #default="{ row }">{{ formatRange(row.contest_start, row.contest_end) }}</template>
        </el-table-column>
        <el-table-column label="我的状态" width="96">
          <template #default="{ row }">
            <el-tag v-if="row.my_status === 'joined'" type="success" size="small">我参加</el-tag>
            <el-tag v-else-if="row.my_status === 'ignored'" type="info" size="small">已忽略</el-tag>
            <span v-else class="cr-text-secondary">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="190" fixed="right">
          <template #default="{ row }">
            <MyStatusButtons :contest="row" @updated="onRowUpdated" />
          </template>
        </el-table-column>
      </el-table>
      <div class="pager-row">
        <el-pagination v-model:current-page="page" :page-size="pageSize" :total="total" layout="total, prev, pager, next" background />
      </div>
    </el-card>

    <el-dialog v-model="dialogVisible" title="手动补录竞赛" width="560px" @closed="resetManual">
      <el-form ref="formRef" :model="manualForm" :rules="manualRules" label-width="92px">
        <el-form-item label="名称" prop="title">
          <el-input v-model="manualForm.title" placeholder="竞赛全名" />
        </el-form-item>
        <el-form-item label="URL" prop="url">
          <el-input v-model="manualForm.url" placeholder="https://…" />
        </el-form-item>
        <el-form-item label="分类" prop="category">
          <el-select v-model="manualForm.category" placeholder="选择分类" style="width: 100%">
            <el-option v-for="c in CATEGORIES" :key="c" :label="c" :value="c" />
          </el-select>
        </el-form-item>
        <el-form-item label="报名起止">
          <el-col :span="11">
            <el-date-picker v-model="manualForm.reg_start" type="date" value-format="YYYY-MM-DD" placeholder="开始" style="width: 100%" />
          </el-col>
          <el-col :span="2" class="center-dot">~</el-col>
          <el-col :span="11">
            <el-date-picker v-model="manualForm.reg_deadline" type="date" value-format="YYYY-MM-DD" placeholder="截止" style="width: 100%" />
          </el-col>
        </el-form-item>
        <el-form-item label="比赛时间">
          <el-col :span="11">
            <el-date-picker v-model="manualForm.contest_start" type="date" value-format="YYYY-MM-DD" placeholder="开始" style="width: 100%" />
          </el-col>
          <el-col :span="2" class="center-dot">~</el-col>
          <el-col :span="11">
            <el-date-picker v-model="manualForm.contest_end" type="date" value-format="YYYY-MM-DD" placeholder="结束" style="width: 100%" />
          </el-col>
        </el-form-item>
        <el-form-item label="主办方">
          <el-input v-model="manualForm.organizer" placeholder="选填" />
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="manualForm.tags" placeholder="选填，逗号分隔，如：个人赛,国家级" />
        </el-form-item>
        <el-form-item label="简介">
          <el-input v-model="manualForm.summary" type="textarea" :rows="2" placeholder="选填" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitManual">提交补录</el-button>
      </template>
    </el-dialog>
  </div>
</template>

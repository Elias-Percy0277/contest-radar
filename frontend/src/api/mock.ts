// 本地 Mock 数据与伪 API：返回结构逐字段与 SPEC §4 一致。
// 用途：VITE_USE_MOCK=1 强制启用，或后端不可用时由 client.ts 自动降级（SPEC §7）。
// 日期全部相对“今天”动态生成，保证任何时间打开演示，状态推导都成立。
import type {
  AiPolicy,
  Category,
  Contest,
  ContestQuery,
  ContestStatus,
  ContestsResponse,
  ManualContestPayload,
  MyStatus,
  RefreshStatus,
  SourceInfo,
  StatsResponse,
} from '../types'

const DAY_MS = 86400000
const HOUR_MS = 3600000

function pad(n: number): string {
  return n < 10 ? '0' + n : String(n)
}
function fmtDate(d: Date): string {
  return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate())
}
function todayStart(): Date {
  const d = new Date()
  d.setHours(0, 0, 0, 0)
  return d
}
/** 相对今天偏移 n 天的日期串 */
function dateStr(offsetDays: number): string {
  return fmtDate(new Date(todayStart().getTime() + offsetDays * DAY_MS))
}
function todayStr(): string {
  return fmtDate(todayStart())
}
/** n 小时前的 ISO8601 时间戳 */
function isoAgo(hours: number): string {
  return new Date(Date.now() - hours * HOUR_MS).toISOString()
}

/** SPEC §3 状态推导（与后端同规则，按本地时区，优先级从上到下） */
export function deriveStatus(c: {
  reg_start?: string | null
  reg_deadline?: string | null
  contest_start?: string | null
  contest_end?: string | null
}): ContestStatus {
  const t = todayStr()
  if (c.contest_end && c.contest_end < t) return 'ended'
  if (c.contest_start && c.contest_start <= t && (!c.contest_end || t <= c.contest_end)) return 'ongoing'
  if (c.contest_start && c.contest_start <= t && !c.contest_end) return 'ongoing'
  if (
    c.reg_deadline &&
    c.reg_deadline >= t &&
    (!c.reg_start || c.reg_start <= t) &&
    (!c.contest_start || c.contest_start > t)
  ) {
    return 'registering'
  }
  return 'unknown'
}

/** SPEC §3 canonical_url 规范化：scheme/host 小写、去 fragment、去尾部斜杠、去 utm_ 系与 from/spm 参数、其余参数按 key 排序 */
export function normalizeUrl(raw: string): string {
  try {
    const u = new URL(raw)
    u.hash = ''
    const drop = ['from', 'spm']
    const kept: Array<[string, string]> = []
    u.searchParams.forEach((value, key) => {
      const k = key.toLowerCase()
      if (k.startsWith('utm_') || drop.indexOf(k) >= 0) return
      kept.push([key, value])
    })
    kept.sort((a, b) => (a[0] === b[0] ? (a[1] < b[1] ? -1 : 1) : a[0] < b[0] ? -1 : 1))
    u.search = ''
    kept.forEach((pair) => u.searchParams.append(pair[0], pair[1]))
    let s = u.toString()
    if (u.pathname !== '/' && s.endsWith('/')) s = s.slice(0, -1)
    return s
  } catch {
    return raw
  }
}

const SOURCE_NAMES: Record<string, string> = {
  ccf_csp: 'CCF CSP认证',
  huawei: '华为云大赛',
  nowcoder: '牛客竞赛',
  codeforces: 'Codeforces',
  manual: '手动补录',
}

interface RawSeed {
  id: number
  title: string
  url: string
  category: Category
  source_id: string
  reg_start?: string | null
  reg_deadline?: string | null
  contest_start?: string | null
  contest_end?: string | null
  organizer?: string | null
  tags?: string[]
  ai_policy?: AiPolicy
  prize?: string | null
  eligibility?: string | null
  requirements?: string | null
  summary?: string | null
  summary_by?: 'llm' | 'rule'
  my_status?: MyStatus
  /** 首次收录距现在的小时数（<48 为 NEW） */
  first_seen_hours_ago: number
  updated_hours_ago?: number
}

// 14 条种子数据：覆盖 6 大分类、4 种状态、NEW、joined/ignored、无日期、不同截止跨度
const SEEDS: RawSeed[] = [
  {
    id: 1,
    title: 'CCF CSP认证 第35次考试',
    url: 'https://www.cspro.org/jump/csp35?utm_source=radar',
    category: '认证考试',
    source_id: 'ccf_csp',
    reg_start: dateStr(-30),
    reg_deadline: dateStr(10),
    contest_start: dateStr(32),
    contest_end: dateStr(32),
    organizer: '中国计算机学会',
    tags: ['认证', '线下考试'],
    ai_policy: 'forbidden',
    eligibility: '不限',
    summary: 'CSP认证重点考察算法设计与编程实现能力，成绩可服务于高校招生与企业招聘。',
    summary_by: 'llm',
    my_status: 'joined',
    first_seen_hours_ago: 120,
  },
  {
    id: 2,
    title: 'Codeforces Round 1005 (Div. 2)',
    url: 'https://codeforces.com/contests/1005',
    category: '算法竞赛',
    source_id: 'codeforces',
    reg_deadline: dateStr(0),
    contest_start: dateStr(0),
    contest_end: dateStr(0),
    organizer: 'Codeforces',
    tags: ['个人赛', '国际级'],
    ai_policy: 'forbidden',
    summary: '2.5 小时线上算法赛，3 题起步，适合 Div.2 选手。',
    my_status: 'none',
    first_seen_hours_ago: 6,
  },
  {
    id: 3,
    title: '牛客 2026 寒假算法集训营（第 1 场）',
    url: 'https://ac.nowcoder.com/acm/contest/90001',
    category: '算法竞赛',
    source_id: 'nowcoder',
    reg_start: dateStr(-2),
    reg_deadline: dateStr(18),
    contest_start: dateStr(20),
    contest_end: dateStr(20),
    organizer: '牛客网',
    tags: ['个人赛', '限在校生'],
    ai_policy: 'forbidden',
    my_status: 'none',
    first_seen_hours_ago: 10,
  },
  {
    id: 4,
    title: '华为云开发者 AI 创新大赛 2026',
    url: 'https://competition.huaweicloud.com/ai2026?from=banner',
    category: 'AI与数据科学',
    source_id: 'huawei',
    reg_start: dateStr(-20),
    reg_deadline: dateStr(5),
    contest_start: dateStr(12),
    contest_end: dateStr(45),
    organizer: '华为云',
    tags: ['企业级', '团队赛'],
    ai_policy: 'allowed',
    prize: '50 万元奖金池',
    eligibility: '高校学生与社会开发者均可组队（1-3 人）',
    summary: '围绕 ModelArts 平台完成大模型应用创新，分初赛/复赛/总决赛三个阶段。',
    summary_by: 'llm',
    my_status: 'joined',
    first_seen_hours_ago: 20,
  },
  {
    id: 5,
    title: '2026 全国大学生信息安全竞赛',
    url: 'https://www.ciscn.cn/detail/2026.html',
    category: '网络安全',
    source_id: 'nowcoder',
    reg_start: dateStr(-40),
    reg_deadline: dateStr(-10),
    contest_start: dateStr(-3),
    contest_end: dateStr(4),
    organizer: '高校网络空间安全类专业教学指导委员会',
    tags: ['团队赛', '国家级'],
    ai_policy: 'unknown',
    my_status: 'none',
    first_seen_hours_ago: 720,
  },
  {
    id: 6,
    title: '全国大学生数学建模竞赛 2026',
    url: 'https://www.mcm.edu.cn/html_cn/node/2026.html',
    category: '综合学科',
    source_id: 'nowcoder',
    reg_deadline: dateStr(-30),
    contest_start: dateStr(-2),
    contest_end: dateStr(2),
    organizer: '中国工业与应用数学学会',
    tags: ['团队赛', '国家级'],
    ai_policy: 'allowed',
    my_status: 'joined',
    first_seen_hours_ago: 400,
  },
  {
    id: 7,
    title: '第 19 届中国大学生计算机设计大赛',
    url: 'https://jsjds.blcu.edu.cn/',
    category: '应用与开发',
    source_id: 'nowcoder',
    reg_start: dateStr(-90),
    reg_deadline: dateStr(-60),
    contest_start: dateStr(-60),
    contest_end: dateStr(-25),
    organizer: '教育部高校计算机类教学指导委员会',
    tags: ['团队赛', '国家级'],
    ai_policy: 'allowed',
    my_status: 'none',
    first_seen_hours_ago: 2200,
  },
  {
    id: 8,
    title: '华为云 CodeArts 代码上云实战赛',
    url: 'https://competition.huaweicloud.com/codearts2026/#/home',
    category: '应用与开发',
    source_id: 'huawei',
    reg_start: dateStr(-15),
    reg_deadline: dateStr(0),
    contest_start: dateStr(15),
    contest_end: dateStr(30),
    organizer: '华为云',
    tags: ['企业级', '个人赛'],
    ai_policy: 'allowed',
    prize: '10 万元奖金池',
    my_status: 'none',
    first_seen_hours_ago: 30,
  },
  {
    id: 9,
    title: 'DataFountain 大数据算法挑战赛（春季赛）',
    url: 'https://www.datafountain.cn/competitions/6012',
    category: 'AI与数据科学',
    source_id: 'nowcoder',
    reg_deadline: dateStr(-45),
    contest_start: dateStr(-40),
    contest_end: dateStr(-5),
    organizer: 'DataFountain',
    tags: ['团队赛'],
    ai_policy: 'allowed',
    my_status: 'none',
    first_seen_hours_ago: 1000,
  },
  {
    id: 10,
    title: '某高校程序设计新生赛（时间待定）',
    url: 'https://ac.nowcoder.com/acm/contest/90012',
    category: '算法竞赛',
    source_id: 'nowcoder',
    organizer: '高校计算机协会',
    tags: ['个人赛', '限在校生'],
    ai_policy: 'unknown',
    my_status: 'none',
    first_seen_hours_ago: 60,
  },
  {
    id: 11,
    title: '软考：系统集成项目管理工程师（下半年）',
    url: 'https://www.ruankao.org.cn/notification/2026b',
    category: '认证考试',
    source_id: 'ccf_csp',
    reg_deadline: dateStr(3),
    contest_start: dateStr(46),
    contest_end: dateStr(46),
    organizer: '工业和信息化部教育与考试中心',
    tags: ['认证'],
    ai_policy: 'forbidden',
    eligibility: '不限学历，社会人员可报考',
    my_status: 'none',
    first_seen_hours_ago: 200,
  },
  {
    id: 12,
    title: '2026 全国大学生英语竞赛（NECCS）',
    url: 'https://www.chinaneccs.cn/signup?spm=1001.2014',
    category: '综合学科',
    source_id: 'nowcoder',
    reg_deadline: dateStr(8),
    contest_start: dateStr(30),
    contest_end: dateStr(31),
    organizer: '高等学校大学外语教学指导委员会',
    tags: ['个人赛', '限在校生'],
    ai_policy: 'forbidden',
    my_status: 'ignored',
    first_seen_hours_ago: 300,
  },
  {
    id: 13,
    title: '华为云大模型应用创新大赛（华东赛区）',
    url: 'https://competition.huaweicloud.com/llm2026',
    category: 'AI与数据科学',
    source_id: 'huawei',
    reg_deadline: dateStr(2),
    contest_start: dateStr(20),
    contest_end: dateStr(21),
    organizer: '华为云',
    tags: ['企业级'],
    ai_policy: 'allowed',
    my_status: 'ignored',
    first_seen_hours_ago: 300,
  },
  {
    id: 14,
    title: '强网杯全国网络安全挑战赛 2026',
    url: 'https://qwb2026.qiangwangbei.com/',
    category: '网络安全',
    source_id: 'nowcoder',
    reg_deadline: dateStr(47),
    contest_start: dateStr(55),
    contest_end: dateStr(56),
    organizer: '信息网络安全领域联席会议',
    tags: ['团队赛', '高难度'],
    ai_policy: 'allowed',
    my_status: 'none',
    first_seen_hours_ago: 500,
  },
]

function buildContests(): Contest[] {
  return SEEDS.map((s) => {
    const base = {
      reg_start: s.reg_start ?? null,
      reg_deadline: s.reg_deadline ?? null,
      contest_start: s.contest_start ?? null,
      contest_end: s.contest_end ?? null,
    }
    const contest: Contest = {
      id: s.id,
      title: s.title,
      url: s.url,
      canonical_url: normalizeUrl(s.url),
      category: s.category,
      ...base,
      organizer: s.organizer ?? null,
      tags: s.tags ?? [],
      ai_policy: s.ai_policy ?? 'unknown',
      prize: s.prize ?? null,
      eligibility: s.eligibility ?? null,
      requirements: s.requirements ?? null,
      summary: s.summary ?? null,
      summary_by: s.summary_by ?? 'rule',
      source_id: s.source_id,
      source_name: SOURCE_NAMES[s.source_id] ?? s.source_id,
      status: deriveStatus(base),
      my_status: s.my_status ?? 'none',
      first_seen: isoAgo(s.first_seen_hours_ago),
      last_updated: isoAgo(s.updated_hours_ago ?? s.first_seen_hours_ago),
      is_new: s.first_seen_hours_ago < 48,
    }
    return contest
  })
}

// ---------------- Mock 服务器状态 ----------------

let contests: Contest[] = buildContests()
let nextId = 100
const sources: SourceInfo[] = [
  { id: 'ccf_csp', name: 'CCF CSP认证', method: 'http', enabled: true, last_run: isoAgo(0.6), last_ok: isoAgo(0.6), last_error: null },
  {
    id: 'huawei',
    name: '华为云大赛',
    method: 'playwright',
    enabled: true,
    last_run: isoAgo(0.6),
    last_ok: isoAgo(5.1),
    last_error: 'Playwright 内核未安装：请先运行 playwright install chromium',
  },
  { id: 'nowcoder', name: '牛客竞赛', method: 'http', enabled: true, last_run: isoAgo(0.6), last_ok: isoAgo(0.6), last_error: null },
  { id: 'codeforces', name: 'Codeforces', method: 'api', enabled: true, last_run: isoAgo(0.6), last_ok: isoAgo(0.6), last_error: null },
]
const refresh: RefreshStatus = { running: false, last_run: isoAgo(0.7), last_ok: isoAgo(0.7), cache_hours: 6 }
let refreshTimer: ReturnType<typeof setTimeout> | null = null

function copy<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T
}

/** ISO-8601 周标签，如 2026-W40 */
function isoWeekLabel(d: Date): string {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))
  const day = date.getUTCDay() || 7
  date.setUTCDate(date.getUTCDate() + 4 - day) // 对齐到本周四
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1))
  const week = Math.ceil(((date.getTime() - yearStart.getTime()) / DAY_MS + 1) / 7)
  return date.getUTCFullYear() + '-W' + pad(week)
}

function weeklyNewSeries(): Array<{ week: string; count: number }> {
  const counts = [3, 5, 2, 6, 4, 7, 3, 5]
  const out: Array<{ week: string; count: number }> = []
  for (let i = 7; i >= 0; i--) {
    const d = new Date(todayStart().getTime() - i * 7 * DAY_MS)
    out.push({ week: isoWeekLabel(d), count: counts[7 - i] })
  }
  return out
}

function queryContests(q: ContestQuery): ContestsResponse {
  let items = contests.slice()
  if (q.hidden !== '1') items = items.filter((c) => c.my_status !== 'ignored')
  const category = q.category ?? ''
  const status = q.status ?? ''
  const myStatus = q.my_status ?? ''
  const sourceId = q.source_id ?? ''
  const aiPolicy = q.ai_policy ?? ''
  const kw = (q.q ?? '').trim().toLowerCase()
  if (category) items = items.filter((c) => c.category === category)
  if (aiPolicy) items = items.filter((c) => c.ai_policy === aiPolicy)
  if (status) items = items.filter((c) => c.status === status)
  if (myStatus) items = items.filter((c) => c.my_status === myStatus)
  if (sourceId) items = items.filter((c) => c.source_id === sourceId)
  if (kw) items = items.filter((c) => c.title.toLowerCase().indexOf(kw) >= 0)
  const sort = q.sort || 'deadline'
  if (sort === 'deadline') {
    // 截止优先：无截止的排最后（SPEC §4）
    items.sort((a, b) => {
      if (a.reg_deadline && b.reg_deadline) return a.reg_deadline < b.reg_deadline ? -1 : 1
      if (a.reg_deadline) return -1
      if (b.reg_deadline) return 1
      return 0
    })
  } else if (sort === 'new') {
    items.sort((a, b) => (a.first_seen < b.first_seen ? 1 : -1))
  } else if (sort === 'title') {
    items.sort((a, b) => a.title.localeCompare(b.title, 'zh'))
  }
  const totalAll = items.length
  const pageSize = q.page_size ?? 0
  const pageNo = Math.max(1, q.page ?? 1)
  if (pageSize > 0) items = items.slice((pageNo - 1) * pageSize, pageNo * pageSize)
  return {
    items: items.map((c) => copy(c)),
    total: totalAll,
    page: pageNo,
    page_size: pageSize || totalAll,
  }
}

function buildStats(): StatsResponse {
  const byCategory: Record<string, number> = {}
  const byStatus: Record<string, number> = {}
  contests.forEach((c) => {
    byCategory[c.category] = (byCategory[c.category] ?? 0) + 1
    byStatus[c.status] = (byStatus[c.status] ?? 0) + 1
  })
  const t = todayStr()
  const upcoming = contests
    .filter((c): c is Contest & { reg_deadline: string } => typeof c.reg_deadline === 'string' && c.reg_deadline >= t && c.my_status !== 'ignored')
    .sort((a, b) => {
      const ja = a.my_status === 'joined' ? 0 : 1
      const jb = b.my_status === 'joined' ? 0 : 1
      if (ja !== jb) return ja - jb
      return a.reg_deadline < b.reg_deadline ? -1 : 1
    })
    .slice(0, 5)
  return {
    by_category: byCategory,
    by_status: byStatus,
    weekly_new: weeklyNewSeries(),
    upcoming_deadlines: upcoming.map((c) => copy(c)),
    joined_count: contests.filter((c) => c.my_status === 'joined').length,
    last_refresh: refresh.last_ok,
    sources: sources.map((s) => copy(s)),
  }
}

function strOrNull(v: unknown): string | null {
  return typeof v === 'string' && v ? v : null
}

function startMockRefresh(): { started: boolean } {
  refresh.running = true
  refresh.last_run = new Date().toISOString()
  if (refreshTimer) clearTimeout(refreshTimer)
  // 约 4 秒后结束 running，并把一条未标记竞赛标记为 NEW，便于演示刷新效果
  refreshTimer = setTimeout(() => {
    refresh.running = false
    refresh.last_ok = new Date().toISOString()
    const target = contests.find((c) => !c.is_new && c.my_status === 'none')
    if (target) {
      target.is_new = true
      target.first_seen = new Date().toISOString()
    }
  }, 4000)
  return { started: true }
}

/** Mock 请求入口：按 method + path 分发，与 SPEC §4 端点一一对应 */
async function request<T>(method: string, pathWithQuery: string, body?: unknown): Promise<T> {
  await new Promise((r) => setTimeout(r, 120 + Math.random() * 180))
  const m = method.toUpperCase()
  const idx = pathWithQuery.indexOf('?')
  const path = idx >= 0 ? pathWithQuery.slice(0, idx) : pathWithQuery
  const qs = idx >= 0 ? pathWithQuery.slice(idx + 1) : ''
  const query = Object.fromEntries(new URLSearchParams(qs).entries())

  if (m === 'GET' && path === '/contests') return queryContests(query) as T

  const ms = path.match(/^\/contests\/(\d+)\/my_status$/)
  if (m === 'POST' && ms) {
    const b = Object.assign({}, body) as { value?: unknown }
    const value = String(b.value ?? '')
    if (['joined', 'ignored', 'none'].indexOf(value) < 0) {
      throw new Error('my_status 取值必须是 joined / ignored / none')
    }
    const contest = contests.find((c) => c.id === Number(ms[1]))
    if (!contest) throw new Error('竞赛不存在：id=' + ms[1])
    contest.my_status = value as MyStatus
    contest.last_updated = new Date().toISOString()
    return copy(contest) as T
  }

  const dd = path.match(/^\/contests\/(\d+)\/deepdive$/)
  if (m === 'POST' && dd) {
    const contest = contests.find((c) => c.id === Number(dd[1]))
    if (!contest) throw new Error('竞赛不存在：id=' + dd[1])
    contest.ai_policy = 'allowed'
    if (contest.tags.indexOf('已深挖') < 0) contest.tags = contest.tags.concat(['已深挖'])
    contest.last_updated = new Date().toISOString()
    return copy(Object.assign({}, contest, { deepdive_changed: ['ai_policy'] })) as T
  }

  if (m === 'POST' && path === '/contests/manual') {
    const b = Object.assign({}, body) as Partial<ManualContestPayload>
    const title = (b.title ?? '').trim()
    const url = (b.url ?? '').trim()
    const category = (b.category ?? '').trim()
    if (!title || !url || !category) throw new Error('补录失败：title / url / category 必填')
    const base = {
      reg_start: strOrNull(b.reg_start),
      reg_deadline: strOrNull(b.reg_deadline),
      contest_start: strOrNull(b.contest_start),
      contest_end: strOrNull(b.contest_end),
    }
    const contest: Contest = {
      id: nextId++,
      title,
      url,
      canonical_url: normalizeUrl(url),
      category: category as Category,
      ...base,
      organizer: strOrNull(b.organizer),
      tags: Array.isArray(b.tags) ? b.tags.map(String) : [],
      ai_policy: 'unknown',
      prize: strOrNull(b.prize),
      eligibility: strOrNull(b.eligibility),
      requirements: strOrNull(b.requirements),
      summary: strOrNull(b.summary),
      summary_by: 'rule',
      source_id: 'manual',
      source_name: SOURCE_NAMES.manual,
      status: deriveStatus(base),
      my_status: 'none',
      first_seen: new Date().toISOString(),
      last_updated: new Date().toISOString(),
      is_new: true,
    }
    contests.push(contest)
    return copy(contest) as T
  }

  if (m === 'POST' && path === '/refresh') return startMockRefresh() as T
  if (m === 'GET' && path === '/refresh/status') return copy(refresh) as T
  if (m === 'GET' && path === '/sources') return sources.map((s) => copy(s)) as T
  if (m === 'GET' && path === '/weekly-report') {
    const t = todayStr()
    const soon = contests.filter((c) => typeof c.reg_deadline === 'string' && c.reg_deadline >= t).slice(0, 5)
    const lines = [
      '（Mock 演示周报）本周重点：',
      ...contests.slice(0, 3).map((c) => '- ' + c.title),
      '',
      '即将截止：',
      ...(soon.length ? soon.map((c) => '- ' + c.title + '（' + c.reg_deadline + ' 截止）') : ['暂无']),
    ]
    return copy({
      text: lines.join(String.fromCharCode(10)),
      generated_at: new Date().toISOString(),
      new_count: 3,
      deadline_count: soon.length,
    }) as T
  }
  if (m === 'GET' && path === '/stats') return buildStats() as T

  throw new Error('Mock 未实现接口：' + m + ' ' + path)
}

export const mockApi = { request }

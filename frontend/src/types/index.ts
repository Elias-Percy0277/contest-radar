// 数据类型定义：字段与 SPEC §3 / §4 完全一致（前后端唯一权威契约）
export type Category =
  | '算法竞赛'
  | 'AI与数据科学'
  | '应用与开发'
  | '网络安全'
  | '综合学科'
  | '认证考试'

export type ContestStatus = 'registering' | 'ongoing' | 'ended' | 'unknown'
export type MyStatus = 'none' | 'joined' | 'ignored'
export type AiPolicy = 'allowed' | 'forbidden' | 'unknown'

/** Contest = ContestRaw + 框架补齐字段（SPEC §3） */
export interface Contest {
  id: number
  title: string
  url: string
  canonical_url: string
  category: Category
  reg_start: string | null
  reg_deadline: string | null
  contest_start: string | null
  contest_end: string | null
  organizer: string | null
  tags: string[]
  ai_policy: AiPolicy
  prize: string | null
  eligibility: string | null
  requirements: string | null
  summary: string | null
  summary_by: 'llm' | 'rule'
  source_id: string
  source_name: string
  status: ContestStatus
  my_status: MyStatus
  first_seen: string
  last_updated: string
  is_new: boolean
}

export interface ContestsResponse {
  items: Contest[]
  total: number
}

export interface SourceInfo {
  id: string
  name: string
  method: string
  enabled: boolean
  last_run: string | null
  last_ok: string | null
  last_error: string | null
}

export interface RefreshStatus {
  running: boolean
  last_run: string | null
  last_ok: string | null
  cache_hours: number
}

export interface WeeklyNewPoint {
  week: string
  count: number
}

export interface StatsResponse {
  by_category: Record<string, number>
  by_status: Record<string, number>
  weekly_new: WeeklyNewPoint[]
  upcoming_deadlines: Contest[]
  joined_count: number
  last_refresh: string | null
  sources: SourceInfo[]
}

export interface ContestQuery {
  category?: string
  status?: string
  my_status?: string
  q?: string
  source_id?: string
  hidden?: string
  sort?: string
}

/** 手动补录请求体：ContestRaw 子集（title/url/category 必填，SPEC §4） */
export interface ManualContestPayload {
  title: string
  url: string
  category: Category
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
}

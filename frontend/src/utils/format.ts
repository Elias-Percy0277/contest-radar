// 展示格式与状态文案工具（全中文）
import type { ContestStatus, MyStatus } from '../types'

export const CATEGORIES = ['算法竞赛', 'AI与数据科学', '应用与开发', '网络安全', '综合学科', '认证考试'] as const

export const STATUS_TEXT: Record<ContestStatus, string> = {
  registering: '报名中',
  ongoing: '进行中',
  ended: '已结束',
  unknown: '未知',
}

// SPEC §7：报名中=primary、进行中=success、已结束=info、未知=warning
export const STATUS_TAG_TYPE: Record<ContestStatus, 'primary' | 'success' | 'info' | 'warning'> = {
  registering: 'primary',
  ongoing: 'success',
  ended: 'info',
  unknown: 'warning',
}

export const MY_STATUS_TEXT: Record<MyStatus, string> = {
  none: '未标记',
  joined: '我参加',
  ignored: '已忽略',
}

export const AI_POLICY_TEXT: Record<string, string> = {
  allowed: '允许AI',
  forbidden: '禁用AI',
  unknown: 'AI政策未知',
}

function pad(n: number): string {
  return n < 10 ? '0' + n : String(n)
}

export function todayStr(): string {
  const d = new Date()
  return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate())
}

/** 距今天数：目标日在未来为正数，已过去为负数 */
export function daysUntil(dateStr: string): number {
  const target = new Date(dateStr + 'T00:00:00')
  const t = new Date()
  t.setHours(0, 0, 0, 0)
  return Math.round((target.getTime() - t.getTime()) / 86400000)
}

/** 截止时刻：日期只有 YYYY-MM-DD，按当日 23:59:59（本地时区）计（假设见 README） */
export function deadlineMoment(dateStr: string): Date {
  return new Date(dateStr + 'T23:59:59')
}

/** 倒计时文案：X天X小时 / X小时 / 不足1小时 / 已截止 */
export function countdownText(deadline: string, nowMs: number = Date.now()): string {
  const diff = deadlineMoment(deadline).getTime() - nowMs
  if (diff <= 0) return '已截止'
  const days = Math.floor(diff / 86400000)
  const hours = Math.floor((diff % 86400000) / 3600000)
  if (days > 0) return days + '天' + hours + '小时'
  if (hours > 0) return hours + '小时'
  return '不足1小时'
}

export function deadlineRelative(deadline: string): string {
  const d = daysUntil(deadline)
  if (d < 0) return '已截止'
  if (d === 0) return '今天截止'
  if (d === 1) return '明天截止'
  return d + '天后截止'
}

export function formatRange(start: string | null, end: string | null): string {
  if (start && end) return start === end ? start : start + ' ~ ' + end
  if (start) return start + ' 开始'
  if (end) return '至 ' + end
  return '时间待定'
}

/** ISO8601 时间戳 -> 'YYYY-MM-DD HH:mm'（本地时区） */
export function formatDateTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes())
}

/** 从 axios 错误 / Error 中提取中文原因（后端错误格式 {"detail":"..."}，SPEC §4） */
export function errText(e: unknown): string {
  if (e && typeof e === 'object') {
    const resp = (e as { response?: { data?: { detail?: string } } }).response
    if (resp && resp.data && resp.data.detail) return resp.data.detail
  }
  if (e instanceof Error && e.message) return e.message
  return '请求失败，请稍后重试'
}

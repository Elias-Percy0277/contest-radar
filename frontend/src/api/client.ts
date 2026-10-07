// 统一 API 客户端（SPEC §4 全部端点）：
// 1) VITE_USE_MOCK=1 时直接使用本地 Mock；
// 2) 任一真实请求失败（网络错误或非 2xx）自动降级 Mock，顶栏显示“Mock 演示数据”徽标。
import axios from 'axios'
import { ref } from 'vue'
import { mockApi } from './mock'
import type {
  Contest,
  ContestQuery,
  ContestsResponse,
  ManualContestPayload,
  RefreshStatus,
  SourceInfo,
  StatsResponse,
} from '../types'

const http = axios.create({ baseURL: '/api', timeout: 8000 })

/** 当前是否处于 Mock 模式（响应式，供顶栏徽标） */
export const mockMode = ref(import.meta.env.VITE_USE_MOCK === '1')
let warned = false

async function request<T>(method: 'get' | 'post', url: string, data?: unknown, params?: ContestQuery): Promise<T> {
  if (!mockMode.value) {
    try {
      const resp = await http.request<T>({ method, url, data, params })
      return resp.data
    } catch (err) {
      mockMode.value = true
      if (!warned) {
        warned = true
        console.warn('[ContestRadar] 后端接口不可用，已自动切换到 Mock 演示数据', err)
      }
    }
  }
  // Mock 分支：把查询参数拼进 path 交给 mock 路由
  let path = url
  if (method === 'get' && params) {
    const search = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') search.append(k, String(v))
    })
    const s = search.toString()
    if (s) path += '?' + s
  }
  return mockApi.request<T>(method, path, data)
}

export const api = {
  /** GET /api/contests：默认排除 ignored（hidden=1 含 ignored） */
  getContests(query: ContestQuery = {}): Promise<ContestsResponse> {
    return request<ContestsResponse>('get', '/contests', undefined, query)
  },
  /** POST /api/contests/{id}/my_status */
  setMyStatus(id: number, value: 'joined' | 'ignored' | 'none'): Promise<Contest> {
    return request<Contest>('post', '/contests/' + id + '/my_status', { value })
  },
  /** POST /api/contests/manual（手动补录） */
  addManualContest(payload: ManualContestPayload): Promise<Contest> {
    return request<Contest>('post', '/contests/manual', payload)
  },
  /** POST /api/refresh（触发立即抓取） */
  refresh(): Promise<{ started: boolean }> {
    return request<{ started: boolean }>('post', '/refresh')
  },
  /** GET /api/refresh/status */
  getRefreshStatus(): Promise<RefreshStatus> {
    return request<RefreshStatus>('get', '/refresh/status')
  },
  /** GET /api/sources */
  getSources(): Promise<SourceInfo[]> {
    return request<SourceInfo[]>('get', '/sources')
  },
  /** GET /api/stats */
  getStats(): Promise<StatsResponse> {
    return request<StatsResponse>('get', '/stats')
  },
}

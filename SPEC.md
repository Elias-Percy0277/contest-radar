# 竞赛雷达 ContestRadar — 技术规范与协作契约（SPEC v1）

> 本文件是全队（Lead + backend-core + sources-crawler + frontend-ui）的唯一权威契约。
> 任何与本文冲突的实现以本文为准；需要改契约必须先消息 Lead 协商，由 Lead 修改本文件后再动手。

## 1. 项目概述

单用户本地 Web 应用：按可配置信息源抓取竞赛/认证信息（首批：CCF CSP、华为云大赛、牛客、Codeforces），聚合去重后用网页可视化呈现。**无后台常驻**：打开程序即检索（缓存 6 小时 + 手动刷新按钮）。需支持 Windows 与 macOS 双平台脚本启动。

- 后端：Python 3.11+ / FastAPI / SQLite（SQLAlchemy 2.0）
- 抓取：混合方案 —— httpx+BeautifulSoup4（默认）、公开 API（Codeforces）、Playwright Chromium（仅华为云）
- 前端：Vue 3（Vite + TypeScript）+ Element Plus + ECharts，中文界面、跟随系统暗色
- LLM：DeepSeek 原生 API（`api.deepseek.com`，模型 `deepseek-chat`）做摘要与分类；**无 Key 自动降级**为关键词规则分类 + 截取摘要
- 分类侧重赛事类型；每条必须标注"是否允许使用 AI"（allowed/forbidden/unknown，拿不到就 unknown）

## 2. 目录结构与所有权（写权限，越界修改一律禁止）

```
contest-radar/
├─ SPEC.md                    # 本文件（Lead）
├─ README.md                  # Lead（依赖清单必须放最前面）
├─ start.bat / run.command    # Lead
├─ .gitignore                 # Lead
├─ backend/                   # backend-core 为主
│  ├─ requirements.txt        #   backend-core（版本锁死）
│  ├─ config.example.yaml     #   backend-core
│  ├─ sources.yaml            #   sources-crawler
│  ├─ data/                   #   运行时生成（contests.db）
│  ├─ tests/                  #   各自写各自模块的测试
│  └─ app/
│     ├─ main.py config.py db.py models.py seed.py   # backend-core
│     ├─ fetcher/             #   调度器 backend-core；base.py 为契约（Lead，勿改）
│     ├─ parsers/             #   sources-crawler（每源一个文件）
│     ├─ services/            #   backend-core（去重/状态推导/保留清理）
│     ├─ llm/                 #   backend-core（DeepSeek 客户端 + 规则降级）
│     └─ api/                 #   backend-core（REST 路由）
└─ frontend/                  # frontend-ui（全部）
```

Python 虚拟环境约定（避免并发安装冲突）：backend-core 用 `contest-radar/.venv`；sources-crawler 自建 `contest-radar/.venv-sources`（只装 httpx/bs4/lxml/pytest，Playwright 内核较大，下载失败就跳过实测并在代码里留 TODO）。前端用 pnpm（`load_workspace_dependencies` 提供 node/pnpm 路径）。

## 3. 数据模型 Contest（ ContestRaw = 解析器产出；Contest = 库表/API 字段）

ContestRaw（parsers 产出，缺省字段可省略）：

| 字段 | 类型 | 说明 |
|---|---|---|
| title | str 必填 | 竞赛全名 |
| url | str 必填 | 详情页原始 URL（入库前由框架规范化为 canonical_url） |
| category | str 必填 | 枚举：算法竞赛/AI与数据科学/应用与开发/网络安全/综合学科/认证考试 |
| reg_start / reg_deadline / contest_start / contest_end | str/null | "YYYY-MM-DD"；解析不到填 null |
| organizer | str/null | 主办方 |
| tags | list[str] | 如 ["个人赛","限在校生","国家级","企业级"] |
| ai_policy | str | allowed / forbidden / unknown（默认 unknown） |
| prize / eligibility / requirements | str/null | 奖金、参赛要求（学历/队伍人数等） |
| summary | str/null | 解析器可给原始摘要文本；LLM 层会重写并标 summary_by |

Contest = ContestRaw + 框架补齐：`id, source_id, source_name, canonical_url(唯一键), summary_by(llm|rule), status, my_status, first_seen, last_updated, is_new`。

**canonical_url 规范化**：scheme/host 小写、去 fragment、去尾部斜杠、去 utm_* / from / spm 查询参数、其余参数按 key 排序。

**status 推导**（每日/查询时按本地时区 Asia/Shanghai 计算，优先级从上到下）：
1. contest_end < 今天 → `ended`
2. contest_start ≤ 今天 ≤ contest_end → `ongoing`
3. contest_start ≤ 今天 且 contest_end 为 null → `ongoing`
4. reg_deadline ≥ 今天 且（reg_start 为 null 或 ≤ 今天）且（contest_start 为 null 或 > 今天）→ `registering`
5. 其余（无任何日期）→ `unknown`

**my_status**：`none` / `joined`（我要参加→进"我的日程"并钉住日历）/ `ignored`（不感兴趣→列表默认隐藏）。

**is_new**：first_seen 距今 < 48h。

**保留清理**（每次刷新后执行）：
- joined：contest_end + 7 天后删；end 为 null 则 last_updated + 30 天删
- 其余（含 ignored）：status ∈ {registering, ongoing} 不删；ended 在 contest_end + 30 天后删；status unknown 在 last_updated + 30 天后删

## 4. REST API 契约（前缀 /api，JSON；日期 "YYYY-MM-DD"，时间戳 ISO8601 带时区）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/contests | 查询参数：category, status, my_status, q(标题模糊), source_id, hidden=1(含ignored)；默认排除 ignored。sort=deadline|new|title，默认 deadline（无截止的排最后）。返回 `{items:[Contest...], total}` |
| POST | /api/contests/{id}/my_status | body `{"value":"joined"|"ignored"|"none"}`，返回更新后 Contest |
| POST | /api/contests/manual | 手动补录，body 为 ContestRaw 子集（title/url/category 必填），source_id 固定 "manual" |
| POST | /api/refresh | 触发立即抓取（异步执行），返回 `{"started":true}` |
| GET | /api/refresh/status | `{"running":bool,"last_run":dt,"last_ok":dt,"cache_hours":6}` |
| GET | /api/sources | `[{id,name,method,enabled,last_run,last_ok,last_error}]` 源健康面板数据 |
| GET | /api/stats | 仪表盘：`{by_category:{}, by_status:{}, weekly_new:[{week:"2026-W40",count}×8], upcoming_deadlines:[前5条Contest，joined优先], joined_count, last_refresh, sources:[...同/api/sources]}` |

响应统一 CORS 允许 http://localhost:5173 与 http://127.0.0.1:5173。错误返回 `{"detail":"中文原因"}`。

## 5. 解析器接口（app/fetcher/base.py，已有，勿改）

`BaseSource`：子类设 `source_id/name/method`，`fetch()` 返回 `list[dict]`（ContestRaw）。失败抛 `SourceError("中文原因")`。Playwright 源（method="playwright"）在 fetch() 内自行启动/关闭 chromium（`playwright.async_api`）；内核未安装时抛 SourceError 提示"请先运行 playwright install chromium"。

调度器（backend-core 实现）：读 sources.yaml → 每源实例化 parser（importlib 按 `parser` 字段）→ asyncio 并发（上限 3）→ 单源超时 http/api 30s、playwright 60s，失败重试 2 次 → 成功则入库（去重合并）+ 更新源健康 → 全部结束后跑 LLM 加工 + 保留清理。缓存：距 last_ok < cache_hours(6) 的源本次跳过（手动刷新强制全量）。

## 6. 配置文件格式

**sources.yaml**（sources-crawler 维护）：
```yaml
sources:
  - id: ccf_csp
    name: CCF CSP认证
    method: http
    parser: app.parsers.cspro.CsproSource
    enabled: true
    params: { url: "https://www.cspro.org/cms/show.action?code=publish_8ac21fad9d27f22a019f5944f2eb00e1&siteid=100000" }
```

**backend/config.example.yaml**（backend-core 维护，运行时复制为 config.yaml，config.yaml 已 gitignore）：
```yaml
server: { host: 127.0.0.1, port: 8300 }
fetch: { cache_hours: 6, concurrency: 3, timeout_seconds: 30, playwright_timeout_seconds: 60, retries: 2 }
llm:
  enabled: true
  api_key: ""            # DeepSeek API Key；留空自动降级为规则模式
  base_url: https://api.deepseek.com
  model: deepseek-chat
retention: { joined_grace_days: 7, unmarked_ended_days: 30, stale_unknown_days: 30 }
```

## 7. 前端契约（frontend-ui）

- 路由：`/` 仪表盘、`/list` 竞赛列表、`/calendar` 日历、`/countdown` 倒计时墙、`/schedule` 我的日程（my_status=joined）
- 列表：筛选（分类/状态/来源/我的状态）、排序（截止优先）、"NEW"徽标、状态 tag 配色（报名中=primary、进行中=success、已结束=info、未知=warning）、操作：我要参加/忽略/取消、手动补录入口
- 仪表盘：统计卡片（报名中数量/我参加的/本周新增）+ ECharts（weekly_new 柱状、by_category 饼图）+ 即将截止 top5
- 日历：月历上标 reg_deadline（橙点）与 contest_start（蓝点），joined 高亮描边；点日期列出当日相关竞赛
- 倒计时墙：卡片按 reg_deadline 升序，倒计时"3天2小时"，过期的移入"已截止"分组
- 我的日程：joined 列表 + 按月分组视图
- 源健康面板：仪表盘页底部小表格（源名/方式/上次成功/异常原因）
- **Mock 模式**：`src/api/client.ts` 统一封装；`VITE_USE_MOCK=1`（或 /api 请求失败时自动）使用本地 mock 数据（字段与 SPEC §4 完全一致），保证后端未起也能开发演示
- 开发代理：vite.config.ts `server.proxy['/api'] → http://127.0.0.1:8300`；生产构建 dist 由后端静态挂载
- Element Plus 暗色：跟随 `prefers-color-scheme`，可用开关手动切换（localStorage 记忆）

## 8. 环境与运行

- 后端启动：`uvicorn app.main:app --port 8300`（app-dir=backend）。main.py lifespan：首次启动若距上次成功抓取超 cache_hours 则后台任务刷新；挂载 `frontend/dist`（存在时）到 `/`；启动完成 1.5s 后 `webbrowser.open("http://127.0.0.1:8300")`（环境变量 DISABLE_AUTO_OPEN=1 可关）
- 种子数据：`python -m app.seed`（backend/ 下）写入 ≥8 条假数据（覆盖各分类/状态/joined），供前后端联调
- Python venv 按 §2；pytest 至少覆盖：status 推导、canonical_url 规范化、保留清理、parsers 对保存的 fixture HTML 的解析（sources-crawler 负责 fixtures）

## 9. 协作规则

1. 只改自己写权限内的文件；发现别处需要改 → 消息 Lead
2. 契约（本文件、base.py、API 格式）有歧义 → 消息 Lead 澄清，勿自行发挥
3. 完成后：更新共享任务（team_task claim→complete）并 send_message Lead 汇报（做了什么/怎么验证/遗留 TODO）
4. 不执行 git 操作、不改工作区外文件；不向用户提问，做合理假设并记录
5. 代码注释与 docstring 用中文；Python 全量 type hints

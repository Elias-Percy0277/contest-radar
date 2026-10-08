# 竞赛雷达 ContestRadar

面向 CS 学生的本地竞赛信息聚合与可视化应用：打开程序自动检索 CCF CSP 认证、华为云大赛、牛客、Codeforces 等信息源的赛事动态，聚合去重后在网页上呈现（仪表盘 / 列表 / 日历 / 倒计时墙 / 我的日程）。无需后台常驻，支持 Windows 与 macOS。

## 一、依赖要求（使用前先确认）

| 依赖 | 说明 |
|---|---|
| **Python 3.11+** | Windows 从 [python.org](https://www.python.org/downloads/windows/) 安装，安装时勾选 **Add python.exe to PATH** |
| pip / venv | 随 Python 自带，无需单独安装 |
| Playwright Chromium | 首次运行由脚本自动下载（约 150MB，自动走 npmmirror 国内镜像），仅华为云源需要 |
| DeepSeek API Key（可选） | 填入 `backend/config.yaml` 启用 LLM 摘要与分类；不填自动降级为规则模式，功能不受阻 |
| Node 18+ / pnpm（可选） | 仅修改前端时需要；日常使用直接用已构建产物，无需安装 |

首次运行脚本会自动完成：创建虚拟环境 → 安装全部 Python 依赖（fastapi、uvicorn、sqlalchemy、httpx、beautifulsoup4、lxml、pyyaml、openai、playwright）→ 下载 Chromium 内核 → 复制配置文件。之后每次启动直接运行。

## 二、快速开始

**Windows**：双击 `start.bat`
**macOS**：双击 `run.command`（或在终端 `bash run.command`）

启动后浏览器自动打开 http://127.0.0.1:8300 ；首次抓取在后台进行，几秒后刷新页面即可看到数据。

## 三、配置

- `backend/config.yaml`（首次自动从 `config.example.yaml` 复制）
  - `llm.api_key`：DeepSeek API Key（https://platform.deepseek.com 申请）
  - `fetch.cache_hours`：缓存时长，距上次成功抓取不足该值时启动不再重复抓
  - `retention.*`：数据保留策略（我要参加的赛事保留至结束后 7 天，其余结束后 30 天清理）
- `backend/sources.yaml`：信息源清单——改 `enabled` 开关即可启停某源；新增站点需要对应 parser（见 `backend/app/parsers/`）

## 四、目录结构

```
backend/   FastAPI 后端（app/ 代码，data/contests.db 本地数据库，tests/ 测试）
frontend/  Vue3 + Element Plus + ECharts 前端（构建产物由后端自动挂载）
start.bat / run.command  双平台启动脚本
SPEC.md    技术规范与接口契约（开发者必读）
```

## 五、常见问题

- **Chromium 下载失败**：手动执行 `PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright .venv/bin/python -m playwright install chromium`（Windows 路径为 `.venv\Scripts\python.exe`）。下载失败只影响华为云源，其余源不受影响。
- **杀毒软件拦截**：无头 Chromium 可能被误报，将 `.venv` 目录加入白名单即可。
- **端口被占用**：修改 `backend/config.yaml` 的 `server.port`，并用同样端口手动启动：`.venv/bin/python -m uvicorn app.main:app --port <端口> --app-dir backend`。
- **某源显示异常**：仪表盘底部"源健康"面板会显示每个源的上次成功时间与失败原因。
- **Playwright 源报 "chromium 内核缺失"**：多因多个虚拟环境的 playwright 版本不一致——它们共享浏览器缓存目录，新版本安装时会把旧内核回收掉。在项目目录运行 `PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright .venv/bin/python -m playwright install chromium` 重装即可（约150MB）。

## 六、开发者

```bash
# 后端测试
.venv/bin/python -m pytest backend/tests -q
# 假数据联调
cd backend && python -m app.seed
# 前端开发
cd frontend && pnpm install && pnpm dev   # http://localhost:5173，/api 自动代理到 8300
```

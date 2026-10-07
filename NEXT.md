# 续作清单（2026-10-08 凌晨收尾时的状态快照）

## 已完成（待最后一次验证）

- **15 个信息源全部接入**：9 HTTP + 1 API + 5 Playwright（蓝桥杯/知乎黑客松/百度之星为新增 Playwright 源）
- **手动深挖功能全链路**：列表页"深挖"按钮 → 后端抓详情页（HTTP 优先，SPA 回退渲染）→ LLM 抽取 AI政策/参赛要求/奖金 → 打"已深挖"标签
- 测试：87 passed + 2 skipped（live 变体）；sources-crawler 单独跑过 32 全过含全部 live
- dist 构建产物已纳入 git（Windows 克隆即用，无需 Node）

## ⚠️ 明早第一件事：复验 5 个 Playwright 源

**现象**：01:15 的 15 源全量刷新中，5 个 Playwright 源全部报"需要 pip install playwright"，
但 .venv 里 playwright 1.60.0 完好、import 正常、23:50 时同类刷新全部成功。

**最可能原因**：当时 sources-crawler 的后台 live 测试仍有 chromium 残留进程，多个 playwright
源并发启动 chromium 时资源冲突，launch 失败被解析器误报为"未安装"。

**复验步骤**（安静环境）：
```bash
cd contest-radar && ./run.command   # 或手动起 uvicorn
# 页面点"立即刷新"，或:
curl -X POST http://127.0.0.1:8300/api/refresh
```
预期：15/15 源 OK；数据库新增 lanqiao(≈27)/zhihu_hackathon(1)/astar(3) 条
（这三源 01:15 失败，数据尚未入库；其余源数据都在，共 61 条）。

## 小改进（顺手做）

1. **解析器错误信息修复**：playwright 启动失败（资源型）目前被误报为"需要 pip install"——
   lanqiao/zhihu_hackathon/astar/huawei/ccf_cacc 五个解析器的异常分支要把 ImportError 与
   launch 失败区分开（ImportError→装包提示；launch 失败→"chromium 启动失败，可能是并发资源不足"）
2. 调度器可考虑对 playwright 源做串行化（Semaphore 单独限 1-2），避免同时 5 个 chromium

## 之后的路线

- 字节/腾讯赛事入口调研（campus.bytedance.com 不存在；试掘金/jobs.bytedance.com）
- 深挖按钮真实体验反馈 → P1 收尾
- Windows 实机部署验证（M4 收官）：git clone → start.bat

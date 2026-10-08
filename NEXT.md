# 续作清单（2026-10-08 上午更新）

## ✅ 今晨已完成

- **15 源全量刷新 15/15 OK**，数据 89 条（蓝桥杯 27、天池 10、挑战杯 10、计设 5、CSP 5、CF 5 等）
- **昨晚 Playwright 故障定位并修复**：根因是多虚拟环境 playwright 版本不一致，共享
  ~/Library/Caches/ms-playwright 时旧内核（v1223）被新版本安装时回收。已重装内核，
  并在 README 常见问题中记录此坑
- **防复发改进 ×2**（昨晚 NEXT.md 遗留）：
  1. 五个 Playwright 解析器统一用 _util.playwright_launch_error() 报错——
     内核缺失/启动失败/包未装三种情况给出准确的人话提示
  2. 调度器对 playwright 源单独限流（_PLAYWRIGHT_CONCURRENCY=2），与 HTTP 并发分开计数
- 测试 87 passed + 2 skipped

## 待办（按优先级）

1. ~~字节/腾讯赛事入口调研~~ **已结案（2026-10-08）**：两家均无稳定官方赛事页（走公众号/牛客/掘金动态发布）；
   已落地替代方案：DataFountain + 赛氪聚合两源上线（commit 8ecc32d），大厂散落赛事由聚合兜底
2. **Windows 实机部署验证（M4 收官）**：git clone → start.bat → 依赖自动安装 → 15 源抓取
   （重点验证：Chromium 镜像下载、CCF 系源的 curl 兜底在 Win10+ 的可用性）
3. **深挖按钮真实体验**：用几天，收集"AI 政策抽取准确率"体感，不准的案例回流调提示词
4. 知乎黑客松源当前 0 条在办（2026-03 场次已结束被过滤）——属正常，下届自动出现
5. 赛氪条目无日期（详情页才有）→ 状态 unknown，30 天无更新会被保留清理删除、下次抓取重新
   插入（轻度churn）——后续可做详情页日期补抓消除
6. DataFountain 当前 0 条在办属赛季性正常（2026 赛季 8 月底结束），新赛季自动出现
7. 用户计划把工作环境迁移 Docker 后再做 Windows 验证——届时可提供 Dockerfile
   （注意容器内 Playwright 需补字体/依赖库）

## 环境备忘

- 本机两套 venv：.venv（运行/主开发，playwright 1.60.0）与 .venv-sources（爬虫开发）——
  **升级任何一方的 playwright 前先同步另一方**，否则浏览器内核会被回收（今晨的坑）
- GitHub Token（~30 天有效期）与 DeepSeek Key 都托管在 ~/.config/contest-radar/
- dist 已入 git：改前端后记得重新构建再提交

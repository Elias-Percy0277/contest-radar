# 竞赛雷达 ContestRadar · 前端（frontend/）

Vue 3 + Vite + TypeScript + Element Plus + ECharts + Pinia。界面全中文，暗色跟随系统
prefers-color-scheme 且顶栏可手动切换（localStorage 记忆）。

## 页面

    /           仪表盘（统计卡片 + weekly_new 柱状图 + by_category 饼图 + 即将截止 top5 + 源健康表）
    /list       竞赛列表（筛选/排序/NEW 徽标/我要参加/忽略/恢复/手动补录/立即刷新）
    /calendar   日历（reg_deadline 橙点、contest_start 蓝点、joined 描边、点日期看当日竞赛）
    /countdown  倒计时墙（按截止升序、每分钟刷新、已截止折叠分组）
    /schedule   我的日程（my_status=joined 按月分组、标记进行中/未开始/已结束）

## 开发

    pnpm install
    pnpm dev          # http://localhost:5173，/api 代理到 http://127.0.0.1:8300

后端未启动时，api/client.ts 会在请求失败后自动切换到本地 Mock 数据（顶栏出现
“Mock 演示数据”徽标），字段结构与 SPEC §4 完全一致；强制使用 Mock：

    VITE_USE_MOCK=1 pnpm dev

## 构建与联调

    pnpm build        # vue-tsc --noEmit + vite build，产物 dist/
    pnpm preview      # 本地预览构建产物

生产模式由后端把 dist/ 挂载到 /（SPEC §8）。路由采用 hash 模式（/#/list），
静态挂载无需 SPA 回退即可任意刷新。

## 已记录的实现假设

- 路由为 hash 模式（createWebHashHistory），保证后端静态挂载下深链接可刷新。
- reg_deadline 只有日期（YYYY-MM-DD），倒计时按当日 23:59:59（本地时区）计。
- “本周新增”取 /api/stats weekly_new 最后一项（当前周）。
- 列表“我的状态=已忽略”时自动带 hidden=1（SPEC §4），其余情况默认排除 ignored。
- Mock 触发刷新后约 4 秒结束 running，并将一条竞赛标记为 NEW，便于演示轮询。
- 一旦真实请求失败切到 Mock，本轮会话保持 Mock（刷新页面后重试真实后端）。

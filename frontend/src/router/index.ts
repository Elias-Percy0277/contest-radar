import { createRouter, createWebHashHistory } from 'vue-router'

// hash 路由：后端把 dist/ 静态挂载到 / 时，深链接刷新无需 SPA 回退（假设已记录于 README）
const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: () => import('../views/DashboardView.vue'), meta: { title: '仪表盘' } },
    { path: '/list', name: 'list', component: () => import('../views/ListView.vue'), meta: { title: '竞赛列表' } },
    { path: '/calendar', name: 'calendar', component: () => import('../views/CalendarView.vue'), meta: { title: '日历' } },
    { path: '/countdown', name: 'countdown', component: () => import('../views/CountdownView.vue'), meta: { title: '倒计时墙' } },
    { path: '/schedule', name: 'schedule', component: () => import('../views/ScheduleView.vue'), meta: { title: '我的日程' } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.afterEach((to) => {
  const title = typeof to.meta.title === 'string' ? to.meta.title : ''
  document.title = title ? title + ' · 竞赛雷达' : '竞赛雷达 ContestRadar'
})

export default router

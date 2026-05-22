import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: () => import('../views/HomeView.vue') },
    { path: '/new', name: 'new', component: () => import('../views/NewNovelView.vue') },
    { path: '/novel/:name', name: 'novel', component: () => import('../views/NovelDetailView.vue') },
    { path: '/revise', name: 'revise', component: () => import('../views/ReviseView.vue') },
    { path: '/continue', name: 'continue', component: () => import('../views/ContinueView.vue') },
  ],
})

export default router

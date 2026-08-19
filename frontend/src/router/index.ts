import { createRouter, createWebHistory } from 'vue-router'
import MainLayout from '../layouts/MainLayout.vue'
import JobAnalysis from '../views/JobAnalysis.vue'
import JobDetail from '../views/JobDetail.vue'
import JobOverview from '../views/JobOverview.vue'
import Management from '../views/Management.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/jobs' },
    {
      path: '/',
      component: MainLayout,
      children: [
        { path: 'jobs', name: 'jobs', component: JobOverview },
        { path: 'jobs/:id', name: 'job-detail', component: JobDetail },
        { path: 'analysis', name: 'analysis', component: JobAnalysis },
        { path: 'management', name: 'management', component: Management },
      ],
    },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

export default router

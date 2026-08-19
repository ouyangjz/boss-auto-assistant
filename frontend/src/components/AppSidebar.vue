<script setup lang="ts">
import { useRoute } from 'vue-router'

const route = useRoute()

const navigation = [
  { label: '投递总览', path: '/jobs', icon: '▦' },
  { label: '岗位分析', path: '/analysis', icon: '⌁' },
  { label: '管理功能', path: '/management', icon: '⚙' },
]

function isActive(path: string) {
  return path === '/jobs' ? route.path.startsWith('/jobs') : route.path === path
}
</script>

<template>
  <aside class="sidebar">
    <div class="brand">
      <div class="brand-mark">B</div>
      <div>
        <div class="brand-title">求职管理后台</div>
        <div class="brand-subtitle">Job workspace</div>
      </div>
    </div>

    <nav class="sidebar-nav" aria-label="主导航">
      <RouterLink
        v-for="item in navigation"
        :key="item.path"
        :to="item.path"
        class="nav-item"
        :class="{ active: isActive(item.path) }"
      >
        <span class="nav-icon" aria-hidden="true">{{ item.icon }}</span>
        <span>{{ item.label }}</span>
      </RouterLink>
    </nav>

    <div class="sidebar-footer">
      <span class="service-dot" />
      本地服务
    </div>
  </aside>
</template>

<script setup lang="ts">
import AppSidebar from '../components/AppSidebar.vue'
</script>

<template>
  <div class="app-shell">
    <AppSidebar />
    <main class="main-content">
      <RouterView />
    </main>
  </div>
</template>

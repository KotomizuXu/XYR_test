<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <n-layout-header bordered class="app-header">
    <div class="header-left">
      <h1 class="logo" @click="router.push('/')">Novel Agent</h1>
    </div>
    <div class="header-right">
      <n-button quaternary @click="router.push('/')">首页</n-button>
      <n-button type="primary" @click="router.push('/new')">新建小说</n-button>
    </div>
  </n-layout-header>
</template>

<style scoped>
.app-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 24px; height: 56px;
}
.logo {
  cursor: pointer; font-size: 18px; font-weight: 700;
  background: linear-gradient(135deg, #36ad6a, #5acea0);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.header-right { display: flex; gap: 8px; }
</style>

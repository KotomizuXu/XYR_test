<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useNovelStore } from '../store'

const store = useNovelStore()
const router = useRouter()

const completedNovels = ref<any[]>([])

onMounted(async () => {
  await store.fetchNovels()
  completedNovels.value = store.novels.filter(n => n.phase === 'complete')
})
</script>

<template>
  <div class="revise-select">
    <n-card title="选择小说" class="form-card">
      <n-space vertical size="large">
        <n-list bordered>
          <n-list-item v-for="novel in completedNovels" :key="novel.name">
            <n-thing>
              <template #header>《{{ novel.name }}》</template>
              <template #description>
                <n-text depth="3">{{ novel.current_chapter }}/{{ novel.total_chapters }} 章 · 已完成</n-text>
              </template>
              <template #action>
                <n-button type="primary" size="small" @click="router.push(`/novel/${novel.name}`)">
                  进入
                </n-button>
              </template>
            </n-thing>
          </n-list-item>
        </n-list>
        <n-empty v-if="!completedNovels.length" description="暂无已完成的小说">
          <template #extra>
            <n-button @click="router.push('/')">返回首页</n-button>
          </template>
        </n-empty>
      </n-space>
    </n-card>
  </div>
</template>

<style scoped>
.revise-select { max-width: 600px; margin: 40px auto; }
.form-card { border-radius: 16px; }
</style>

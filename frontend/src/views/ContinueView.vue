<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useNovelStore } from '../store'

const store = useNovelStore()
const router = useRouter()

const incompleteNovels = ref<any[]>([])

onMounted(async () => {
  await store.fetchNovels()
  incompleteNovels.value = store.novels.filter(n => n.phase !== 'complete')
})
</script>

<template>
  <div class="continue-select">
    <n-card title="选择小说" class="form-card">
      <n-space vertical size="large">
        <n-list bordered>
          <n-list-item v-for="novel in incompleteNovels" :key="novel.name">
            <n-thing>
              <template #header>《{{ novel.name }}》</template>
              <template #description>
                <n-space align="center" :size="8">
                  <n-tag size="small" :type="novel.phase === 'complete' ? 'success' : 'warning'">
                    {{ novel.phase }}
                  </n-tag>
                  <n-text v-if="novel.total_chapters" depth="3">
                    {{ novel.current_chapter }}/{{ novel.total_chapters }} 章
                  </n-text>
                </n-space>
              </template>
              <template #action>
                <n-button type="primary" size="small" @click="router.push(`/novel/${novel.name}`)">
                  进入
                </n-button>
              </template>
            </n-thing>
          </n-list-item>
        </n-list>
        <n-empty v-if="!incompleteNovels.length" description="暂无未完成的小说">
          <template #extra>
            <n-button @click="router.push('/new')">开始创作</n-button>
          </template>
        </n-empty>
      </n-space>
    </n-card>
  </div>
</template>

<style scoped>
.continue-select { max-width: 600px; margin: 40px auto; }
.form-card { border-radius: 16px; }
</style>

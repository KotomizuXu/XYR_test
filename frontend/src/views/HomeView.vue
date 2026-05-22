<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useNovelStore } from '../store'

const store = useNovelStore()
const router = useRouter()

onMounted(() => store.fetchNovels())

const phaseLabel: Record<string, string> = {
  styling: '风格分析', collecting_params: '参数确认', directing: '导演阶段',
  plotting: '剧情拆章', writing: '写作中', editing: '润色中', complete: '已完成',
}

const phaseColor: Record<string, string> = {
  styling: '#36ad6a', collecting_params: '#36ad6a', directing: '#d0a000',
  plotting: '#36ad6a', writing: '#5acea0', editing: '#5acea0', complete: '#36ad6a',
}
</script>

<template>
  <div>
    <n-space vertical size="large">
      <div class="hero">
        <h1>AI 多角色协作小说生成</h1>
        <p>7 个 Agent 协作：风格顾问 → 导演 → 编剧 → 作家 → 审稿 → 编辑 → 评审</p>
      </div>

      <n-grid :cols="1" :x-gap="16" :y-gap="16">
        <n-gi v-for="novel in store.novels" :key="novel.name">
          <n-card hoverable @click="router.push(`/novel/${novel.name}`)" class="novel-card">
            <div class="card-header">
              <h3>《{{ novel.name }}》</h3>
              <n-tag :color="{ color: phaseColor[novel.phase] || '#78788c', textColor: '#fff' }" size="small">
                {{ phaseLabel[novel.phase] || novel.phase }}
              </n-tag>
            </div>
            <p class="card-preview">{{ novel.story_idea_preview }}</p>
            <div v-if="novel.total_chapters" class="card-meta">
              <n-progress :percentage="Math.round((novel.current_chapter / novel.total_chapters) * 100)" :height="6" :show-indicator="false" />
              <span>{{ novel.current_chapter }}/{{ novel.total_chapters }} 章</span>
            </div>
          </n-card>
        </n-gi>
      </n-grid>

      <n-empty v-if="!store.novels.length" description="暂无小说项目">
        <template #extra>
          <n-button type="primary" @click="router.push('/new')">开始创作</n-button>
        </template>
      </n-empty>
    </n-space>
  </div>
</template>

<style scoped>
.hero { text-align: center; padding: 40px 0 20px; }
.hero h1 { font-size: 28px; font-weight: 700; background: linear-gradient(135deg, #36ad6a, #5acea0); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.hero p { color: rgba(255,255,255,0.5); margin-top: 8px; }
.novel-card { cursor: pointer; transition: transform 0.2s; }
.novel-card:hover { transform: translateY(-2px); }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.card-header h3 { margin: 0; font-size: 16px; }
.card-preview { color: rgba(255,255,255,0.5); font-size: 13px; margin-top: 8px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.card-meta { display: flex; align-items: center; gap: 8px; margin-top: 8px; font-size: 12px; color: rgba(255,255,255,0.4); }
</style>

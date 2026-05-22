<script setup lang="ts">
import { ref, computed } from 'vue'
import { useNovelStore } from '../store'

const store = useNovelStore()

const storyIdea = ref('')
const novelName = ref('')
const style = ref('')
const step = ref<'form' | 'running'>('form')

const nameCandidates = ref<string[]>([])
const nameLoading = ref(false)

const INVALID_CHARS = new Set(['\\', '/', ':', '*', '?', '"', '<', '>', '|'])
const WINDOWS_RESERVED = new Set([
  'CON', 'PRN', 'AUX', 'NUL',
  ...Array.from({ length: 9 }, (_, i) => `COM${i + 1}`),
  ...Array.from({ length: 9 }, (_, i) => `LPT${i + 1}`),
])

const nameValidationError = computed(() => {
  const name = novelName.value
  if (!name || !name.trim()) return ''
  if (name.length > 64) return '小说名称过长（>64 字符），请使用更短的名字'
  const bad = [...name].filter(c => INVALID_CHARS.has(c))
  if (bad.length) return `小说名称包含非法字符：${[...new Set(bad)].join('')}（不允许 \\ / : * ? " < > |）`
  if (name.endsWith('.') || name.endsWith(' ')) return "小说名称不能以 '.' 或空格结尾"
  const base = name.split('.')[0].toUpperCase()
  if (WINDOWS_RESERVED.has(base)) return `「${name}」是 Windows 保留名，请换一个名字`
  return ''
})

async function fetchNameSuggestions() {
  if (!storyIdea.value.trim()) return
  nameLoading.value = true
  try {
    const res = await fetch('/api/suggest-names', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ idea: storyIdea.value, style: style.value || null }),
    })
    const data = await res.json()
    nameCandidates.value = data.candidates || []
  } catch { nameCandidates.value = [] }
  finally { nameLoading.value = false }
}

function pickCandidate(name: string) {
  novelName.value = name
  nameCandidates.value = []
}

function startCreation() {
  if (!storyIdea.value.trim()) return
  if (!novelName.value.trim()) return
  if (nameValidationError.value) return
  store.connect()
  step.value = 'running'
  setTimeout(() => {
    store.startMode('new', {
      story_idea: storyIdea.value,
      novel_name: novelName.value,
      style: style.value || null,
    })
  }, 500)
}
</script>

<template>
  <div v-if="step === 'form'" class="new-form">
    <n-card title="开始创作新小说" class="form-card">
      <n-space vertical size="large">
        <n-form-item label="故事灵感">
          <n-input v-model:value="storyIdea" type="textarea" :rows="5" placeholder="描述你的故事创意..." />
        </n-form-item>

        <n-form-item label="小说名称" required>
          <n-input-group>
            <n-input v-model:value="novelName" placeholder="输入小说名称，或点击 AI 起名" style="flex: 1" />
            <n-button :loading="nameLoading" :disabled="!storyIdea.trim()" @click="fetchNameSuggestions">
              AI 起名
            </n-button>
          </n-input-group>
          <n-text v-if="nameValidationError" depth="3" type="error" style="font-size: 12px; margin-top: 4px">
            {{ nameValidationError }}
          </n-text>
          <div v-if="nameCandidates.length" class="candidates">
            <n-tag
              v-for="c in nameCandidates" :key="c" size="medium"
              style="cursor: pointer" type="success"
              @click="pickCandidate(c)"
            >
              {{ c }}
            </n-tag>
            <n-button text type="info" @click="fetchNameSuggestions">再生成</n-button>
            <n-button text type="default" @click="nameCandidates = []">自己输入</n-button>
          </div>
        </n-form-item>

        <n-form-item label="风格偏好（可选）">
          <n-input v-model:value="style" placeholder="如：网文爽文、传统文学、悬疑推理" />
        </n-form-item>

        <n-button type="primary" size="large" block :disabled="!storyIdea.trim() || !novelName.trim()" @click="startCreation">
          开始创作
        </n-button>
      </n-space>
    </n-card>
  </div>
  <div v-else>
    <NovelDetailViewInner :novel-name="novelName || 'untitled'" />
  </div>
</template>

<style scoped>
.new-form { max-width: 600px; margin: 40px auto; }
.form-card { border-radius: 16px; }
.candidates { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; align-items: center; }
</style>

<script lang="ts">
import NovelDetailViewInner from './NovelDetailView.vue'
export default { components: { NovelDetailViewInner } }
</script>

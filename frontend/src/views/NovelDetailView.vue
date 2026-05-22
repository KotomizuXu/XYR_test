<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useNovelStore, type InputRequest } from '../store'
import MessageLog from '../components/display/MessageLog.vue'
import InputDispatcher from '../components/interaction/InputDispatcher.vue'
import ParamTable from '../components/display/ParamTable.vue'
import ProgressBar from '../components/display/ProgressBar.vue'
import JsonViewer from '../components/display/JsonViewer.vue'

const store = useNovelStore()
const route = useRoute()
const router = useRouter()

const props = defineProps<{ novelName?: string }>()

const isStandalone = computed(() => !!route.params.name)
const detail = ref<any>(null)
const loading = ref(false)
const activeTab = ref('styling')

const PHASE_ORDER = [
  'styling', 'collecting_params', 'directing', 'plotting',
  'writing', 'complete',
]

const phaseLabel: Record<string, string> = {
  styling: '风格分析', collecting_params: '参数确认', directing: '导演阶段',
  plotting: '剧情拆章', writing: '章节进度', complete: '已完成',
}

const STAGE_STEPS = ['drafted', 'reviewed', 'tracked', 'edited']
const STEP_LABELS: Record<string, string> = { drafted: '草稿', reviewed: '审核', tracked: '追踪', edited: '润色' }

function normalizePhase(phase: string): string {
  if (phase === 'editing') return 'writing'
  if (phase === 'refining') return 'directing'
  return phase
}

function resolveActiveTab(phase: string): string {
  const p = normalizePhase(phase)
  return PHASE_ORDER.includes(p) ? p : 'styling'
}

function phaseState(phase: string): 'past' | 'current' | 'future' {
  const cur = PHASE_ORDER.indexOf(currentPhase.value)
  const idx = PHASE_ORDER.indexOf(phase)
  if (idx < 0 || cur < 0) return 'future'
  if (idx < cur) return 'past'
  if (idx === cur) return 'current'
  return 'future'
}

function chapterStepState(ch: any): { step: string; done: boolean }[] {
  const stageIdx = ch.stage ? STAGE_STEPS.indexOf(ch.stage) : -1
  return STAGE_STEPS.map((s, i) => ({
    step: s,
    done: ch.has_edited ? true : (stageIdx >= i),
  }))
}

const groupedChapters = computed(() => {
  if (!detail.value?.volumes?.length) return null
  return detail.value.volumes.map((vol: any) => ({
    ...vol,
    chapters: detail.value.chapters.filter(
      (ch: any) => ch.number >= vol.start_chapter && ch.number <= vol.end_chapter
    ),
  }))
})

// Current phase: from REST API data or from store messages
const currentPhase = computed(() => {
  if (detail.value?.phase) return normalizePhase(detail.value.phase)
  const msgs = store.messages
  for (let i = msgs.length - 1; i >= 0; i--) {
    const m = msgs[i]
    if (m.type !== 'output') continue
    const kind = m.data?.kind
    if (kind === 'progress' || kind === 'info') {
      const label = m.data?.label || m.data?.message || ''
      if (label.includes('写作') || label.includes('撰写') || label.includes('审核') || label.includes('润色')) return 'writing'
      if (label.includes('剧情') || label.includes('拆章') || label.includes('编剧')) return 'plotting'
      if (label.includes('导演') || label.includes('世界观') || label.includes('精修')) return 'directing'
      if (label.includes('参数') || label.includes('章数')) return 'collecting_params'
      if (label.includes('风格') || label.includes('style')) return 'styling'
    }
    if (kind === 'param_suggestions') return 'collecting_params'
    if (kind === 'param_confirmed') return 'directing'
    if (kind === 'braindump_intro') return 'styling'
    if (kind === 'completion') return 'complete'
  }
  return 'styling'
})

watch(currentPhase, (p) => { activeTab.value = p })

async function fetchDetail() {
  const name = isStandalone.value
    ? (route.params.name as string)
    : props.novelName || null
  if (!name) return
  try {
    const res = await fetch(`/api/novels/${encodeURIComponent(name)}`)
    if (res.ok) detail.value = await res.json()
  } catch { /* novel may not exist yet */ }
}

let refreshTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  fetchDetail()
  activeTab.value = resolveActiveTab(detail.value?.phase || currentPhase.value)
  if (!isStandalone.value && props.novelName) {
    refreshTimer = setInterval(fetchDetail, 5000)
  }
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})

const hasSession = computed(() => store.sessionId !== null || store.messages.length > 0)

const displayMessages = computed(() =>
  store.outputMessages.filter(m => !['param_suggestions', 'param_confirmed', 'novel_list'].includes(m.data.kind))
)

const lastParamSuggestions = computed(() => {
  for (let i = store.messages.length - 1; i >= 0; i--) {
    const msg = store.messages[i]
    if (msg.type === 'output' && msg.data.kind === 'param_suggestions') return msg.data
  }
  return null
})

function handleRespond(requestId: string, value: any) {
  store.respondToInput(requestId, value)
}

const isIncomplete = computed(() => {
  const p = detail.value?.phase
  return p && p !== 'complete'
})

// Resolve novel name from standalone route or embedded prop
const novelName = computed(() => {
  if (isStandalone.value) return (route.params.name as string) || ''
  return props.novelName || ''
})

// Standalone: start continue session directly
function startContinue() {
  store.connect()
  setTimeout(() => {
    store.startMode('continue', { novel_name: novelName.value })
  }, 500)
}

// Standalone: start revise session for a specific chapter
function startRevise(chapterNumber: number) {
  store.connect()
  setTimeout(() => {
    store.startMode('revise', {
      novel_name: novelName.value,
      chapter_number: chapterNumber,
    })
  }, 500)
}

const sessionEndTitle = computed(() => {
  if (isIncomplete.value) return '流程已暂停'
  return '创作完成'
})

// Refresh detail after session ends
watch(() => store.sessionEnded, (ended) => {
  if (ended && isStandalone.value) {
    fetchDetail()
  }
})
</script>

<template>
  <div class="novel-detail">
    <n-spin :show="isStandalone && loading">
      <!-- Standalone header: title + phase tag only -->
      <n-page-header v-if="isStandalone && detail" @back="router.push('/')">
        <template #title>《{{ detail.name }}》</template>
        <template #extra>
          <n-tag :type="detail.phase === 'complete' ? 'success' : 'warning'">
            {{ phaseLabel[normalizePhase(detail.phase)] || detail.phase }}
          </n-tag>
        </template>
      </n-page-header>

      <!-- Session status bar: show whenever there's an active session -->
      <n-card v-if="hasSession" size="small" class="status-bar">
        <n-space justify="space-between" align="center">
          <n-space>
            <n-tag :type="store.connected ? 'success' : 'error'">{{ store.connected ? '已连接' : '未连接' }}</n-tag>
            <n-tag type="info">{{ phaseLabel[currentPhase] || currentPhase }}</n-tag>
          </n-space>
          <n-space>
            <n-button v-if="store.sessionEnded" size="small" @click="router.push('/')">返回首页</n-button>
          </n-space>
        </n-space>
      </n-card>

      <n-alert v-if="store.sessionError" type="error" :title="store.sessionError" style="margin-top: 12px" />

      <!-- Standalone incomplete: "继续创作" call-to-action when no session -->
      <n-card v-if="isStandalone && isIncomplete && !hasSession" size="small" class="cta-card">
        <n-space justify="space-between" align="center">
          <n-text>小说尚未完成，可以继续创作</n-text>
          <n-button type="primary" @click="startContinue">继续创作</n-button>
        </n-space>
      </n-card>

      <n-grid :cols="24" :x-gap="16" style="margin-top: 12px">
        <!-- Left: Tabs -->
        <n-gi :span="hasSession ? 14 : 24">
          <n-tabs v-model:value="activeTab" type="line" animated>
        <n-tab-pane name="styling" :tab="phaseLabel.styling" :disabled="phaseState('styling') === 'future'">
          <n-card v-if="phaseState('styling') !== 'future' && detail?.style_guide" size="small">
            <n-text v-if="detail.style_description" depth="3" style="margin-bottom: 8px; display: block;">{{ detail.style_description }}</n-text>
            <JsonViewer :data="detail.style_guide" type="style" />
          </n-card>
          <n-text v-else-if="phaseState('styling') === 'current' && hasSession" depth="3" class="tab-placeholder">进行中...</n-text>
          <n-text v-else depth="3" class="tab-placeholder">此阶段尚未开始</n-text>
        </n-tab-pane>

        <n-tab-pane name="collecting_params" :tab="phaseLabel.collecting_params" :disabled="phaseState('collecting_params') === 'future'">
          <n-card v-if="phaseState('collecting_params') !== 'future' && detail?.novel_params" size="small">
            <n-descriptions bordered :column="2">
              <n-descriptions-item label="总章数">{{ detail.total_chapters || '?' }}</n-descriptions-item>
              <n-descriptions-item label="进度">{{ detail.current_chapter }} / {{ detail.total_chapters || '?' }} 章</n-descriptions-item>
              <n-descriptions-item label="每章字数">
                {{ detail.novel_params.words_per_chapter?.min }} - {{ detail.novel_params.words_per_chapter?.max }}
              </n-descriptions-item>
            </n-descriptions>
            <ParamTable v-if="lastParamSuggestions" :data="lastParamSuggestions" style="margin-top: 12px" />
          </n-card>
          <n-text v-else-if="phaseState('collecting_params') === 'current' && hasSession" depth="3" class="tab-placeholder">进行中...</n-text>
          <n-text v-else depth="3" class="tab-placeholder">此阶段尚未开始</n-text>
        </n-tab-pane>

        <n-tab-pane name="directing" :tab="phaseLabel.directing" :disabled="phaseState('directing') === 'future'">
          <n-card v-if="phaseState('directing') !== 'future' && (detail?.world_data || detail?.outline)" size="small">
            <template v-if="detail.world_data">
              <n-text depth="3" class="jv-section-title">世界观</n-text>
              <JsonViewer :data="detail.world_data" type="world" />
            </template>
            <template v-if="detail.outline" style="margin-top: 16px">
              <n-text depth="3" class="jv-section-title">大纲</n-text>
              <JsonViewer :data="detail.outline" type="outline" />
            </template>
          </n-card>
          <n-text v-else-if="phaseState('directing') === 'current' && hasSession" depth="3" class="tab-placeholder">进行中...</n-text>
          <n-text v-else depth="3" class="tab-placeholder">此阶段尚未开始</n-text>
        </n-tab-pane>

        <n-tab-pane name="plotting" :tab="phaseLabel.plotting" :disabled="phaseState('plotting') === 'future'">
          <n-card v-if="phaseState('plotting') !== 'future' && detail?.chapters?.length" size="small">
            <template v-if="groupedChapters">
              <div v-for="vol in groupedChapters" :key="vol.number">
                <n-divider>卷{{ vol.number }} {{ vol.title }}</n-divider>
                <n-list bordered>
                  <n-list-item v-for="ch in vol.chapters" :key="ch.number">
                    <n-thing>
                      <template #header>第{{ ch.number }}章 {{ ch.title }}</template>
                    </n-thing>
                  </n-list-item>
                </n-list>
              </div>
            </template>
            <n-list v-else bordered>
              <n-list-item v-for="ch in detail.chapters" :key="ch.number">
                <n-thing>
                  <template #header>第{{ ch.number }}章 {{ ch.title }}</template>
                </n-thing>
              </n-list-item>
            </n-list>
          </n-card>
          <n-text v-else-if="phaseState('plotting') === 'current' && hasSession" depth="3" class="tab-placeholder">进行中...</n-text>
          <n-text v-else depth="3" class="tab-placeholder">此阶段尚未开始</n-text>
        </n-tab-pane>

        <n-tab-pane name="writing" :tab="phaseLabel.writing" :disabled="phaseState('writing') === 'future'">
          <n-card v-if="phaseState('writing') !== 'future' && detail?.chapters?.length" size="small">
            <template v-if="groupedChapters">
              <div v-for="vol in groupedChapters" :key="vol.number">
                <n-divider>卷{{ vol.number }} {{ vol.title }}</n-divider>
                <n-list bordered>
                  <n-list-item v-for="ch in vol.chapters" :key="ch.number">
                    <n-thing>
                      <template #header>第{{ ch.number }}章 {{ ch.title }}</template>
                      <template #description>
                        <n-space align="center" :size="4">
                          <template v-for="(s, i) in chapterStepState(ch)" :key="i">
                            <n-tag size="tiny" :type="s.done ? 'success' : 'default'" :bordered="!s.done" round>
                              {{ s.done ? STEP_LABELS[s.step] + '✓' : STEP_LABELS[s.step] }}
                            </n-tag>
                            <span v-if="i < STAGE_STEPS.length - 1" class="step-arrow">→</span>
                          </template>
                          <n-tag v-if="ch.revision_count > 0" size="tiny" type="warning" round>重写{{ ch.revision_count }}次</n-tag>
                        </n-space>
                      </template>
                    </n-thing>
                  </n-list-item>
                </n-list>
              </div>
            </template>
            <n-list v-else bordered>
              <n-list-item v-for="ch in detail.chapters" :key="ch.number">
                <n-thing>
                  <template #header>第{{ ch.number }}章 {{ ch.title }}</template>
                  <template #description>
                    <n-space align="center" :size="4">
                      <template v-for="(s, i) in chapterStepState(ch)" :key="i">
                        <n-tag size="tiny" :type="s.done ? 'success' : 'default'" :bordered="!s.done" round>
                          {{ s.done ? STEP_LABELS[s.step] + '✓' : STEP_LABELS[s.step] }}
                        </n-tag>
                        <span v-if="i < STAGE_STEPS.length - 1" class="step-arrow">→</span>
                      </template>
                      <n-tag v-if="ch.revision_count > 0" size="tiny" type="warning" round>重写{{ ch.revision_count }}次</n-tag>
                    </n-space>
                  </template>
                </n-thing>
              </n-list-item>
            </n-list>
          </n-card>
          <n-text v-else-if="phaseState('writing') === 'current' && hasSession" depth="3" class="tab-placeholder">进行中...</n-text>
          <n-text v-else depth="3" class="tab-placeholder">此阶段尚未开始</n-text>
        </n-tab-pane>

        <!-- 完成 Tab: success message + chapter list with revise actions -->
        <n-tab-pane name="complete" :tab="phaseLabel.complete" :disabled="phaseState('complete') === 'future'">
          <n-card v-if="phaseState('complete') !== 'future'" size="small">
            <n-result status="success" title="创作完成" :description="`共 ${(detail?.total_chapters || '?')} 章已全部完成`" />
            <template v-if="detail?.chapters?.length">
              <template v-if="groupedChapters">
                <div v-for="vol in groupedChapters" :key="vol.number">
                  <n-divider>卷{{ vol.number }} {{ vol.title }}</n-divider>
                  <n-list bordered>
                    <n-list-item v-for="ch in vol.chapters" :key="ch.number">
                      <n-thing>
                        <template #header>第{{ ch.number }}章 {{ ch.title }}</template>
                        <template #action>
                          <n-button size="small" @click="startRevise(ch.number)">修订</n-button>
                        </template>
                      </n-thing>
                    </n-list-item>
                  </n-list>
                </div>
              </template>
              <n-list v-else bordered style="margin-top: 12px">
                <n-list-item v-for="ch in detail.chapters" :key="ch.number">
                  <n-thing>
                    <template #header>第{{ ch.number }}章 {{ ch.title }}</template>
                    <template #action>
                      <n-button size="small" @click="startRevise(ch.number)">修订</n-button>
                    </template>
                  </n-thing>
                </n-list-item>
              </n-list>
            </template>
          </n-card>
          <n-text v-else depth="3" class="tab-placeholder">尚未完成</n-text>
        </n-tab-pane>
          </n-tabs>
        </n-gi>

        <!-- Right: Live session panel -->
        <n-gi v-if="hasSession" :span="10">
          <n-space vertical size="small">
            <ProgressBar />
            <n-card title="实时日志" size="small">
              <MessageLog :messages="displayMessages" />
            </n-card>
            <InputDispatcher
              v-if="store.pendingInput"
              :request="store.pendingInput as InputRequest"
              @respond="handleRespond"
            />
            <n-result v-if="store.sessionEnded" status="info" :title="sessionEndTitle">
              <template #footer>
                <n-space>
                  <n-button v-if="isIncomplete" type="primary" @click="startContinue">继续创作</n-button>
                  <n-button @click="router.push('/')">返回首页</n-button>
                </n-space>
              </template>
            </n-result>
          </n-space>
        </n-gi>
      </n-grid>

      <n-empty v-if="isStandalone && !loading && !detail" description="未找到小说信息" style="margin-top: 24px" />
    </n-spin>
  </div>
</template>

<style scoped>
.novel-detail { padding-top: 8px; }
.tab-placeholder { display: block; padding: 24px; text-align: center; }
.step-arrow { color: rgba(255,255,255,0.25); font-size: 12px; }
.status-bar { margin-top: 8px; }
.cta-card { margin-top: 12px; }
</style>

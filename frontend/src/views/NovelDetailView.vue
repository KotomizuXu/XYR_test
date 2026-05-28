<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useNovelStore, type InputRequest } from '../store'
import MessageLog from '../components/display/MessageLog.vue'
import InputDispatcher from '../components/interaction/InputDispatcher.vue'
import ParamTable from '../components/display/ParamTable.vue'
import ProgressBar from '../components/display/ProgressBar.vue'
import JsonViewer from '../components/display/JsonViewer.vue'
import RefineBlockViewer from '../components/display/RefineBlockViewer.vue'
import BatchAuditView from '../components/display/BatchAuditView.vue'
import GlobalAuditView from '../components/display/GlobalAuditView.vue'

const store = useNovelStore()
const route = useRoute()
const router = useRouter()

const props = defineProps<{ novelName?: string }>()

const isStandalone = computed(() => !!route.params.name)
const detail = ref<any>(null)
const loading = ref(false)
const activeTab = ref('styling')
const refreshing = ref(false)

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
    chapters: mergedChapters.value.filter(
      (ch: any) => ch.number >= vol.start_chapter && ch.number <= vol.end_chapter
    ),
  }))
})

const mergedChapters = computed(() => {
  const chapters = detail.value?.chapters || []
  const plans = detail.value?.chapter_plans || []
  const planMap = new Map(plans.map((p: any) => [p.chapter_number, p]))
  return chapters.map((ch: any) => {
    const plan = planMap.get(ch.number)
    return plan ? { ...ch, plan } : { ...ch }
  })
})

const auditByChapter = computed(() => {
  const audits = detail.value?.chapter_audits || []
  const map = new Map<number, any>()
  for (const a of audits) {
    map.set(a.chapter_number, a)
  }
  return map
})

// Drawer for chapter content
const showDrawer = ref(false)
const drawerChapter = ref<any>(null)
const drawerContent = ref('')
const drawerLoading = ref(false)

async function openChapterContent(ch: any) {
  const name = isStandalone.value
    ? (route.params.name as string)
    : props.novelName || null
  if (!name) return
  drawerChapter.value = ch
  drawerContent.value = ''
  drawerLoading.value = true
  showDrawer.value = true
  try {
    const res = await fetch(`/api/novels/${encodeURIComponent(name)}/chapter/${ch.number}`)
    if (res.ok) {
      const data = await res.json()
      drawerContent.value = data.content || '（暂无内容）'
    } else {
      drawerContent.value = '（加载失败）'
    }
  } catch {
    drawerContent.value = '（加载失败）'
  } finally {
    drawerLoading.value = false
  }
}

const rollbackLoading = ref<string | null>(null)

async function rollbackToPhase(targetPhase: string) {
  const name = isStandalone.value
    ? (route.params.name as string)
    : props.novelName || null
  if (!name) return
  rollbackLoading.value = targetPhase
  try {
    const res = await fetch(`/api/novels/${encodeURIComponent(name)}/rollback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_phase: targetPhase }),
    })
    const data = await res.json()
    if (data.ok) {
      await fetchDetail()
    } else {
      window.alert(data.error || '回滚失败')
    }
  } catch {
    window.alert('回滚请求失败')
  } finally {
    rollbackLoading.value = null
  }
}

const TENSION_MAP: Record<string, { label: string; type: 'error' | 'warning' | 'info' }> = {
  high: { label: '高', type: 'error' },
  medium: { label: '中', type: 'warning' },
  low: { label: '低', type: 'info' },
}

const EMOTION_MAP: Record<string, { label: string; color: string }> = {
  pleasure: { label: '愉悦', color: '#36ad6a' },
  pain: { label: '痛苦', color: '#e88080' },
  suspense: { label: '悬疑', color: '#f0a020' },
  calm: { label: '平静', color: '#70c0e8' },
}

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

async function handleRefresh() {
  refreshing.value = true
  await fetchDetail()
  refreshing.value = false
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

// Standalone mode: start polling when a session becomes active
watch(hasSession, (active) => {
  if (active && !refreshTimer) {
    refreshTimer = setInterval(fetchDetail, 5000)
  }
})

const displayMessages = computed(() =>
  store.outputMessages.filter(m => !['param_suggestions', 'novel_list'].includes(m.data.kind))
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

// Refresh Tab data immediately when a refine_block message arrives via WebSocket,
// instead of waiting for the 5-second polling interval.
watch(() => store.messages.length, () => {
  const last = store.messages[store.messages.length - 1]
  if (last?.type === 'output' && last.data?.kind === 'refine_block') {
    fetchDetail()
  }
})

// Combine world_data + outline for RefineBlockViewer sub-tabs in the directing Tab
const directingContent = computed(() => {
  const wd = detail.value?.world_data
  const outline = detail.value?.outline
  if (!wd && !outline) return null
  const result: any = {}
  if (wd) {
    const { characters, locations, world, style, ...rest } = wd
    // LLM 可能在 world_data 内嵌套 world 对象，展平到顶层
    const flat = world && typeof world === 'object' ? { ...world, ...rest } : { ...rest }
    result.world_data = flat
    if (characters) result.characters = characters
    if (locations) result.locations = locations
    if (style) result.style = style
  }
  if (outline) result.outline = outline
  return result
})
</script>

<template>
  <div class="novel-detail">
    <n-spin :show="isStandalone && loading">
      <!-- Standalone header: title only -->
      <n-page-header v-if="isStandalone && detail" @back="router.push('/')">
        <template #title>《{{ detail.name }}》</template>
      </n-page-header>

      <!-- Session status bar: show whenever there's an active session -->
      <n-card v-if="hasSession" size="small" class="status-bar">
        <n-space justify="space-between" align="center">
          <n-space>
            <n-tag :type="store.connected ? 'success' : 'error'">{{ store.connected ? '已连接' : '未连接' }}</n-tag>
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
          <n-card v-if="phaseState('styling') !== 'future' && detail?.style_guide" size="small" :title="phaseLabel.styling">
            <template #header-extra>
              <n-button size="small" @click="handleRefresh" :loading="refreshing">刷新数据</n-button>
            </template>
            <n-text v-if="detail.style_description" depth="3" style="margin-bottom: 8px; display: block;">{{ detail.style_description }}</n-text>
            <JsonViewer :data="detail.style_guide" type="style" />
          </n-card>
          <n-text v-else-if="phaseState('styling') === 'current' && hasSession" depth="3" class="tab-placeholder">进行中...</n-text>
          <n-text v-else depth="3" class="tab-placeholder">此阶段尚未开始</n-text>
        </n-tab-pane>

        <n-tab-pane name="collecting_params" :tab="phaseLabel.collecting_params" :disabled="phaseState('collecting_params') === 'future'">
          <n-card v-if="phaseState('collecting_params') !== 'future' && detail?.novel_params" size="small" :title="phaseLabel.collecting_params">
            <template #header-extra>
              <n-space>
                <n-button size="small" @click="handleRefresh" :loading="refreshing">刷新数据</n-button>
                <template v-if="phaseState('collecting_params') === 'past'">
                  <n-popconfirm @positive-click="rollbackToPhase('collecting_params')">
                    <template #trigger>
                      <n-button size="small" type="warning" :loading="rollbackLoading === 'collecting_params'" :disabled="hasSession">回滚到此阶段</n-button>
                    </template>
                    回滚将清除此后所有阶段的数据（导演、剧情、正文等），确定继续？
                  </n-popconfirm>
                </template>
              </n-space>
            </template>
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
          <n-card v-if="phaseState('directing') !== 'future' && (detail?.world_data || detail?.outline)" size="small" :title="phaseLabel.directing">
            <template #header-extra>
              <n-space>
                <n-button size="small" @click="handleRefresh" :loading="refreshing">刷新数据</n-button>
                <template v-if="phaseState('directing') === 'past'">
                  <n-popconfirm @positive-click="rollbackToPhase('directing')">
                    <template #trigger>
                      <n-button size="small" type="warning" :loading="rollbackLoading === 'directing'" :disabled="hasSession">回滚到此阶段</n-button>
                    </template>
                    回滚将清除此后所有阶段的数据（剧情拆章、正文等），确定继续？
                  </n-popconfirm>
                </template>
              </n-space>
            </template>
            <RefineBlockViewer v-if="directingContent" :content="directingContent" :bare="true" />
          </n-card>
          <n-text v-else-if="phaseState('directing') === 'current' && hasSession" depth="3" class="tab-placeholder">进行中...</n-text>
          <n-text v-else depth="3" class="tab-placeholder">此阶段尚未开始</n-text>
        </n-tab-pane>

        <n-tab-pane name="plotting" :tab="phaseLabel.plotting" :disabled="phaseState('plotting') === 'future'">
          <template v-if="phaseState('plotting') !== 'future' && detail?.chapters?.length">
            <!-- Refresh + rollback buttons -->
            <n-space justify="end" style="margin-bottom: 8px">
              <n-button size="small" @click="handleRefresh" :loading="refreshing">刷新数据</n-button>
              <n-popconfirm v-if="phaseState('plotting') === 'past'" @positive-click="rollbackToPhase('plotting')">
                <template #trigger>
                  <n-button size="small" type="warning" :loading="rollbackLoading === 'plotting'" :disabled="hasSession">回滚到此阶段</n-button>
                </template>
                回滚将清除此后所有阶段的数据（正文、追踪等），确定继续？
              </n-popconfirm>
            </n-space>
            <!-- 大纲查看入口（复用 directing Tab 的 RefineBlockViewer 渲染 outline）-->
            <n-collapse v-if="detail?.outline" style="margin-bottom: 12px">
              <n-collapse-item title="📖 查看大纲" name="outline">
                <RefineBlockViewer :content="{ outline: detail.outline }" :bare="true" />
              </n-collapse-item>
            </n-collapse>
            <!-- Has chapter_plans: show full outline -->
            <template v-if="detail.chapter_plans?.length">
              <template v-if="groupedChapters">
                <n-divider v-for="vol in groupedChapters" :key="vol.number">卷{{ vol.number }} {{ vol.title }}</n-divider>
              </template>
              <n-card v-for="ch in (groupedChapters ? groupedChapters.flatMap((v: any) => v.chapters) : mergedChapters)" :key="ch.number" size="small" style="margin-bottom: 12px">
                <template #header>
                  <n-space align="center" :size="8">
                    <span>第{{ ch.number }}章 {{ ch.title }}</span>
                    <n-tag v-if="ch.plan?.act" size="tiny" round>{{ ch.plan.act }}</n-tag>
                    <n-tag v-if="ch.plan?.tension_level" size="tiny" :type="TENSION_MAP[ch.plan.tension_level]?.type || 'default'" round>张力 {{ TENSION_MAP[ch.plan.tension_level]?.label || ch.plan.tension_level }}</n-tag>
                  </n-space>
                </template>
                <template v-if="ch.plan" #header-extra>
                  <n-button size="small" quaternary @click="openChapterContent(ch)" :disabled="!ch.has_edited && !ch.has_draft">阅读正文</n-button>
                </template>
                <template v-if="ch.plan">
                  <n-text v-if="ch.plan.summary" style="display:block;margin-bottom:12px;font-size:14px;line-height:1.8">{{ ch.plan.summary }}</n-text>
                  <n-descriptions bordered :column="2" label-placement="left" size="small">
                    <n-descriptions-item v-if="ch.plan.emotional_arc" label="情绪曲线">{{ ch.plan.emotional_arc }}</n-descriptions-item>
                    <n-descriptions-item v-if="ch.plan.emotional_type" label="情绪类型">
                      <n-tag size="tiny" :color="{ color: EMOTION_MAP[ch.plan.emotional_type]?.color || '#666', textColor: '#fff' }" round>{{ EMOTION_MAP[ch.plan.emotional_type]?.label || ch.plan.emotional_type }}</n-tag>
                    </n-descriptions-item>
                    <n-descriptions-item v-if="ch.plan.emotional_intensity" label="情绪强度">{{ ch.plan.emotional_intensity }}</n-descriptions-item>
                    <n-descriptions-item v-if="ch.plan.location" label="地点">{{ ch.plan.location }}</n-descriptions-item>
                    <n-descriptions-item v-if="ch.plan.time" label="时间">{{ ch.plan.time }}</n-descriptions-item>
                    <n-descriptions-item v-if="ch.plan.duration" label="时长">{{ ch.plan.duration }}</n-descriptions-item>
                    <n-descriptions-item v-if="ch.plan.opening_hook_type" label="开头钩子">{{ ch.plan.opening_hook_type }}</n-descriptions-item>
                    <n-descriptions-item v-if="ch.plan.ending_hook_type" label="结尾钩子">{{ ch.plan.ending_hook_type }}</n-descriptions-item>
                  </n-descriptions>
                  <n-collapse style="margin-top: 8px">
                    <n-collapse-item title="场景结构" name="scene_structure">
                      <n-text v-if="ch.plan.scene_structure" style="white-space:pre-wrap">{{ ch.plan.scene_structure }}</n-text>
                      <n-descriptions v-if="ch.plan.scene_list?.length" bordered :column="1" label-placement="left" size="small" style="margin-top:8px">
                        <n-descriptions-item v-for="(s, i) in ch.plan.scene_list" :key="i" :label="s.name">
                          {{ s.location }} — {{ s.purpose }}
                        </n-descriptions-item>
                      </n-descriptions>
                    </n-collapse-item>
                    <n-collapse-item title="情节点" name="plot_points">
                      <n-list size="small" bordered>
                        <n-list-item v-for="(pp, i) in (ch.plan.plot_points || [])" :key="i">{{ pp }}</n-list-item>
                      </n-list>
                    </n-collapse-item>
                    <n-collapse-item title="角色" name="characters">
                      <n-space vertical size="small">
                        <div v-if="ch.plan.characters_on_stage?.length">
                          <n-text depth="3" style="font-size:12px">出场角色：</n-text>
                          <n-tag v-for="c in ch.plan.characters_on_stage" :key="c" size="tiny" round style="margin:2px">{{ c }}</n-tag>
                        </div>
                        <div v-if="ch.plan.characters_involved?.length">
                          <n-text depth="3" style="font-size:12px">涉及角色：</n-text>
                          <n-tag v-for="c in ch.plan.characters_involved" :key="c" size="tiny" round type="info" style="margin:2px">{{ c }}</n-tag>
                        </div>
                      </n-space>
                    </n-collapse-item>
                    <n-collapse-item v-if="ch.plan.cliffhanger" title="悬念" name="cliffhanger">
                      <n-text>{{ ch.plan.cliffhanger }}</n-text>
                    </n-collapse-item>
                    <n-collapse-item v-if="ch.plan.previous_link" title="前后衔接" name="previous_link">
                      <n-text>{{ ch.plan.previous_link }}</n-text>
                    </n-collapse-item>
                    <n-collapse-item v-if="ch.plan.foreshadowing?.length" title="伏笔" name="foreshadowing">
                      <n-list size="small" bordered>
                        <n-list-item v-for="(f, i) in ch.plan.foreshadowing" :key="i">
                          <n-thing>
                            <template #header>{{ f.content }}</template>
                            <template #description>
                              <n-space :size="4">
                                <n-tag size="tiny" round>可见度: {{ f.visibility }}</n-tag>
                                <n-tag v-if="f.planned_reveal" size="tiny" round type="info">计划揭示: 第{{ f.planned_reveal }}章</n-tag>
                              </n-space>
                            </template>
                          </n-thing>
                        </n-list-item>
                      </n-list>
                    </n-collapse-item>
                    <n-collapse-item v-if="ch.plan.active_plotlines?.length" title="活跃主线" name="plotlines">
                      <n-tag v-for="pl in ch.plan.active_plotlines" :key="pl" size="small" style="margin:2px">{{ pl }}</n-tag>
                    </n-collapse-item>
                    <n-collapse-item v-if="auditByChapter.get(ch.number)" title="🔍 审计结果" name="audit">
                      <template v-if="auditByChapter.get(ch.number)">
                        <n-space align="center" :size="8" style="margin-bottom:8px">
                          <n-tag :type="auditByChapter.get(ch.number).approved ? 'success' : 'error'" size="small">
                            {{ auditByChapter.get(ch.number).approved ? '✅ 通过' : '❌ 打回' }}
                          </n-tag>
                          <n-tag size="small">{{ auditByChapter.get(ch.number).total_quality }}/50</n-tag>
                        </n-space>
                        <!-- 能力矩阵摘要 -->
                        <div v-if="Object.keys(auditByChapter.get(ch.number).capability_manifest || {}).length" style="margin-bottom:8px">
                          <n-text depth="3" style="font-size:12px">角色能力表现：</n-text>
                          <div v-for="(charCaps, charName) in auditByChapter.get(ch.number).capability_manifest" :key="charName" style="margin-top:4px">
                            <n-text style="font-size:12px;font-weight:700">{{ charName }}：</n-text>
                            <n-tag v-for="(cap, capName) in charCaps" :key="capName" size="tiny"
                              :type="cap.status === 'major' ? 'error' : cap.status === 'warning' ? 'warning' : 'success'"
                              style="margin:2px">
                              {{ capName }}: {{ cap.setting }}→{{ cap.actual }}
                            </n-tag>
                          </div>
                        </div>
                        <!-- 问题摘要 -->
                        <div v-if="auditByChapter.get(ch.number).issues?.length">
                          <n-text depth="3" style="font-size:12px">问题 ({{ auditByChapter.get(ch.number).issues.length }})：</n-text>
                          <div v-for="(issue, idx) in auditByChapter.get(ch.number).issues" :key="idx" style="font-size:12px;margin-top:2px">
                            <n-tag :type="issue.severity === 'major' ? 'error' : issue.severity === 'warning' ? 'warning' : 'info'" size="tiny">{{ issue.severity }}</n-tag>
                            {{ issue.detail }}
                          </div>
                        </div>
                      </template>
                    </n-collapse-item>
                  </n-collapse>
                </template>
              </n-card>
            </template>
            <!-- No chapter_plans: fallback to title list -->
            <n-card v-else size="small">
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
            <!-- 批次审计 + 全局审计持久化展示 -->
            <n-collapse v-if="(detail?.batch_audits?.length || detail?.global_audit)" style="margin-top: 12px">
              <n-collapse-item v-if="detail?.batch_audits?.length" title="📊 批次审计汇总" name="batch_audits">
                <BatchAuditView v-for="(b, idx) in detail.batch_audits" :key="idx" :data="b" />
              </n-collapse-item>
              <n-collapse-item v-if="detail?.global_audit" title="📋 全书完整性报告" name="global_audit">
                <GlobalAuditView :data="detail.global_audit" />
              </n-collapse-item>
            </n-collapse>
          </template>
          <n-text v-else-if="phaseState('plotting') === 'current' && hasSession" depth="3" class="tab-placeholder">进行中...</n-text>
          <n-text v-else depth="3" class="tab-placeholder">此阶段尚未开始</n-text>
        </n-tab-pane>

        <n-tab-pane name="writing" :tab="phaseLabel.writing" :disabled="phaseState('writing') === 'future'">
          <n-card v-if="phaseState('writing') !== 'future' && detail?.chapters?.length" size="small" :title="phaseLabel.writing">
            <template #header-extra>
              <n-space>
                <n-button size="small" @click="handleRefresh" :loading="refreshing">刷新数据</n-button>
                <template v-if="phaseState('writing') === 'past'">
                  <n-popconfirm @positive-click="rollbackToPhase('writing')">
                    <template #trigger>
                      <n-button size="small" type="warning" :loading="rollbackLoading === 'writing'" :disabled="hasSession">回滚到此阶段</n-button>
                    </template>
                    回滚将清除所有章节内容和追踪数据，重新开始写作，确定继续？
                  </n-popconfirm>
                </template>
              </n-space>
            </template>
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
                      <template #action>
                        <n-button size="small" @click="openChapterContent(ch)" :disabled="!ch.has_edited && !ch.has_draft">阅读</n-button>
                      </template>
                    </n-thing>
                  </n-list-item>
                </n-list>
              </div>
            </template>
            <n-list v-else bordered>
              <n-list-item v-for="ch in mergedChapters" :key="ch.number">
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
                  <template #action>
                    <n-button size="small" @click="openChapterContent(ch)" :disabled="!ch.has_edited && !ch.has_draft">阅读</n-button>
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
                          <n-space>
                            <n-button size="small" @click="openChapterContent(ch)">阅读</n-button>
                            <n-button size="small" @click="startRevise(ch.number)">修订</n-button>
                          </n-space>
                        </template>
                      </n-thing>
                    </n-list-item>
                  </n-list>
                </div>
              </template>
              <n-list v-else bordered style="margin-top: 12px">
                <n-list-item v-for="ch in mergedChapters" :key="ch.number">
                  <n-thing>
                    <template #header>第{{ ch.number }}章 {{ ch.title }}</template>
                    <template #action>
                      <n-space>
                        <n-button size="small" @click="openChapterContent(ch)">阅读</n-button>
                        <n-button size="small" @click="startRevise(ch.number)">修订</n-button>
                      </n-space>
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

    <!-- Chapter content drawer -->
    <n-drawer v-model:show="showDrawer" :width="640" placement="right">
      <n-drawer-content :title="drawerChapter ? `第${drawerChapter.number}章 ${drawerChapter.title}` : '加载中...'">
        <n-spin :show="drawerLoading">
          <div class="chapter-content">{{ drawerContent }}</div>
        </n-spin>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<style scoped>
.novel-detail { padding-top: 8px; }
.tab-placeholder { display: block; padding: 24px; text-align: center; }
.step-arrow { color: rgba(255,255,255,0.25); font-size: 12px; }
.status-bar { margin-top: 8px; }
.cta-card { margin-top: 12px; }
.chapter-content { white-space: pre-wrap; line-height: 1.9; font-size: 15px; }
</style>

<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import type { OutputMessage } from '../../store'
import RefineBlockViewer from './RefineBlockViewer.vue'
import BatchAuditView from './BatchAuditView.vue'
import GlobalAuditView from './GlobalAuditView.vue'

const props = defineProps<{ messages: OutputMessage[] }>()
const logRef = ref<HTMLElement | null>(null)

watch(() => props.messages.length, async () => {
  await nextTick()
  if (logRef.value) logRef.value.scrollTop = logRef.value.scrollHeight
})

const kindColor: Record<string, string> = {
  info: 'rgba(54,173,106,0.15)',
  success: 'rgba(54,173,106,0.25)',
  warn: 'rgba(208,160,0,0.15)',
  error: 'rgba(208,48,48,0.15)',
  hint: 'rgba(120,120,140,0.15)',
}

const kindBorder: Record<string, string> = {
  info: '#36ad6a',
  success: '#36ad6a',
  warn: '#d0a000',
  error: '#d03030',
  hint: '#78788c',
}

function severityColor(sev: string): string {
  if (sev === 'major') return '#d03030'
  if (sev === 'warning') return '#d0a000'
  return '#78788c'
}
function capStatusColor(status: string): string {
  if (status === 'major') return '#d03030'
  if (status === 'warning') return '#d0a000'
  return '#36ad6a'
}
function qualityColor(score: number): string {
  if (score >= 7) return '#36ad6a'
  if (score >= 5) return '#d0a000'
  return '#d03030'
}
</script>

<template>
  <div ref="logRef" class="message-log">
    <div v-for="(msg, i) in messages" :key="i">
      <!-- Simple text messages -->
      <div
        v-if="['info','success','warn','error','hint'].includes(msg.data.kind)"
        class="msg-item"
        :style="{ background: kindColor[msg.data.kind] || kindColor.info, borderLeftColor: kindBorder[msg.data.kind] || kindBorder.info }"
      >
        <span class="msg-badge" :style="{ color: kindBorder[msg.data.kind] }">{{ msg.data.kind }}</span>
        <span>{{ msg.data.message }}</span>
      </div>

      <!-- Banner -->
      <div v-else-if="msg.data.kind === 'banner'" class="msg-banner">
        <div class="banner-title">{{ msg.data.title }}</div>
        <div v-if="msg.data.subtitle" class="banner-sub">{{ msg.data.subtitle }}</div>
      </div>

      <!-- Section -->
      <div v-else-if="msg.data.kind === 'section'" class="msg-section">
        <h3>{{ msg.data.title }}</h3>
        <p v-if="msg.data.body">{{ msg.data.body }}</p>
      </div>

      <!-- Divider -->
      <div v-else-if="msg.data.kind === 'divider'" class="msg-divider">
        {{ msg.data.label }}
      </div>

      <!-- Progress -->
      <div v-else-if="msg.data.kind === 'progress'" class="msg-progress">
        <n-progress
          type="line"
          :percentage="msg.data.total ? Math.round((msg.data.current / msg.data.total) * 100) : 0"
          :indicator-placement="'inside'"
        />
        <span class="progress-label">{{ msg.data.label }} ({{ msg.data.current }}/{{ msg.data.total }})</span>
      </div>

      <!-- Completion -->
      <div v-else-if="msg.data.kind === 'completion'" class="msg-completion">
        <n-icon size="32" color="#36ad6a"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg></n-icon>
        <div>
          <h3>创作完成！</h3>
          <p>《{{ msg.data.novel_name }}》已保存至 {{ msg.data.final_dir }}</p>
        </div>
      </div>

      <!-- Braindump intro -->
      <div v-else-if="msg.data.kind === 'braindump_intro'" class="msg-braindump-intro">
        <h3>立项问答</h3>
        <n-descriptions bordered :column="1" size="small">
          <n-descriptions-item label="灵感">{{ msg.data.idea }}</n-descriptions-item>
          <n-descriptions-item label="名称">{{ msg.data.name }}</n-descriptions-item>
          <n-descriptions-item v-if="msg.data.style" label="风格">{{ msg.data.style }}</n-descriptions-item>
        </n-descriptions>
      </div>

      <!-- Braindump result -->
      <div v-else-if="msg.data.kind === 'braindump_result'" class="msg-braindump-result">
        <div class="braindump-header">
          <span class="braindump-label">{{ msg.data.label }}</span>
          <n-tag v-if="msg.data.modified" size="tiny" type="warning">修改后</n-tag>
        </div>
        <div class="braindump-content">{{ msg.data.content }}</div>
      </div>

      <!-- Braindump summary -->
      <div v-else-if="msg.data.kind === 'braindump_summary'" class="msg-braindump-summary">
        <h3>立项问答汇总</h3>
        <div v-for="(pair, idx) in msg.data.parts" :key="idx" class="summary-item">
          <strong>{{ pair[0] }}</strong>
          <p>{{ pair[1] }}</p>
        </div>
      </div>

      <!-- Name candidates -->
      <div v-else-if="msg.data.kind === 'name_candidates'" class="msg-name-candidates">
        <h4>AI 推荐名称</h4>
        <n-space>
          <n-tag v-for="c in msg.data.candidates" :key="c" type="success">{{ c }}</n-tag>
        </n-space>
      </div>

      <!-- Param confirmed -->
      <div v-else-if="msg.data.kind === 'param_confirmed'" class="msg-param-confirmed">
        <h4>参数已确认</h4>
        <n-space>
          <n-tag>章数: {{ msg.data.total_chapters }}</n-tag>
          <n-tag>字数: {{ msg.data.words_min }}-{{ msg.data.words_max }}</n-tag>
        </n-space>
      </div>

      <!-- Refine block (inline in message log) -->
      <div v-else-if="msg.data.kind === 'refine_block'" class="msg-refine-block">
        <div class="refine-header">
          <span class="refine-label">{{ msg.data.label }}</span>
          <n-tag v-if="msg.data.modified" size="tiny" type="warning">修改后</n-tag>
        </div>
        <RefineBlockViewer :content="msg.data.content" :label="msg.data.label" />
      </div>

      <!-- Chapter Audit -->
      <div v-else-if="msg.data.kind === 'chapter_audit'" class="msg-chapter-audit">
        <div class="audit-header">
          <h3>第{{ msg.data.chapter_num }}章「{{ msg.data.title }}」审计</h3>
          <n-tag :type="msg.data.approved ? 'success' : 'error'" size="small">
            {{ msg.data.approved ? '✅ 通过' : '❌ 打回' }}
          </n-tag>
          <n-tag size="small">{{ msg.data.total_quality }}/50</n-tag>
        </div>
        <!-- 能力矩阵 -->
        <div v-if="Object.keys(msg.data.capability_manifest || {}).length" class="audit-section">
          <n-collapse>
            <n-collapse-item title="角色能力矩阵" name="cap">
              <div v-for="(charCaps, charName) in msg.data.capability_manifest" :key="charName" class="char-block">
                <strong class="char-name">{{ charName }}</strong>
                <div class="cap-grid">
                  <div v-for="(cap, capName) in charCaps" :key="capName" class="cap-cell" :style="{ borderLeftColor: capStatusColor(cap.status) }">
                    <span class="cap-name">{{ capName }}</span>
                    <span class="cap-scores">
                      {{ cap.setting }}→<strong :style="{ color: capStatusColor(cap.status) }">{{ cap.actual }}</strong>
                    </span>
                    <span v-if="cap.status !== 'pass'" class="cap-status" :style="{ color: capStatusColor(cap.status) }">{{ cap.status }}</span>
                  </div>
                </div>
              </div>
            </n-collapse-item>
          </n-collapse>
        </div>
        <!-- 质量评分 -->
        <div class="audit-section quality-section">
          <div v-for="(score, dim) in msg.data.quality_scores" :key="dim" class="quality-row">
            <span class="dim-label">{{ dim }}</span>
            <div class="quality-bar" :style="{ width: (score * 10) + '%', background: qualityColor(score) }"></div>
            <span class="score-val" :style="{ color: qualityColor(score) }">{{ score }}</span>
          </div>
        </div>
        <!-- 问题列表 -->
        <div v-if="msg.data.issues && msg.data.issues.length" class="audit-section">
          <div v-for="(issue, idx) in msg.data.issues" :key="idx" class="issue-item" :style="{ borderLeftColor: severityColor(issue.severity) }">
            <n-tag :bordered="false" size="tiny" :style="{ background: severityColor(issue.severity), color: '#fff' }">{{ issue.severity }}</n-tag>
            <span class="issue-type">{{ issue.type }}</span>
            <p class="issue-detail">{{ issue.detail }}</p>
            <p v-if="issue.suggestion" class="issue-suggestion">💡 {{ issue.suggestion }}</p>
          </div>
        </div>
      </div>

      <!-- Batch Audit -->
      <BatchAuditView v-else-if="msg.data.kind === 'batch_audit'" :data="msg.data" />

      <!-- Global Audit -->
      <GlobalAuditView v-else-if="msg.data.kind === 'global_audit'" :data="msg.data" />
    </div>
  </div>
</template>

<style scoped>
.message-log { max-height: 60vh; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 8px; }
.msg-item { padding: 8px 12px; border-radius: 8px; border-left: 3px solid; font-size: 14px; line-height: 1.6; }
.msg-badge { font-size: 11px; font-weight: 700; text-transform: uppercase; margin-right: 8px; }
.msg-banner { text-align: center; padding: 20px; border: 2px solid #36ad6a; border-radius: 12px; margin: 12px 0; background: rgba(54,173,106,0.08); }
.banner-title { font-size: 20px; font-weight: 700; color: #36ad6a; }
.banner-sub { font-size: 14px; color: rgba(255,255,255,0.6); margin-top: 4px; }
.msg-section { padding: 12px 16px; background: rgba(255,255,255,0.04); border-radius: 8px; margin: 8px 0; }
.msg-section h3 { font-size: 16px; color: #36ad6a; margin-bottom: 4px; }
.msg-divider { text-align: center; color: rgba(255,255,255,0.4); padding: 8px; border-bottom: 1px solid rgba(255,255,255,0.1); }
.msg-progress { padding: 8px 0; }
.progress-label { font-size: 13px; color: rgba(255,255,255,0.6); margin-top: 4px; }
.msg-completion { display: flex; align-items: center; gap: 12px; padding: 20px; background: rgba(54,173,106,0.12); border-radius: 12px; margin: 16px 0; }
.msg-completion h3 { font-size: 18px; color: #36ad6a; }
.msg-braindump-intro { padding: 12px; background: rgba(255,255,255,0.04); border-radius: 8px; }
.msg-braindump-intro h3 { color: #36ad6a; margin-bottom: 8px; }
.msg-braindump-result { padding: 12px; background: rgba(54,173,106,0.08); border: 1px solid rgba(54,173,106,0.2); border-radius: 8px; }
.braindump-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.braindump-label { font-weight: 700; color: #36ad6a; }
.braindump-content { white-space: pre-wrap; line-height: 1.7; font-size: 14px; max-height: 300px; overflow-y: auto; }
.msg-braindump-summary { padding: 12px; background: rgba(54,173,106,0.12); border-radius: 8px; }
.msg-braindump-summary h3 { color: #36ad6a; margin-bottom: 8px; }
.summary-item { margin-bottom: 8px; padding-bottom: 8px; border-bottom: 1px solid rgba(255,255,255,0.08); }
.summary-item strong { color: #5acea0; }
.summary-item p { font-size: 13px; color: rgba(255,255,255,0.7); margin-top: 4px; white-space: pre-wrap; }
.msg-name-candidates { padding: 8px 0; }
.msg-name-candidates h4 { margin-bottom: 8px; }
.msg-param-confirmed { padding: 8px 0; }
.msg-param-confirmed h4 { margin-bottom: 8px; }
.msg-refine-block { padding: 12px; background: rgba(255,255,255,0.03); border-radius: 8px; max-height: 400px; overflow-y: auto; }
.refine-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.refine-label { font-weight: 700; color: #5acea0; }

/* ── 大纲审计样式（chapter_audit；batch/global 已抽至独立子组件）── */
.msg-chapter-audit {
  padding: 16px; background: rgba(255,255,255,0.03); border: 1px solid rgba(54,173,106,0.2);
  border-radius: 12px; margin: 8px 0;
}
.msg-chapter-audit h3 {
  font-size: 16px; color: #36ad6a; margin-bottom: 12px;
}
.audit-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.audit-header h3 { margin-bottom: 0; }
.audit-section { margin-top: 12px; }
.audit-section h4 { font-size: 14px; color: rgba(255,255,255,0.8); margin-bottom: 8px; }

/* 角色能力矩阵 */
.char-block { margin-bottom: 12px; }
.char-name { display: block; color: #5acea0; margin-bottom: 6px; font-size: 14px; }
.cap-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 6px; }
.cap-cell {
  padding: 6px 10px; border-radius: 6px; border-left: 3px solid #36ad6a;
  background: rgba(255,255,255,0.04); display: flex; flex-wrap: wrap; align-items: center; gap: 4px 8px;
}
.cap-name { font-size: 13px; color: rgba(255,255,255,0.9); }
.cap-scores { font-size: 12px; color: rgba(255,255,255,0.6); }
.cap-status { font-size: 11px; font-weight: 700; }

/* 质量评分条 */
.quality-section { margin-top: 8px; }
.quality-row {
  display: flex; align-items: center; gap: 8px; margin-bottom: 4px; font-size: 13px;
}
.dim-label { width: 120px; color: rgba(255,255,255,0.7); text-transform: capitalize; }
.quality-bar { height: 8px; border-radius: 4px; transition: width 0.3s; }
.score-val { font-weight: 700; min-width: 24px; text-align: right; }

/* 问题列表 */
.issue-item {
  padding: 8px 12px; margin-bottom: 6px; border-radius: 6px; border-left: 3px solid;
  background: rgba(255,255,255,0.03);
}
.issue-type { font-size: 12px; color: rgba(255,255,255,0.5); margin-left: 8px; }
.issue-detail { font-size: 13px; color: rgba(255,255,255,0.8); margin: 4px 0 0; }
.issue-suggestion { font-size: 12px; color: #5acea0; margin: 4px 0 0; }
</style>

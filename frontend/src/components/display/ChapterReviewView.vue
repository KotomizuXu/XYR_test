<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ review: any }>()

const r = computed(() => props.review || {})

const DIM_LABELS: Record<string, string> = {
  opening_hook: '开头吸引力',
  plot_progression: '剧情推进',
  character_depth: '人物深度',
  dialogue_quality: '对话质量',
  ending_hook: '结尾悬念',
  pacing: '节奏控制',
  show_not_tell: '展示非陈述',
  language_quality: '语言质量',
}

const CONSISTENCY_KEYS: { key: string; label: string }[] = [
  { key: 'character_issues', label: '角色一致性' },
  { key: 'world_issues', label: '世界观一致性' },
  { key: 'timeline_issues', label: '时间线一致性' },
  { key: 'physical_traits_issues', label: '外貌特征' },
  { key: 'personality_issues', label: '性格行为' },
  { key: 'knowledge_state_issues', label: '知识状态' },
]

const TRACKING_SECTIONS: { key: string; label: string }[] = [
  { key: 'character_changes', label: '角色状态变化' },
  { key: 'relationship_changes', label: '关系变化' },
  { key: 'conflict_updates', label: '冲突更新' },
  { key: 'foreshadowing_updates', label: '伏笔更新' },
  { key: 'timeline_updates', label: '时间线标记' },
]

function qualityColor(s: number): string {
  if (s >= 7) return '#36ad6a'
  if (s >= 5) return '#d0a000'
  return '#d03030'
}

function severityColor(sev: string): string {
  if (sev === 'major') return '#d03030'
  if (sev === 'warning') return '#d0a000'
  return '#78788c'
}

const sortedIssues = computed(() => {
  const order: Record<string, number> = { major: 0, warning: 1, note: 2 }
  return [...(r.value.issues || [])].sort((a, b) => (order[a.severity] ?? 9) - (order[b.severity] ?? 9))
})

const breakdown = computed(() => r.value.quality_breakdown || {})

const hasTracking = computed(() => {
  const tu = r.value.tracking_updates
  if (!tu) return false
  return TRACKING_SECTIONS.some(s => {
    const v = tu[s.key]
    if (Array.isArray(v)) return v.length > 0
    if (typeof v === 'object' && v !== null) return Object.keys(v).some(k => Array.isArray(v[k]) ? v[k].length > 0 : true)
    return false
  })
})
</script>

<template>
  <div class="review-detail">
    <!-- 八维质量评分 -->
    <div v-if="breakdown.total !== undefined" class="review-section">
      <div class="section-title">八维质量评分</div>
      <div v-for="(label, dim) in DIM_LABELS" :key="dim" class="quality-row">
        <span class="dim-label">{{ label }}</span>
        <div class="quality-bar-bg">
          <div class="quality-bar" :style="{ width: ((breakdown[dim] || 0) / 10 * 100) + '%', background: qualityColor(breakdown[dim] || 0) }"></div>
        </div>
        <span class="score-val" :style="{ color: qualityColor(breakdown[dim] || 0) }">{{ breakdown[dim] ?? '-' }}</span>
      </div>
      <div class="quality-row total-row">
        <span class="dim-label">总分</span>
        <div class="quality-bar-bg">
          <div class="quality-bar" :style="{ width: (breakdown.total / 80 * 100) + '%', background: qualityColor(breakdown.total / 8) }"></div>
        </div>
        <span class="score-val" :style="{ color: qualityColor(breakdown.total / 8) }">{{ breakdown.total }}/80</span>
      </div>
    </div>

    <!-- 问题列表 -->
    <div v-if="sortedIssues.length" class="review-section">
      <div class="section-title">问题（{{ sortedIssues.length }}）</div>
      <div v-for="(issue, idx) in sortedIssues" :key="idx" class="issue-item" :style="{ borderLeftColor: severityColor(issue.severity) }">
        <div class="issue-header">
          <n-tag :bordered="false" size="tiny" :style="{ background: severityColor(issue.severity), color: '#fff' }">{{ issue.severity }}</n-tag>
          <span v-if="issue.type" class="issue-type">{{ issue.type }}</span>
        </div>
        <p class="issue-detail">{{ issue.description }}</p>
        <p v-if="issue.suggestion" class="issue-suggestion">{{ issue.suggestion }}</p>
        <p v-if="issue.location" class="issue-location">{{ issue.location }}</p>
      </div>
    </div>

    <!-- 一致性检查 -->
    <div v-if="r.consistency_checks" class="review-section">
      <div class="section-title">一致性检查</div>
      <n-collapse :default-expanded-names="[]">
        <n-collapse-item v-for="cs in CONSISTENCY_KEYS" :key="cs.key" :title="cs.label" :name="cs.key">
          <template #header-extra>
            <n-tag v-if="!r.consistency_checks[cs.key]?.length" size="tiny" type="success">无问题</n-tag>
            <n-tag v-else size="tiny" type="error">{{ r.consistency_checks[cs.key].length }} 项</n-tag>
          </template>
          <ul v-if="r.consistency_checks[cs.key]?.length" class="check-list">
            <li v-for="(item, i) in r.consistency_checks[cs.key]" :key="i">{{ item }}</li>
          </ul>
          <n-text v-else depth="3">无问题</n-text>
        </n-collapse-item>
      </n-collapse>
    </div>

    <!-- 亮点 -->
    <div v-if="r.strengths?.length" class="review-section">
      <div class="section-title">亮点</div>
      <n-space :size="6" :wrap="true">
        <n-tag v-for="(s, i) in r.strengths" :key="i" size="small" type="success" :bordered="false">{{ s }}</n-tag>
      </n-space>
    </div>

    <!-- 自动修复建议 -->
    <div v-if="r.auto_fix_suggestions?.length" class="review-section">
      <div class="section-title">自动修复建议</div>
      <div v-for="(fix, i) in r.auto_fix_suggestions" :key="i" class="fix-item">
        <n-tag size="tiny" :bordered="false">{{ fix.type }}</n-tag>
        <span class="fix-text">
          <span class="fix-old">{{ fix.original }}</span>
          <span class="fix-arrow"> → </span>
          <span class="fix-new">{{ fix.suggested }}</span>
        </span>
        <n-tag v-if="fix.confidence >= 0.9" size="tiny" type="success" :bordered="false">已自动应用</n-tag>
        <n-tag v-else size="tiny" type="default" :bordered="false">置信度 {{ (fix.confidence * 100).toFixed(0) }}%</n-tag>
      </div>
    </div>

    <!-- 追踪更新 -->
    <div v-if="hasTracking" class="review-section">
      <div class="section-title">追踪数据更新</div>
      <n-collapse :default-expanded-names="[]">
        <n-collapse-item v-for="ts in TRACKING_SECTIONS" :key="ts.key" :title="ts.label" :name="ts.key">
          <!-- 角色状态变化 -->
          <template v-if="ts.key === 'character_changes'">
            <div v-for="(c, i) in r.tracking_updates.character_changes" :key="i" class="track-item">
              <strong>{{ c.name }}</strong>
              <span class="track-field">{{ c.field }}</span>
              <span class="track-change">{{ c.old }} → {{ c.new }}</span>
              <span v-if="c.evidence" class="track-evidence">{{ c.evidence }}</span>
            </div>
          </template>
          <!-- 关系变化 -->
          <template v-else-if="ts.key === 'relationship_changes'">
            <div v-for="(rc, i) in r.tracking_updates.relationship_changes" :key="i" class="track-item">
              <strong>{{ rc.characters?.join(' ↔ ') }}</strong>
              <n-tag size="tiny" :bordered="false">{{ rc.type }}</n-tag>
              <span>{{ rc.change }}</span>
            </div>
          </template>
          <!-- 冲突/伏笔/时间线（结构不固定，直接 JSON 展示） -->
          <template v-else>
            <pre class="track-json">{{ JSON.stringify(r.tracking_updates[ts.key], null, 2) }}</pre>
          </template>
        </n-collapse-item>
      </n-collapse>
    </div>
  </div>
</template>

<style scoped>
.review-detail { display: flex; flex-direction: column; gap: 16px; }
.review-section { }
.section-title { font-size: 14px; font-weight: 600; color: #5acea0; margin-bottom: 8px; }

/* 八维质量评分 */
.quality-row { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; font-size: 13px; }
.dim-label { width: 100px; min-width: 100px; color: rgba(255,255,255,0.7); }
.quality-bar-bg { flex: 1; height: 8px; border-radius: 4px; background: rgba(255,255,255,0.08); }
.quality-bar { height: 100%; border-radius: 4px; transition: width 0.3s; }
.score-val { font-weight: 700; min-width: 40px; text-align: right; }
.total-row { margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.1); }
.total-row .dim-label { font-weight: 600; }

/* 问题列表 */
.issue-item {
  padding: 8px 12px; margin-bottom: 6px; border-radius: 6px; border-left: 3px solid;
  background: rgba(255,255,255,0.03);
}
.issue-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.issue-type { font-size: 12px; color: rgba(255,255,255,0.5); }
.issue-detail { font-size: 13px; color: rgba(255,255,255,0.8); margin: 0; }
.issue-suggestion { font-size: 12px; color: #5acea0; margin: 4px 0 0; }
.issue-location { font-size: 11px; color: rgba(255,255,255,0.4); margin: 2px 0 0; font-style: italic; }

/* 一致性检查 */
.check-list { margin: 0; padding-left: 20px; }
.check-list li { font-size: 13px; color: rgba(255,255,255,0.8); margin-bottom: 4px; }

/* 自动修复 */
.fix-item {
  display: flex; align-items: center; gap: 8px; padding: 6px 10px;
  background: rgba(255,255,255,0.03); border-radius: 6px; margin-bottom: 4px; font-size: 13px;
}
.fix-text { flex: 1; }
.fix-old { color: #d03030; }
.fix-arrow { color: rgba(255,255,255,0.4); }
.fix-new { color: #36ad6a; }

/* 追踪更新 */
.track-item {
  display: flex; align-items: baseline; gap: 8px; padding: 4px 0;
  font-size: 13px; color: rgba(255,255,255,0.8);
  border-bottom: 1px solid rgba(255,255,255,0.05);
}
.track-item:last-child { border-bottom: none; }
.track-field { color: #5acea0; font-size: 12px; }
.track-change { color: rgba(255,255,255,0.6); }
.track-evidence { color: rgba(255,255,255,0.4); font-size: 12px; font-style: italic; flex: 1; }
.track-json { font-size: 12px; color: rgba(255,255,255,0.7); background: rgba(255,255,255,0.03); padding: 8px; border-radius: 6px; margin: 0; white-space: pre-wrap; word-break: break-all; max-height: 300px; overflow-y: auto; }
</style>

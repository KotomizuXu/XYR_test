<script setup lang="ts">
defineProps<{ data: any }>()

function severityColor(sev: string): string {
  if (sev === 'major') return '#d03030'
  if (sev === 'warning') return '#d0a000'
  return '#78788c'
}
</script>

<template>
  <div class="msg-global-audit">
    <h3>📋 全书大纲完整性报告</h3>
    <!-- 覆盖率 -->
    <div v-if="data.coverage_rate" class="audit-section coverage-row">
      <div class="coverage-item">
        <div class="coverage-circle" :style="{ borderColor: data.coverage_rate.characters_pct >= 80 ? '#36ad6a' : '#d0a000' }">
          {{ data.coverage_rate.characters_pct }}%
        </div>
        <span>角色</span>
      </div>
      <div class="coverage-item">
        <div class="coverage-circle" :style="{ borderColor: data.coverage_rate.locations_pct >= 80 ? '#36ad6a' : '#d0a000' }">
          {{ data.coverage_rate.locations_pct }}%
        </div>
        <span>地点</span>
      </div>
      <div class="coverage-item">
        <div class="coverage-circle" :style="{ borderColor: data.coverage_rate.turning_points_pct >= 80 ? '#36ad6a' : '#d0a000' }">
          {{ data.coverage_rate.turning_points_pct }}%
        </div>
        <span>转折点</span>
      </div>
    </div>
    <!-- 完整性问题 -->
    <div v-if="data.completeness" class="audit-section">
      <div v-for="char in (data.completeness.unused_characters || [])" :key="char.name" class="forgotten-item warn">
        ⚠️ 角色「{{ char.name }}」全书未出场
      </div>
      <div v-for="loc in (data.completeness.unused_locations || [])" :key="loc.name" class="forgotten-item note">
        📝 地点「{{ loc.name }}」无章节使用
      </div>
      <div v-for="tp in (data.completeness.uncovered_turning_points || [])" :key="tp.turning_point" class="forgotten-item error">
        🔴 转折点「{{ tp.turning_point }}」无对应章节
      </div>
    </div>
    <!-- 跨批次问题 -->
    <div v-if="data.cross_batch_issues && data.cross_batch_issues.length" class="audit-section">
      <h4>跨批次一致性</h4>
      <div v-for="(issue, idx) in data.cross_batch_issues" :key="idx" class="issue-item" :style="{ borderLeftColor: severityColor(issue.severity) }">
        <n-tag :bordered="false" size="tiny" :style="{ background: severityColor(issue.severity), color: '#fff' }">{{ issue.severity }}</n-tag>
        <span>{{ issue.detail }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.msg-global-audit {
  padding: 16px; background: rgba(255,255,255,0.03); border: 1px solid rgba(54,173,106,0.2);
  border-radius: 12px; margin: 8px 0;
}
.msg-global-audit h3 { font-size: 16px; color: #36ad6a; margin-bottom: 12px; }
.audit-section { margin-top: 12px; }
.audit-section h4 { font-size: 14px; color: rgba(255,255,255,0.8); margin-bottom: 8px; }
.forgotten-item { padding: 6px 10px; margin-bottom: 4px; border-radius: 6px; font-size: 13px; }
.forgotten-item.warn { background: rgba(208,160,0,0.12); }
.forgotten-item.error { background: rgba(208,48,48,0.12); }
.forgotten-item.note { background: rgba(120,120,140,0.12); }
.issue-item {
  padding: 8px 12px; margin-bottom: 6px; border-radius: 6px; border-left: 3px solid;
  background: rgba(255,255,255,0.03);
}
.coverage-row { display: flex; gap: 24px; justify-content: center; }
.coverage-item { display: flex; flex-direction: column; align-items: center; gap: 4px; }
.coverage-circle {
  width: 64px; height: 64px; border-radius: 50%; border: 3px solid;
  display: flex; align-items: center; justify-content: center;
  font-size: 16px; font-weight: 700; color: rgba(255,255,255,0.9);
}
</style>

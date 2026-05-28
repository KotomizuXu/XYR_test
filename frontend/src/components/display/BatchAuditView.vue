<script setup lang="ts">
defineProps<{ data: any }>()
</script>

<template>
  <div class="msg-batch-audit">
    <h3>📊 批次审计 第{{ data.batch_range }}章</h3>
    <!-- 遗忘元素 -->
    <div class="audit-section">
      <h4>遗忘曲线检测</h4>
      <template v-if="data.forgotten_elements">
        <div v-for="char in (data.forgotten_elements.characters || [])" :key="char.name" class="forgotten-item warn">
          ⚠️ 角色「{{ char.name }}」已连续 {{ char.absent_chapters }} 章未出场（阈值 {{ char.threshold }}）
        </div>
        <div v-for="plot in (data.forgotten_elements.plotlines || [])" :key="plot.name" class="forgotten-item warn">
          ⚠️ 支线「{{ plot.name }}」已 {{ plot.stalled_chapters }} 章无进展
        </div>
        <div v-for="fs in (data.forgotten_elements.foreshadowing || [])" :key="fs.id" class="forgotten-item error">
          🔴 伏笔「{{ fs.content }}」超期 {{ fs.overdue_chapters }} 章未回收
        </div>
        <div v-if="!(data.forgotten_elements.characters || []).length && !(data.forgotten_elements.plotlines || []).length && !(data.forgotten_elements.foreshadowing || []).length" class="no-issues">✅ 无遗忘元素</div>
      </template>
      <div v-else class="no-issues">✅ 无遗忘元素</div>
    </div>
    <!-- 节奏曲线 -->
    <div v-if="data.pacing_curve && data.pacing_curve.tension_sequence" class="audit-section">
      <h4>节奏曲线</h4>
      <div class="pacing-chart">
        <div v-for="(t, idx) in data.pacing_curve.tension_sequence" :key="idx" class="tension-col">
          <div class="tension-bar" :class="t" :style="{ height: t === 'high' ? '60px' : t === 'medium' ? '36px' : '18px' }"></div>
          <span class="ch-num">{{ (data.pacing_curve.start_chapter || 1) + idx }}</span>
        </div>
      </div>
      <div v-for="(w, idx) in (data.pacing_curve.warnings || [])" :key="idx" class="pacing-warn">
        ⚠️ {{ w.detail || w }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.msg-batch-audit {
  padding: 16px; background: rgba(255,255,255,0.03); border: 1px solid rgba(54,173,106,0.2);
  border-radius: 12px; margin: 8px 0;
}
.msg-batch-audit h3 { font-size: 16px; color: #36ad6a; margin-bottom: 12px; }
.audit-section { margin-top: 12px; }
.audit-section h4 { font-size: 14px; color: rgba(255,255,255,0.8); margin-bottom: 8px; }
.forgotten-item { padding: 6px 10px; margin-bottom: 4px; border-radius: 6px; font-size: 13px; }
.forgotten-item.warn { background: rgba(208,160,0,0.12); }
.forgotten-item.error { background: rgba(208,48,48,0.12); }
.forgotten-item.note { background: rgba(120,120,140,0.12); }
.no-issues { font-size: 13px; color: #36ad6a; padding: 4px 0; }
.pacing-chart { display: flex; align-items: flex-end; gap: 4px; height: 70px; margin-bottom: 8px; }
.tension-col { display: flex; flex-direction: column; align-items: center; gap: 2px; }
.tension-bar { width: 24px; border-radius: 4px 4px 0 0; }
.tension-bar.high { background: #d03030; }
.tension-bar.medium { background: #d0a000; }
.tension-bar.low { background: #70c0e8; }
.ch-num { font-size: 10px; color: rgba(255,255,255,0.4); }
.pacing-warn { font-size: 12px; color: #d0a000; margin-top: 4px; }
</style>

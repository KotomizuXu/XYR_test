<script setup lang="ts">
import { computed, ref } from 'vue'
import JsonViewer from './JsonViewer.vue'

const props = defineProps<{ content: any; label?: string }>()

const data = computed(() => {
  if (!props.content || typeof props.content !== 'object') return null
  return props.content
})

const tabs = computed(() => {
  const d = data.value
  if (!d) return []
  const result: { key: string; label: string; data: any; type: 'world' | 'outline' | 'auto' }[] = []
  if (d.world_data && typeof d.world_data === 'object') result.push({ key: 'world', label: '世界观', data: d.world_data, type: 'world' })
  if (d.characters && Array.isArray(d.characters)) result.push({ key: 'characters', label: `角色 (${d.characters.length})`, data: d.characters, type: 'auto' })
  if (d.locations && Array.isArray(d.locations)) result.push({ key: 'locations', label: `地点 (${d.locations.length})`, data: d.locations, type: 'auto' })
  if (d.outline && typeof d.outline === 'object') result.push({ key: 'outline', label: '大纲', data: d.outline, type: 'outline' })
  if (result.length === 0) result.push({ key: 'raw', label: '原始数据', data: d, type: 'auto' })
  return result
})

const activeTab = ref(tabs.value[0]?.key || '')
</script>

<template>
  <n-card :title="label || '设定详情'" class="refine-viewer">
    <n-tabs v-model:value="activeTab" type="segment" animated>
      <n-tab-pane v-for="tab in tabs" :key="tab.key" :name="tab.key" :tab="tab.label">
        <JsonViewer :data="tab.data" :type="tab.type" />
      </n-tab-pane>
    </n-tabs>
  </n-card>
</template>

<style scoped>
.refine-viewer { margin: 12px 0; }
</style>

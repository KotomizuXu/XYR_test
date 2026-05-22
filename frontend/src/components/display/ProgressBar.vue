<script setup lang="ts">
import { computed } from 'vue'
import { useNovelStore } from '../../store'

const store = useNovelStore()

const progressInfo = computed(() => {
  for (let i = store.messages.length - 1; i >= 0; i--) {
    const msg = store.messages[i]
    if (msg.type === 'output' && msg.data.kind === 'progress') {
      return msg.data
    }
  }
  return null
})
</script>

<template>
  <n-card v-if="progressInfo" title="写作进度" size="small">
    <n-progress
      type="line"
      :percentage="progressInfo.total ? Math.round((progressInfo.current / progressInfo.total) * 100) : 0"
      indicator-placement="inside"
      :height="24"
    />
    <p style="margin-top: 8px; text-align: center; color: rgba(255,255,255,0.6)">
      {{ progressInfo.current || 0 }} / {{ progressInfo.total || 0 }} {{ progressInfo.label }}
    </p>
  </n-card>
</template>

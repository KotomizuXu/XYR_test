<script setup lang="ts">
import type { InputRequest } from '../../store'

const props = defineProps<{ request: InputRequest }>()
const emit = defineEmits<{ respond: [value: boolean] }>()
</script>

<template>
  <div>
    <p class="prompt-message">{{ props.request.data.message }}</p>
    <n-space>
      <n-button type="primary" @click="emit('respond', true)">确认</n-button>
      <n-button @click="emit('respond', false)">取消</n-button>
    </n-space>
  </div>
</template>

<style scoped>
.prompt-message { margin-bottom: 12px; font-size: 15px; }
</style>

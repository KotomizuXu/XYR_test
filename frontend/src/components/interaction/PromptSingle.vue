<script setup lang="ts">
import { ref } from 'vue'
import type { InputRequest } from '../../store'

const props = defineProps<{ request: InputRequest }>()
const emit = defineEmits<{ respond: [value: string] }>()
const value = ref(props.request.data.default || '')
</script>

<template>
  <div>
    <p class="prompt-message">{{ props.request.data.message }}</p>
    <n-input
      v-model:value="value"
      :placeholder="props.request.data.default || ''"
      @keydown.enter="emit('respond', value)"
    />
    <n-button type="primary" style="margin-top: 8px" @click="emit('respond', value)">提交</n-button>
  </div>
</template>

<style scoped>
.prompt-message { margin-bottom: 12px; font-size: 15px; }
</style>

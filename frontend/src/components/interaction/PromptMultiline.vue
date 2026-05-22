<script setup lang="ts">
import { ref } from 'vue'
import type { InputRequest } from '../../store'

const props = defineProps<{ request: InputRequest }>()
const emit = defineEmits<{ respond: [value: string] }>()
const value = ref('')
</script>

<template>
  <div>
    <p class="prompt-message">{{ props.request.data.message }}</p>
    <n-input
      v-model:value="value"
      type="textarea"
      :rows="5"
      :placeholder="props.request.data.hint || '请输入...'"
    />
    <n-button type="primary" style="margin-top: 8px" @click="emit('respond', value)">提交</n-button>
  </div>
</template>

<style scoped>
.prompt-message { margin-bottom: 12px; font-size: 15px; }
</style>

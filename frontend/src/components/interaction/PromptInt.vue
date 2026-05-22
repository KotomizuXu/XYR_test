<script setup lang="ts">
import { ref } from 'vue'
import type { InputRequest } from '../../store'

const props = defineProps<{ request: InputRequest }>()
const emit = defineEmits<{ respond: [value: number] }>()
const value = ref(props.request.data.default ?? 0)
</script>

<template>
  <div>
    <p class="prompt-message">{{ props.request.data.message }}</p>
    <div class="input-row">
      <n-input-number
        v-model:value="value"
        :min="props.request.data.min_val"
        :max="props.request.data.max_val"
        style="width: 200px"
      />
      <n-button type="primary" @click="emit('respond', value)">确认</n-button>
    </div>
  </div>
</template>

<style scoped>
.prompt-message { margin-bottom: 12px; font-size: 15px; }
.input-row { display: flex; align-items: center; gap: 8px; }
</style>

<script setup lang="ts">
import type { InputRequest } from '../../store'

const props = defineProps<{ request: InputRequest }>()
const emit = defineEmits<{ respond: [value: string] }>()
</script>

<template>
  <div>
    <p class="prompt-message">{{ props.request.data.message }}</p>
    <n-space vertical>
      <n-button
        v-for="opt in props.request.data.options"
        :key="opt.key"
        :type="opt.key === props.request.data.default_key ? 'primary' : 'default'"
        block
        @click="emit('respond', opt.key)"
      >
        {{ opt.label }}
      </n-button>
    </n-space>
  </div>
</template>

<style scoped>
.prompt-message { margin-bottom: 12px; font-size: 15px; line-height: 1.6; white-space: pre-wrap; }
</style>

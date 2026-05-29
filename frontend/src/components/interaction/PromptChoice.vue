<script setup lang="ts">
import { ref } from 'vue'
import type { InputRequest } from '../../store'

const props = defineProps<{ request: InputRequest }>()
const emit = defineEmits<{ respond: [value: string] }>()
const customValue = ref('')
const showCustom = ref(false)
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
      <template v-if="props.request.data.allow_custom">
        <n-button
          v-if="!showCustom"
          block
          dashed
          @click="showCustom = true"
        >
          自定义输入...
        </n-button>
        <template v-else>
          <n-input
            v-model:value="customValue"
            placeholder="请输入自定义选项"
            @keyup.enter="customValue && emit('respond', customValue)"
          />
          <n-button
            type="primary"
            block
            :disabled="!customValue"
            @click="emit('respond', customValue)"
          >
            确认自定义
          </n-button>
        </template>
      </template>
    </n-space>
  </div>
</template>

<style scoped>
.prompt-message { margin-bottom: 12px; font-size: 15px; line-height: 1.6; white-space: pre-wrap; }
</style>

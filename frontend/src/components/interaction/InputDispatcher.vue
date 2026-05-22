<script setup lang="ts">
import type { InputRequest } from '../../store'
import PromptChoice from './PromptChoice.vue'
import PromptYesNo from './PromptYesNo.vue'
import PromptSingle from './PromptSingle.vue'
import PromptMultiline from './PromptMultiline.vue'
import PromptInt from './PromptInt.vue'

defineProps<{ request: InputRequest }>()
const emit = defineEmits<{ respond: [requestId: string, value: any] }>()
</script>

<template>
  <div class="input-dispatcher" v-if="request">
    <PromptChoice
      v-if="request.data.kind === 'choice'"
      :request="request"
      @respond="(v) => emit('respond', request.request_id, v)"
    />
    <PromptYesNo
      v-else-if="request.data.kind === 'yes_no'"
      :request="request"
      @respond="(v) => emit('respond', request.request_id, v)"
    />
    <PromptSingle
      v-else-if="request.data.kind === 'single'"
      :request="request"
      @respond="(v) => emit('respond', request.request_id, v)"
    />
    <PromptMultiline
      v-else-if="request.data.kind === 'multiline'"
      :request="request"
      @respond="(v) => emit('respond', request.request_id, v)"
    />
    <PromptInt
      v-else-if="request.data.kind === 'int'"
      :request="request"
      @respond="(v) => emit('respond', request.request_id, v)"
    />
  </div>
</template>

<style scoped>
.input-dispatcher {
  padding: 16px; margin-top: 16px;
  border: 1px solid rgba(54,173,106,0.3); border-radius: 12px;
  background: rgba(54,173,106,0.05);
}
</style>

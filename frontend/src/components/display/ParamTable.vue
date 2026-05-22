<script setup lang="ts">
defineProps<{ data: any }>()
</script>

<template>
  <n-card title="参数建议" size="small">
    <n-descriptions bordered :column="1">
      <n-descriptions-item label="风格">{{ data.style_name }}</n-descriptions-item>
      <n-descriptions-item label="推荐章数">{{ data.rec_chapters }}</n-descriptions-item>
      <n-descriptions-item label="每章字数">{{ data.rec_min }} - {{ data.rec_max }}</n-descriptions-item>
      <n-descriptions-item v-if="data.pace_desc" label="节奏">{{ data.pace_desc }}</n-descriptions-item>
      <n-descriptions-item v-if="data.chapters_reason" label="章数理由">{{ data.chapters_reason }}</n-descriptions-item>
    </n-descriptions>
  </n-card>
</template>

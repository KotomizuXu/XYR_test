<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  data: any
  type?: 'world' | 'outline' | 'style' | 'auto'
}>()

// ── 中文标签映射表 ──

const FIELD_LABELS: Record<string, string> = {
  // 通用
  name: '名称', description: '描述', status: '状态', type: '类型',
  content: '内容', purpose: '目的', event: '事件', result: '结果',
  cause: '起因', time: '时间', scale: '规模', climate: '气候',
  terrain: '地形', nature: '性质', title: '标题', summary: '概要',
  role: '角色定位', number: '编号', location: '地点/场景',

  // 世界观
  tone: '基调', setting: '背景', narrative_perspective: '叙事视角',
  rules: '核心规则', unique_elements: '世界特色',
  social_structure: '社会结构', geography: '地理', factions: '势力',
  history: '历史事件', daily_life: '日常生活',
  main_locations: '主要地点', political_system: '政治体系',
  economy: '经济', social_classes: '社会阶层', culture: '文化',
  clothing_food: '衣食', etiquette: '礼仪', festivals: '节庆', currency: '货币',
  magic_system: '魔法/力量体系', technology_level: '科技水平',
  key_figures: '关键人物', period: '时代',
  travel_routes: '旅行路线', from: '出发地', to: '目的地', distance: '距离/耗时',
  impact: '影响', planned_cast: '角色规划', brief: '简介',
  planned_locations: '地点规划',

  // 角色字段
  characters: '角色', personality: '性格特点', motivation: '核心动机',
  arc: '成长弧线', fatal_flaw: '致命缺陷', false_belief: '错误信念',
  want: '表面渴望', need: '深层需求', ghost: '心魔/旧伤',
  mbti: 'MBTI', aliases: '别名', biggest_fear: '最大恐惧',
  inner_desire: '内心渴望', appearance: '外貌', abilities: '能力',
  background: '背景', growth_plan: '成长弧线', voice: '语言风格',
  protagonist: '主角', supporting_characters: '配角',
  currentStatus: '当前状态', health: '健康', location_name: '当前位置',
  development: '发展', planned: '预设', current: '当前',
  speech: '语言特征', sample_phrases: '口头禅',
  physical_traits: '外貌特征', distinguishing_marks: '显著特征',
  consistency: '一致性', physicalTraits: '外貌一致性', personalityTraits: '性格一致性',
  speechPatterns: '语言风格一致性',
  age: '年龄', height_build: '身高体型', features: '相貌特点',
  clothing_style: '穿着风格', distinctive_marks: '特殊标记',
  special: '特殊能力', skills: '技能特长', weaknesses: '弱点',
  childhood: '童年经历', growth: '成长历程', key_events: '重要事件',
  turning_point: '人生转折', early: '初期状态', mid: '中期发展',
  late: '后期蜕变', final: '最终形态',
  catchphrases: '口头禅', address_style: '称呼方式',
  elders: '对长辈称呼', peers: '对平辈称呼', self: '自称',
  emotional_expressions: '情绪表达', happy: '高兴时', angry: '愤怒时',
  sad: '悲伤时', nervous: '紧张时',
  secrets: '秘密/反差', speech_patterns: '言语习惯',

  // 地点卡
  position: '相对位置', first_appearance: '首次出现',
  five_senses: '五感细节', visual: '视觉元素', auditory: '听觉元素',
  olfactory: '嗅觉元素', tactile: '触觉元素',
  function: '剧情功能', related_characters: '相关人物',
  significance: '故事意义', inhabitants: '常驻人群', access: '进出方式',
  atmosphere: '氛围', sensory_details: '感官细节', taste: '味觉元素',

  // 大纲
  theme: '主题', ending: '结局方向', three_act: '三幕结构',
  key_turning_points: '关键转折点', act_1: '第一幕', act_2: '第二幕', act_3: '第三幕',
  '第一幕-开端': '第一幕-开端', '第二幕-发展': '第二幕-发展', '第三幕-高潮与结局': '第三幕-高潮与结局',
  premise: '前提', central_conflict: '核心冲突', climax: '高潮',
  volumes: '分卷结构', narrative_focus: '叙事焦点',
  tone_guidance: '文风指导', reference_works: '参考作品',
  target_words_per_chapter: '每章目标字数', style: '风格指南',

  // 章节计划
  chapter_number: '章节号', emotional_arc: '情绪线',
  emotional_type: '情绪类型', emotional_intensity: '情绪强度',
  characters_involved: '涉及角色', foreshadowing: '伏笔',
  active_plotlines: '活跃线索', act: '所属幕', cliffhanger: '章节钩子',
  scene_structure: '场景结构', tension_level: '张力等级',
  previous_link: '承上启下', opening_hook_type: '章首引子类型',
  ending_hook_type: '章尾悬念类型', characters_on_stage: '实际登场角色',
  scene_list: '场景列表', plot_points: '情节点',
  duration: '时长', planned_reveal: '计划揭示', visibility: '可见度',

  // 风格
  style_name: '风格名称', genre: '类型',
  pacing: '节奏', plot: '剧情', character: '角色',
  worldbuilding: '世界观构建', review: '审核', editing: '编辑',
  style_presets: '风格预设', requirements: '写作规范',
  overall: '整体', language: '语言风格', sentence_structure: '句式',
  imagery: '意象', speed: '节奏速度', hooks_per_chapter: '每章钩子数',
  cliffhanger_style: '悬念风格', dialogue_style: '对话风格',
  depth: '深度', growth_pace: '成长节奏', detail_level: '细节密度',
  exposition_style: '展现方式', priority: '优先级', focus: '侧重点',
  detected: '检测项', anti_ai_banned_words: '禁用词',
  genre_conventions: '类型惯例', taboos: '禁忌',
  style_rules: '风格规则', dialogue_rules: '对话规则',
  suggestions: '建议', agent_temperatures: 'Agent温度',
  genre_knowledge: '类型知识库',
  quality_gates: '质量红线',
  conflict_style: '冲突风格', progression: '剧情推进方式',
  reward_density: '奖励密度', turning_points: '转折点风格',
  unique_focus: '独特性侧重', dealbreakers: '绝对不能出现',
  flexible_aspects: '可宽容方面', preserve: '必须保留特征',
  total_chapters: '建议总章数', recommended: '推荐值', reason: '理由',
  words_per_chapter: '每章字数建议', min: '最小值', max: '最大值',
  pace_description: '节奏建议', tracking_thresholds: '追踪阈值',
  plotline: '支线停滞阈值', required_elements: '必需元素',
  pacing_rules: '节奏规则', primary_style: '主文风',
  narration_rules: '叙述风格规则',
  director: '导演', plotter: '编剧', writer: '作家',
  reviewer: '审核', editor: '编辑', style_advisor: '风格顾问', critic: '修订顾问',

  // 关系/追踪
  allies: '盟友', enemies: '敌人', romantic: '恋爱', family: '家人',
  mentors: '导师', relationships: '关系', factions_list: '势力列表',
  conflicts: '冲突', active: '活跃', resolved: '已解决', upcoming: '即将发生',
  foreshadowing_list: '伏笔列表', planted: '已埋设', retired: '已回收',
  storyTime: '故事时间', events: '事件', currentState: '当前状态',
  mainPlotStage: '主线阶段', plotlines: '线索', checkpoints: '检查点',
}

function label(key: string): string {
  return FIELD_LABELS[key] || key
}

// 分类：将 entries 按类型分为两组
// scalars = 字符串/数字/布尔/字符串数组（合并到一个 descriptions 表格）
// complex = 对象数组/嵌套对象（各自独立成块）
function classifyEntries(obj: any) {
  const scalars: { key: string; val: any; kind: 'scalar' | 'tags' }[] = []
  const complex: { key: string; val: any; kind: 'objectArray' | 'object' }[] = []

  if (!obj || typeof obj !== 'object') return { scalars, complex }

  for (const [key, val] of Object.entries(obj)) {
    if (val == null) continue
    if (Array.isArray(val)) {
      if (val.length === 0) continue
      if (val.every((x: any) => typeof x === 'string')) {
        scalars.push({ key, val, kind: 'tags' })
      } else if (val.every((x: any) => x && typeof x === 'object' && !Array.isArray(x))) {
        complex.push({ key, val, kind: 'objectArray' })
      } else {
        scalars.push({ key, val, kind: 'tags' })
      }
    } else if (typeof val === 'object') {
      complex.push({ key, val, kind: 'object' })
    } else {
      scalars.push({ key, val, kind: 'scalar' })
    }
  }
  return { scalars, complex }
}

function getTitle(item: any): string {
  if (!item || typeof item !== 'object') return ''
  // 优先使用标识性字段
  const id = item.name || item.title || item.event || item.type
    || item.description || item.label || item.turning_point
  if (id && typeof id === 'string') return id.length > 40 ? id.slice(0, 40) + '…' : id
  // 回退：取第一个字符串值
  for (const v of Object.values(item)) {
    if (typeof v === 'string' && v.length > 0) {
      return v.length > 40 ? v.slice(0, 40) + '…' : v
    }
  }
  return ''
}
</script>

<template>
  <div v-if="!data || typeof data !== 'object'" class="jv-empty">暂无数据</div>
  <template v-else>
    <template v-for="([groupKey, entries], gi) in [['scalars', classifyEntries(data).scalars], ['complex', classifyEntries(data).complex]]" :key="groupKey">

      <!-- Scalar group: one unified descriptions table -->
      <n-descriptions v-if="groupKey === 'scalars' && entries.length" bordered :column="1" label-placement="left" size="small" class="jv-table">
        <template v-for="s in entries" :key="s.key">
          <n-descriptions-item :label="label(s.key)">
            <template v-if="s.kind === 'tags'">
              <n-space size="small" wrap>
                <n-tag v-for="(t, i) in s.val" :key="i" size="small" round>{{ typeof t === 'string' ? t : String(t) }}</n-tag>
              </n-space>
            </template>
            <template v-else>
              <span class="jv-text">{{ s.val }}</span>
            </template>
          </n-descriptions-item>
        </template>
      </n-descriptions>

      <!-- Complex group: each item gets its own block -->
      <template v-if="groupKey === 'complex'">
        <template v-for="c in entries" :key="c.key">
          <!-- Array of objects -->
          <template v-if="c.kind === 'objectArray'">
            <div class="jv-sub-title">{{ label(c.key) }}（{{ c.val.length }}）</div>
            <n-collapse>
              <n-collapse-item v-for="(item, i) in c.val" :key="i" :title="getTitle(item) || `${label(c.key)} ${i + 1}`" :name="`${c.key}-${i}`">
                <JsonViewer :data="item" type="auto" />
              </n-collapse-item>
            </n-collapse>
          </template>

          <!-- Nested object -->
          <template v-else-if="c.kind === 'object'">
            <div class="jv-sub-title">{{ label(c.key) }}</div>
            <div class="jv-indent">
              <JsonViewer :data="c.val" type="auto" />
            </div>
          </template>
        </template>
      </template>
    </template>
  </template>
</template>

<style scoped>
.jv-empty { color: rgba(255,255,255,0.3); text-align: center; padding: 16px; }
.jv-sub-title { font-size: 13px; color: rgba(255,255,255,0.5); margin-top: 14px; margin-bottom: 6px; }
.jv-indent { margin-left: 8px; padding-left: 8px; border-left: 2px solid rgba(255,255,255,0.08); }
.jv-text { white-space: pre-wrap; line-height: 1.7; }
.jv-table { margin-bottom: 4px; }
</style>

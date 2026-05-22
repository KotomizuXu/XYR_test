<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  data: any
  type?: 'world' | 'outline' | 'style' | 'auto'
}>()

// Resolve the actual world object — it may be nested under "world" key
const worldObj = computed(() => {
  const d = props.data
  if (!d || typeof d !== 'object') return null
  // holistic directing wraps under "world"
  if (d.world && typeof d.world === 'object') return d.world
  // if top-level has setting+rules, it's already the world object
  if (d.setting && d.rules) return d
  return null
})

const charsList = computed(() => {
  const d = props.data
  if (!d) return []
  // characters at top level (holistic) or inside world
  const chars = d.characters || (d.world?.characters)
  if (!Array.isArray(chars)) return []
  return chars
})

const resolvedType = computed(() => {
  if (props.type && props.type !== 'auto') return props.type
  if (worldObj.value) return 'world'
  const d = props.data
  if (d?.three_act || d?.theme) return 'outline'
  if (d?.style_name && d?.tone) return 'style'
  return 'auto'
})

// ── World ──
const worldScalars = computed(() => {
  const d = worldObj.value
  if (!d) return []
  const items: { label: string; value: string }[] = []
  if (d.name) items.push({ label: '世界名称', value: d.name })
  if (d.tone) items.push({ label: '基调', value: d.tone })
  if (d.setting) items.push({ label: '背景', value: d.setting })
  if (d.narrative_perspective) items.push({ label: '叙事视角', value: d.narrative_perspective })
  if (d.rules) items.push({ label: '核心规则', value: d.rules })
  return items
})

const worldTags = computed(() => {
  const el = worldObj.value?.unique_elements
  if (!Array.isArray(el)) return []
  return el.slice(0, 8).map(String)
})

const worldSocial = computed(() => {
  const s = worldObj.value?.social_structure
  if (!s || typeof s !== 'object') return null
  const map: Record<string, string> = { political_system: '政治体系', economy: '经济', social_classes: '社会阶层', culture: '文化' }
  const items = Object.entries(map).filter(([k]) => s[k]).map(([k, label]) => ({ label, value: s[k] }))
  return items.length ? items : null
})

const worldLocations = computed(() => {
  const locs = worldObj.value?.geography?.main_locations
  if (!Array.isArray(locs)) return []
  return locs.slice(0, 8)
})

const worldFactions = computed(() => {
  const f = worldObj.value?.factions
  if (!Array.isArray(f)) return []
  return f.slice(0, 8)
})

const worldHistory = computed(() => {
  const h = worldObj.value?.history
  if (!Array.isArray(h)) return []
  return h.slice(0, 5)
})

const worldDaily = computed(() => {
  const dl = worldObj.value?.daily_life
  if (!dl || typeof dl !== 'object') return null
  const map: Record<string, string> = { clothing_food: '衣食', etiquette: '礼仪', festivals: '节庆', currency: '货币' }
  const items = Object.entries(dl).filter(([, v]) => v).map(([k, v]) => ({ label: map[k] || k, value: String(v) }))
  return items.length ? items : null
})

// ── Characters ──
// Extract key fields from complex character objects into displayable sections
const charSections = ['appearance', 'abilities', 'background', 'growth_plan', 'voice'] as const
const charSectionLabels: Record<string, string> = {
  appearance: '外貌', abilities: '能力', background: '背景', growth_plan: '成长弧线', voice: '语言风格',
}

function flattenObj(obj: any, prefix = ''): { label: string; value: string }[] {
  if (!obj || typeof obj !== 'object') return []
  const items: { label: string; value: string }[] = []
  for (const [k, v] of Object.entries(obj)) {
    if (!v) continue
    const key = prefix ? `${prefix}.${k}` : k
    if (typeof v === 'object' && !Array.isArray(v)) {
      items.push(...flattenObj(v, key))
    } else {
      const val = Array.isArray(v) ? v.join('、') : String(v)
      if (val.length > 500) {
        items.push({ label: key, value: val.slice(0, 500) + '...' })
      } else {
        items.push({ label: key, value: val })
      }
    }
  }
  return items
}

// ── Outline ──
const outlineScalars = computed(() => {
  const d = props.data
  if (!d) return []
  const items: { label: string; value: string }[] = []
  if (d.theme) items.push({ label: '主题', value: d.theme })
  if (d.ending) items.push({ label: '结局方向', value: d.ending })
  return items
})

const outlineActs = computed(() => {
  const ta = props.data?.three_act
  if (!ta || typeof ta !== 'object') return []
  return Object.entries(ta).map(([k, v]) => ({ label: k, value: String(v) }))
})

const outlineTurning = computed(() => {
  const tp = props.data?.key_turning_points
  if (!Array.isArray(tp)) return []
  return tp.map(String)
})

// ── Style ──
const styleScalars = computed(() => {
  const d = props.data
  if (!d) return []
  const items: { label: string; value: string }[] = []
  if (d.style_name) items.push({ label: '风格名称', value: d.style_name })
  if (d.tone && typeof d.tone === 'object') {
    const map: Record<string, string> = { overall: '整体基调', language: '语言风格', sentence_structure: '句式', imagery: '意象' }
    for (const [k, v] of Object.entries(d.tone)) {
      if (v) items.push({ label: map[k] || k, value: String(v) })
    }
  }
  if (d.setting?.genre) items.push({ label: '类型', value: d.setting.genre })
  return items
})

const styleSubSections = ['pacing', 'plot', 'character', 'worldbuilding', 'review', 'editing'] as const
const styleSectionLabels: Record<string, string> = {
  pacing: '节奏', plot: '剧情', character: '角色', worldbuilding: '世界观构建', review: '审核', editing: '编辑',
}

const styleTagsGroups = computed(() => {
  const d = props.data
  const groups: { label: string; items: string[] }[] = []
  const add = (label: string, arr: any) => { if (Array.isArray(arr) && arr.length) groups.push({ label, items: arr.slice(0, 10).map(String) }) }
  add('类型惯例', d?.setting?.genre_conventions)
  add('禁忌', d?.setting?.taboos)
  add('写作规范', d?.requirements?.detected)
  add('禁用词', d?.requirements?.anti_ai_banned_words)
  add('风格规则', d?.style_presets?.style_rules)
  add('对话规则', d?.style_presets?.dialogue_rules)
  return groups
})
</script>

<template>
  <div v-if="!data || typeof data !== 'object'" class="jv-empty">暂无数据</div>

  <!-- ═══ World ═══ -->
  <template v-else-if="resolvedType === 'world'">
    <!-- Top-level scalars -->
    <n-descriptions v-if="worldScalars.length" bordered :column="1" label-placement="left" size="small">
      <n-descriptions-item v-for="s in worldScalars" :key="s.label" :label="s.label">{{ s.value }}</n-descriptions-item>
    </n-descriptions>

    <!-- Unique elements -->
    <div v-if="worldTags.length" class="jv-tags">
      <span class="jv-tag-label">世界特色</span>
      <n-tag v-for="(t, i) in worldTags" :key="i" size="small" round>{{ t }}</n-tag>
    </div>

    <!-- Social structure -->
    <template v-if="worldSocial">
      <div class="jv-sub-title">社会结构</div>
      <n-descriptions bordered :column="2" label-placement="left" size="small">
        <n-descriptions-item v-for="s in worldSocial" :key="s.label" :label="s.label">{{ s.value }}</n-descriptions-item>
      </n-descriptions>
    </template>

    <!-- Locations -->
    <template v-if="worldLocations.length">
      <div class="jv-sub-title">主要地点 ({{ worldLocations.length }})</div>
      <n-list bordered size="small">
        <n-list-item v-for="loc in worldLocations" :key="loc.name">
          <n-thing>
            <template #header>{{ loc.name }}</template>
            <template #description>{{ loc.description }}</template>
            <template #footer>
              <n-space size="small">
                <n-tag v-if="loc.climate" size="tiny">{{ loc.climate }}</n-tag>
                <n-tag v-if="loc.terrain" size="tiny" type="info">{{ loc.terrain }}</n-tag>
              </n-space>
            </template>
          </n-thing>
        </n-list-item>
      </n-list>
    </template>

    <!-- Factions -->
    <template v-if="worldFactions.length">
      <div class="jv-sub-title">势力 ({{ worldFactions.length }})</div>
      <n-list bordered size="small">
        <n-list-item v-for="f in worldFactions" :key="f.name">
          <n-thing>
            <template #header>{{ f.name }}</template>
            <template #description>{{ f.nature }} · {{ f.purpose }}</template>
            <template #footer>
              <n-space size="small">
                <n-tag v-if="f.scale" size="tiny">{{ f.scale }}</n-tag>
                <n-tag v-for="fig in (f.key_figures || []).slice(0, 3)" :key="fig" size="tiny" type="info">{{ fig }}</n-tag>
              </n-space>
            </template>
          </n-thing>
        </n-list-item>
      </n-list>
    </template>

    <!-- History -->
    <template v-if="worldHistory.length">
      <div class="jv-sub-title">历史事件</div>
      <n-list bordered size="small">
        <n-list-item v-for="h in worldHistory" :key="h.event">
          <n-thing>
            <template #header>{{ h.event }}</template>
            <template #description>{{ h.result }}</template>
            <template #footer>
              <n-space size="small">
                <n-tag v-if="h.time" size="tiny">{{ h.time }}</n-tag>
                <n-tag v-if="h.cause" size="tiny" type="info">起因：{{ h.cause }}</n-tag>
              </n-space>
            </template>
          </n-thing>
        </n-list-item>
      </n-list>
    </template>

    <!-- Daily life -->
    <template v-if="worldDaily">
      <div class="jv-sub-title">日常生活</div>
      <n-descriptions bordered :column="2" label-placement="left" size="small">
        <n-descriptions-item v-for="d in worldDaily" :key="d.label" :label="d.label">{{ d.value }}</n-descriptions-item>
      </n-descriptions>
    </template>

    <!-- Characters -->
    <template v-if="charsList.length">
      <div class="jv-sub-title">角色 ({{ charsList.length }})</div>
      <n-collapse>
        <n-collapse-item v-for="c in charsList" :key="c.name" :title="`${c.name}（${c.role || '角色'}）`" :name="c.name">
          <n-descriptions bordered :column="1" label-placement="left" size="small">
            <n-descriptions-item v-if="c.personality" label="性格">{{ c.personality }}</n-descriptions-item>
            <n-descriptions-item v-if="c.motivation" label="动机">{{ c.motivation }}</n-descriptions-item>
            <n-descriptions-item v-if="c.arc" label="成长弧线">{{ c.arc }}</n-descriptions-item>
            <n-descriptions-item v-if="c.fatal_flaw" label="致命缺陷">{{ c.fatal_flaw }}</n-descriptions-item>
            <n-descriptions-item v-if="c.aliases?.length" label="别名">{{ c.aliases.join('、') }}</n-descriptions-item>
          </n-descriptions>
          <n-collapse v-if="charSections.some(s => c[s])" style="margin-top: 8px">
            <n-collapse-item v-for="sec in charSections" :key="sec" :title="charSectionLabels[sec]" :name="sec">
              <n-descriptions v-if="c[sec] && typeof c[sec] === 'object' && !Array.isArray(c[sec])" bordered :column="1" label-placement="left" size="small">
                <n-descriptions-item v-for="item in flattenObj(c[sec])" :key="item.label" :label="item.label">{{ item.value }}</n-descriptions-item>
              </n-descriptions>
              <n-text v-else>{{ c[sec] }}</n-text>
            </n-collapse-item>
          </n-collapse>
        </n-collapse-item>
      </n-collapse>
    </template>

    <!-- Raw fallback -->
    <n-collapse class="jv-raw">
      <n-collapse-item title="完整原始数据" name="raw">
        <n-code :code="JSON.stringify(data, null, 2)" language="json" word-wrap />
      </n-collapse-item>
    </n-collapse>
  </template>

  <!-- ═══ Outline ═══ -->
  <template v-else-if="resolvedType === 'outline'">
    <n-descriptions v-if="outlineScalars.length" bordered :column="1" label-placement="left" size="small">
      <n-descriptions-item v-for="s in outlineScalars" :key="s.label" :label="s.label">{{ s.value }}</n-descriptions-item>
    </n-descriptions>

    <template v-if="outlineActs.length">
      <div class="jv-sub-title">三幕结构</div>
      <n-descriptions bordered :column="1" label-placement="top" size="small">
        <n-descriptions-item v-for="a in outlineActs" :key="a.label" :label="a.label">{{ a.value }}</n-descriptions-item>
      </n-descriptions>
    </template>

    <template v-if="outlineTurning.length">
      <div class="jv-sub-title">关键转折点</div>
      <n-list bordered size="small">
        <n-list-item v-for="(t, i) in outlineTurning" :key="i">
          <n-text>{{ t }}</n-text>
        </n-list-item>
      </n-list>
    </template>

    <n-collapse class="jv-raw">
      <n-collapse-item title="完整原始数据" name="raw">
        <n-code :code="JSON.stringify(data, null, 2)" language="json" word-wrap />
      </n-collapse-item>
    </n-collapse>
  </template>

  <!-- ═══ Style ═══ -->
  <template v-else-if="resolvedType === 'style'">
    <n-descriptions v-if="styleScalars.length" bordered :column="1" label-placement="left" size="small">
      <n-descriptions-item v-for="s in styleScalars" :key="s.label" :label="s.label">{{ s.value }}</n-descriptions-item>
    </n-descriptions>

    <template v-for="secKey in styleSubSections" :key="secKey">
      <template v-if="data[secKey] && typeof data[secKey] === 'object'">
        <div class="jv-sub-title">{{ styleSectionLabels[secKey] }}</div>
        <n-descriptions bordered :column="1" label-placement="left" size="small">
          <n-descriptions-item v-for="(v, k) in data[secKey]" :key="k" :label="k">
            <template v-if="typeof v === 'string'">{{ v }}</template>
            <template v-else>{{ v }}</template>
          </n-descriptions-item>
        </n-descriptions>
      </template>
    </template>

    <template v-for="tg in styleTagsGroups" :key="tg.label">
      <div class="jv-tags">
        <span class="jv-tag-label">{{ tg.label }}</span>
        <n-tag v-for="t in tg.items" :key="t" size="small" round>{{ t }}</n-tag>
      </div>
    </template>

    <!-- Genre knowledge (long text) -->
    <template v-if="data?.setting?.genre_knowledge">
      <n-collapse style="margin-top: 12px">
        <n-collapse-item title="类型知识库" name="genre_knowledge">
          <n-text style="white-space: pre-wrap">{{ data.setting.genre_knowledge }}</n-text>
        </n-collapse-item>
      </n-collapse>
    </template>

    <n-collapse class="jv-raw">
      <n-collapse-item title="完整原始数据" name="raw">
        <n-code :code="JSON.stringify(data, null, 2)" language="json" word-wrap />
      </n-collapse-item>
    </n-collapse>
  </template>

  <!-- ═══ Auto fallback ═══ -->
  <template v-else>
    <n-collapse>
      <n-collapse-item title="数据" name="raw">
        <n-code :code="JSON.stringify(data, null, 2)" language="json" word-wrap />
      </n-collapse-item>
    </n-collapse>
  </template>
</template>

<style scoped>
.jv-empty { color: rgba(255,255,255,0.3); text-align: center; padding: 16px; }
.jv-sub-title { font-size: 13px; color: rgba(255,255,255,0.5); margin-top: 16px; margin-bottom: 6px; }
.jv-tags { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: 12px; }
.jv-tag-label { font-size: 12px; color: rgba(255,255,255,0.4); margin-right: 4px; }
.jv-raw { margin-top: 16px; }
</style>

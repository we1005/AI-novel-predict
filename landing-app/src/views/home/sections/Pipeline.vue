<script setup lang="ts">
import { Badge } from '@/components/ui/badge'

const steps = [
  { idx: '一', title: '拆成记忆', desc: '6 个 agent 逐章抽实体 / 伏笔 / 关系 / 状态,存成可查询的结构化记忆。' },
  { idx: '二', title: '预测整弧', desc: '从当前进度推演到结局的候选故事弧,逐阶段重锚定,做完整性裁决。' },
  { idx: '三', title: '逐章成稿', desc: '写 → 三审(剧情 · 一致性 · 文风)→ 把新章回灌进记忆,环环相扣。' },
  { idx: '四', title: '写到结局', desc: '每阶段跨章复审 + 人审通过再续,一路滚到大结局,不断线。' },
]

const chips = [
  ['四层记忆', '实体 / 伏笔 / 关系 / 状态'],
  ['写完即回灌', '下一章读得到上一章'],
  ['仿原作者文风', '对齐单章体量'],
  ['逐章 git', '可追溯 · 可回滚'],
]
</script>

<template>
  <section id="how" class="relative py-28 px-6 bg-gradient-to-b from-transparent to-mb-canvas-2">
    <div class="max-w-6xl mx-auto">
      <div
        class="max-w-2xl mb-14"
        v-motion
        :initial="{ opacity: 0, y: 28 }"
        :visible-once="{ opacity: 1, y: 0, transition: { duration: 600 } }"
      >
        <Badge variant="qing" class="mb-4">How · 它怎么记住一百万字</Badge>
        <h2 class="font-mb-display text-[clamp(28px,4.2vw,44px)] leading-tight">
          四步,一路滚动地平线写到结局
        </h2>
        <p class="mt-4 font-mb-body text-[16px] text-mb-ink-soft">
          每一步都拿上一步的产物当记忆——写出来的新章,立刻变成下一章能读到的东西。
        </p>
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <div
          v-for="(s, i) in steps"
          :key="s.idx"
          class="glass lift rounded-[18px] p-8"
          v-motion
          :initial="{ opacity: 0, y: 30 }"
          :visible-once="{ opacity: 1, y: 0, transition: { duration: 560, delay: i * 100 } }"
        >
          <span class="font-mb-display text-[38px] text-mb-seal leading-none block mb-4">{{ s.idx }}</span>
          <h4 class="font-mb-display text-[19px] mb-2.5">{{ s.title }}</h4>
          <p class="font-mb-body text-[14px] text-mb-ink-soft leading-[1.8]">{{ s.desc }}</p>
        </div>
      </div>

      <div
        class="flex gap-3 flex-wrap mt-10"
        v-motion
        :initial="{ opacity: 0, y: 20 }"
        :visible-once="{ opacity: 1, y: 0, transition: { duration: 560, delay: 200 } }"
      >
        <span
          v-for="c in chips"
          :key="c[0]"
          class="inline-flex items-center gap-2 rounded-full border border-mb-line-2 bg-white/55 px-4 py-2.5 text-[13px] text-mb-ink-soft font-mb-body"
        >
          <b class="text-mb-qing font-semibold">{{ c[0] }}</b>
          <span class="text-mb-ink-mute">·</span>
          {{ c[1] }}
        </span>
      </div>
    </div>
  </section>
</template>

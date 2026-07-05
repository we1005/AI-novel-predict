<script setup lang="ts">
import { XCircle, CheckCircle2 } from 'lucide-vue-next'

const cards = [
  {
    kind: 'flaw' as const,
    icon: XCircle,
    title: '直接让模型写,会塌',
    desc: '把一百万字全塞进去让 LLM 接着写:它会忘掉早埋的伏笔、把人物写偏、违反自己立下的世界设定。上下文越长,越糊。',
  },
  {
    kind: 'fix' as const,
    icon: CheckCircle2,
    title: '先把书拆成记忆',
    desc: '墨笔用一组 agent 把小说嚼成可查询的结构——谁欠谁一条命、哪句谶语还没应验、剑在第几章出鞘。续写时只召回「当下该被想起的」那几条。',
  },
]
</script>

<template>
  <section class="relative py-24 px-6">
    <div class="max-w-6xl mx-auto grid md:grid-cols-2 gap-6">
      <div
        v-for="(c, i) in cards"
        :key="c.title"
        class="glass lift rounded-[20px] p-9"
        v-motion
        :initial="{ opacity: 0, y: 34 }"
        :visible-once="{ opacity: 1, y: 0, transition: { duration: 620, delay: i * 110 } }"
      >
        <component
          :is="c.icon"
          class="w-8 h-8 mb-5"
          :class="c.kind === 'flaw' ? 'text-mb-seal' : 'text-mb-qing'"
        />
        <h2
          class="font-mb-display text-[26px] mb-3"
          :class="c.kind === 'flaw' ? 'text-mb-seal' : 'text-mb-qing'"
        >
          {{ c.title }}
        </h2>
        <p class="font-mb-body text-[16.5px] text-mb-ink-soft max-w-[42ch]">{{ c.desc }}</p>
      </div>
    </div>
  </section>
</template>

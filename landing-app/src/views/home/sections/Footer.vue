<script setup lang="ts">
import { BookOpen } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { brand } from '../../../brand'

const year = new Date().getFullYear()
</script>

<template>
  <footer class="relative pt-24 pb-12 px-6 bg-mb-ink text-white overflow-hidden">
    <!-- 竖排题签:此後 · 墨筆續 -->
    <div class="max-w-6xl mx-auto text-center">
      <p class="font-mb-display text-[clamp(26px,4vw,40px)] leading-relaxed tracking-[0.08em]">
        此後
        <span class="inline-block mx-4 align-middle w-10 h-px bg-white/30" />
        墨筆續
      </p>
      <p class="mt-4 font-mb-caps text-white/45">A memory-native engine · continue to the end</p>
    </div>

    <div class="max-w-6xl mx-auto mt-16 grid md:grid-cols-[1.6fr_1fr] gap-10 pb-10 border-b border-white/10">
      <div>
        <div class="flex items-baseline gap-3 mb-3">
          <span class="font-mb-display text-2xl">{{ brand.chinese }}</span>
          <span class="font-mb-caps text-white/45">{{ brand.english }}</span>
        </div>
        <p class="font-mb-body text-sm text-white/60 max-w-md">
          {{ brand.tagline }}——把「读者的记忆」外化出来:先把一本书拆成可被记起的结构化记忆,再让笔只在此刻该想起的部分上落墨。
        </p>
        <p class="mt-4 font-mb-body text-[13px] text-white/40">{{ brand.twin }}</p>
      </div>

      <div class="md:justify-self-end md:text-right">
        <p class="font-mb-caps text-white/40 mb-4">Read</p>
        <Button as="a" :href="brand.readUrl" target="_blank" rel="noopener" size="default">
          <BookOpen class="w-4 h-4" />
          读续写的《天之炽》
        </Button>
      </div>
    </div>

    <div
      class="max-w-6xl mx-auto mt-8 flex flex-wrap items-center justify-between gap-4 text-[11px] text-white/40 font-mb-caps"
    >
      <span>© {{ year }} {{ brand.chinese }} · {{ brand.english }}</span>
      <span>Crafted with Vue 3 · Vite · Tailwind v4 · reka-ui</span>
    </div>
  </footer>
</template>

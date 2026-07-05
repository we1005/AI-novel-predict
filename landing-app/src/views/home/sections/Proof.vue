<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { ArrowRight } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { stats, brand } from '../../../brand'

const displayed = ref<number[]>(stats.map(() => 0))
const sectionRef = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | null = null

function animate() {
  const duration = 1500
  let start = 0
  const targets = stats.map((s) => s.value)
  function tick(t: number) {
    if (!start) start = t
    const p = Math.min(1, (t - start) / duration)
    const e = 1 - Math.pow(1 - p, 3) // easeOutCubic
    displayed.value = targets.map((v) => v * e)
    if (p < 1) requestAnimationFrame(tick)
    else displayed.value = targets.slice()
  }
  requestAnimationFrame(tick)
}

function fmt(i: number) {
  const s = stats[i]
  const v = displayed.value[i]
  return s.decimals ? v.toFixed(s.decimals) : Math.round(v).toString()
}

onMounted(() => {
  if (!sectionRef.value) return
  observer = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (e.isIntersecting) {
          animate()
          observer?.disconnect()
          break
        }
      }
    },
    { threshold: 0.3 },
  )
  observer.observe(sectionRef.value)
})
onUnmounted(() => observer?.disconnect())
</script>

<template>
  <section
    ref="sectionRef"
    class="relative py-28 px-6 bg-mb-ink text-white overflow-hidden isolate"
  >
    <!-- 竖细纹 -->
    <div
      class="absolute inset-0 opacity-[0.06] pointer-events-none"
      style="background-image: linear-gradient(90deg, #fff 1px, transparent 1px); background-size: 84px 100%"
    />
    <!-- 巨「墨」水印 -->
    <span
      class="absolute -right-[3vw] -top-[8vh] font-mb-display font-black leading-none opacity-[0.05] pointer-events-none select-none"
      style="font-size: 46vh"
      aria-hidden="true"
      >墨</span
    >

    <div class="relative max-w-6xl mx-auto">
      <p class="font-mb-caps text-white/50 mb-4">跑通的证据 · Proof</p>
      <h3 class="font-mb-display text-[clamp(26px,3.8vw,40px)] leading-tight text-white max-w-[20ch]">
        《天之炽》从第 157 章,一路续到结局
      </h3>
      <p class="mt-5 font-mb-body text-[15.5px] text-white/60 max-w-[58ch]">
        江南的《天之炽》原著到第 156 章。墨笔从这里接手,仿原作者文风、对齐原著单章体量,逐章成稿到第 260 章大结局——每一章都进 git,可追溯、可回滚。
      </p>

      <div class="mt-14 grid grid-cols-2 md:grid-cols-4 gap-x-8 gap-y-12">
        <div v-for="(s, i) in stats" :key="s.label">
          <div class="font-mb-num tabular text-white text-[clamp(40px,5.5vw,60px)] leading-none">
            {{ fmt(i) }}<span class="text-white/45 text-[0.42em] ml-1.5 font-mb-body">{{ s.unit }}</span>
          </div>
          <div class="mt-3.5 text-[12.5px] text-white/55 font-mb-body">{{ s.label }}</div>
        </div>
      </div>

      <div class="mt-16">
        <Button as="a" :href="brand.readUrl" target="_blank" rel="noopener" size="lg" class="group">
          读读续写出来的《天之炽》
          <ArrowRight class="w-4 h-4 transition-transform group-hover:translate-x-1" />
        </Button>
      </div>
    </div>
  </section>
</template>

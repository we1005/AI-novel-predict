<script setup lang="ts">
import { onMounted, onUnmounted, ref, computed } from 'vue'
import NavBar from './sections/NavBar.vue'
import Hero from './sections/Hero.vue'
import Argue from './sections/Argue.vue'
import Proof from './sections/Proof.vue'
import Pipeline from './sections/Pipeline.vue'
import Footer from './sections/Footer.vue'
import { brand } from '../../brand'

// 全页水印随滚动做轻视差(rAF 节流)
const scrollY = ref(0)
let raf = 0
function onScroll() {
  cancelAnimationFrame(raf)
  raf = requestAnimationFrame(() => (scrollY.value = window.scrollY))
}
onMounted(() => {
  window.addEventListener('scroll', onScroll, { passive: true })
  window.scrollTo({ top: 0 })
})
onUnmounted(() => {
  cancelAnimationFrame(raf)
  window.removeEventListener('scroll', onScroll)
})

const mark1 = computed(() => `translate3d(0, ${scrollY.value * -0.14}px, 0)`)
const mark2 = computed(() => `translate3d(0, ${scrollY.value * 0.1}px, 0)`)
</script>

<template>
  <div class="home-root relative">
    <!-- 环境网格光晕(缓慢漂移) -->
    <div class="mesh-bg" aria-hidden="true" />
    <!-- 幽灵水印 記 / 續 -->
    <div
      class="mark"
      aria-hidden="true"
      style="left: -6vw; top: 2vh; font-size: 44vh"
      :style="{ transform: mark1 }"
    >
      {{ brand.hanziFloat[0] }}
    </div>
    <div
      class="mark"
      aria-hidden="true"
      style="right: -4vw; bottom: -6vh; font-size: 38vh; color: var(--color-mb-qing); opacity: 0.05"
      :style="{ transform: mark2 }"
    >
      {{ brand.hanziFloat[1] }}
    </div>

    <div class="relative z-10">
      <NavBar />
      <main>
        <Hero />
        <Argue />
        <Proof />
        <Pipeline />
      </main>
      <Footer />
    </div>
  </div>
</template>

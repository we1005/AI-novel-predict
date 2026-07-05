<script setup lang="ts">
import { ArrowRight } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { brand } from '../../../brand'
</script>

<template>
  <section class="relative min-h-screen flex items-center overflow-hidden px-6 pt-28 pb-16">
    <!-- 局部水墨底纹(纯矢量,不依赖网络) -->
    <svg
      class="absolute inset-0 w-full h-full opacity-[0.05] mix-blend-multiply pointer-events-none"
      viewBox="0 0 1600 900"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
    >
      <defs><filter id="mb-ink"><feGaussianBlur stdDeviation="7" /></filter></defs>
      <g filter="url(#mb-ink)" fill="#14141a">
        <path
          d="M-40 640 C 220 560, 400 700, 640 620 S 1020 540, 1260 660 1700 620 1700 720 L1700 900 -40 900 Z"
        />
        <path
          d="M140 200 C 280 240, 420 160, 580 250 S 860 190, 980 280"
          stroke="#14141a"
          stroke-width="16"
          stroke-linecap="round"
          fill="none"
          opacity="0.5"
        />
      </g>
    </svg>

    <div class="relative w-full max-w-6xl mx-auto grid lg:grid-cols-[1.05fr_minmax(300px,400px)] gap-14 items-center">
      <!-- 命题 -->
      <div>
        <p class="font-mb-caps text-mb-seal mb-6 mb-reveal">{{ brand.englishSub }}</p>

        <h1
          class="font-mb-display leading-[0.94] whitespace-nowrap mb-reveal mb-reveal-1"
          style="font-size: clamp(44px, 7.4vw, 104px)"
        >
          记忆<span class="text-mb-qing font-serif font-normal align-[0.16em] mx-[0.04em]" style="font-size: 0.44em">&gt;</span>上下文
        </h1>

        <p class="font-mb-num text-mb-ink-soft mt-3 mb-reveal mb-reveal-2" style="font-size: clamp(22px, 3.4vw, 34px)">
          墨笔 · MoBi
        </p>

        <p class="mt-7 max-w-[34ch] text-[19px] text-mb-ink-soft font-mb-body mb-reveal mb-reveal-2">
          让 AI 续写百万字长篇,靠的不是更大的模型——是先把这本书变成<b class="text-mb-qing font-semibold">可以被记起的东西</b>,每次落笔只取此刻该想起的部分。
        </p>

        <div class="mt-9 flex items-center gap-4 flex-wrap mb-reveal mb-reveal-3">
          <Button as="a" :href="brand.readUrl" target="_blank" rel="noopener" size="xl" class="group">
            读续写出来的《天之炽》
            <ArrowRight class="w-4 h-4 transition-transform group-hover:translate-x-1" />
          </Button>
          <a
            href="#how"
            class="font-mb-body text-[15px] text-mb-ink-soft border-b border-mb-line-2 pb-0.5 hover:text-mb-qing hover:border-mb-qing transition-colors"
          >
            看它怎么记住
          </a>
        </div>

        <!-- 图例 -->
        <div class="mt-14 flex gap-8 flex-wrap items-center text-[12.5px] text-mb-ink-mute font-mb-body">
          <span class="inline-flex items-center gap-2.5">
            <i class="w-3.5 h-3.5 rounded-[3px] bg-mb-ink" />浓墨 · 原著
          </span>
          <span class="inline-flex items-center gap-2.5">
            <i class="w-3.5 h-3.5 rounded-[3px] bg-mb-qing" />花青 · 墨笔续写
          </span>
          <span class="inline-flex items-center gap-2.5">
            <i class="w-3.5 h-3.5 rounded-[3px] bg-mb-seal" />朱砂 · 接笔之缝
          </span>
        </div>
      </div>

      <!-- 竖排双墨手稿 -->
      <div
        class="glass rounded-[20px] relative justify-self-end w-full max-w-[400px] h-[min(60vh,520px)] px-8 py-7 flex overflow-hidden max-lg:h-auto max-lg:justify-self-stretch max-lg:max-w-none"
        aria-label="手稿:原著墨迹在朱文印处转为墨笔续写的花青"
        v-motion
        :initial="{ opacity: 0, y: 24, scale: 0.97 }"
        :enter="{ opacity: 1, y: 0, scale: 1, transition: { duration: 700, delay: 320 } }"
      >
        <span
          class="absolute top-5 bottom-5 right-5 w-px bg-mb-line-2 max-lg:hidden"
          aria-hidden="true"
        />
        <p class="manu max-lg:[writing-mode:horizontal-tb] max-lg:h-auto max-lg:leading-[2]">
          <span class="ori">夜雨敲窗,他写到这一行,墨已干,书未竟。</span>
          <span
            class="seal-mark"
            aria-hidden="true"
            v-motion
            :initial="{ opacity: 0, scale: 1.4, rotate: -9 }"
            :enter="{ opacity: 1, scale: 1, rotate: -3, transition: { duration: 550, delay: 980 } }"
          >
            {{ brand.sealText[0] }}<br />{{ brand.sealText[1] }}
          </span>
          <span
            class="cont"
            v-motion
            :initial="{ opacity: 0 }"
            :enter="{ opacity: 1, transition: { duration: 800, delay: 760 } }"
          >
            可故事记得每一道伏笔、每个人的来路——于是笔自己接着写了下去,一直写到结局。
          </span>
        </p>
      </div>
    </div>
  </section>
</template>

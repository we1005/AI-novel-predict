<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { BookOpen } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { brand } from '../../../brand'

const scrolled = ref(false)
function onScroll() {
  scrolled.value = window.scrollY > 20
}
onMounted(() => {
  window.addEventListener('scroll', onScroll, { passive: true })
  onScroll()
})
onUnmounted(() => window.removeEventListener('scroll', onScroll))
</script>

<template>
  <nav
    class="fixed inset-x-0 top-0 z-50 transition-all duration-500 ease-[cubic-bezier(0.2,0.8,0.2,1)]"
    :class="scrolled ? 'pt-3' : 'pt-5'"
  >
    <div class="max-w-6xl mx-auto px-4 md:px-6">
      <div
        class="flex items-center justify-between transition-all duration-500 ease-[cubic-bezier(0.2,0.8,0.2,1)]"
        :class="
          scrolled
            ? 'glass glass-float rounded-full pl-6 pr-2.5 py-2.5'
            : 'rounded-full px-2 py-1.5'
        "
      >
        <a :href="brand.readUrl" class="flex items-baseline gap-2.5 group" target="_blank" rel="noopener">
          <span
            class="font-mb-display text-[22px] tracking-[0.14em] group-hover:text-mb-seal transition-colors"
          >
            {{ brand.chinese }}
          </span>
          <span class="font-mb-caps text-mb-ink-mute">{{ brand.english }}</span>
        </a>

        <Button as="a" :href="brand.readUrl" target="_blank" rel="noopener" size="sm">
          <BookOpen class="w-4 h-4" />
          读续写的《天之炽》
        </Button>
      </div>
    </div>
  </nav>
</template>

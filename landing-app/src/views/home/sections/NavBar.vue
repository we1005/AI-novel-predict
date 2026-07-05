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
    class="fixed top-0 inset-x-0 z-50 transition-all duration-300"
    :class="scrolled ? 'glass-navbar py-3' : 'py-5'"
  >
    <div class="max-w-6xl mx-auto px-6 flex items-center justify-between">
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
  </nav>
</template>

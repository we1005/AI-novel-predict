import { createApp } from 'vue'
import { MotionPlugin } from '@vueuse/motion'

import './assets/tailwind.css'
import './style/home.css'
import App from './App.vue'

createApp(App).use(MotionPlugin).mount('#app')

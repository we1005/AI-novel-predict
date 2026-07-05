import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

/**
 * shadcn-vue 约定的 className 合并器:tailwind-merge 解决冲突 + clsx 处理条件 class。
 * 所有 ui/* 组件都 import { cn } from '@/lib/utils'。
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

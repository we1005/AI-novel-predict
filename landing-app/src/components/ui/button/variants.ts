import { cva, type VariantProps } from 'class-variance-authority'

/**
 * shadcn-vue Button variants(cva)。基础类显式定义 box/flex/font,不依赖 Preflight。
 * 墨笔定制:default=朱砂印;qing=花青(续写);outline/ghost;size 增加 xl(hero CTA)。
 */
export const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full font-medium transition-[transform,background-color,box-shadow,color,border-color] duration-200 ease-[cubic-bezier(0.2,0.8,0.2,1)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-mb-canvas disabled:pointer-events-none disabled:opacity-50 cursor-pointer select-none border box-border',
  {
    variants: {
      variant: {
        default:
          'bg-mb-seal text-primary-foreground border-transparent shadow-[0_12px_26px_-14px_rgba(180,54,26,0.7)] hover:-translate-y-0.5 hover:shadow-[0_18px_34px_-14px_rgba(180,54,26,0.78)]',
        qing:
          'bg-mb-qing text-white border-transparent shadow-[0_12px_26px_-14px_rgba(46,107,117,0.7)] hover:-translate-y-0.5 hover:shadow-[0_18px_34px_-14px_rgba(46,107,117,0.78)]',
        outline:
          'border-mb-line-2 bg-white/60 backdrop-blur text-mb-ink hover:bg-white hover:border-mb-seal/50',
        ghost:
          'border-transparent bg-transparent text-mb-ink-soft hover:bg-white/60 hover:text-mb-ink',
      },
      size: {
        sm: 'h-8 px-4 text-[13px]',
        default: 'h-10 px-5 text-[14px]',
        lg: 'h-12 px-6 text-[15px]',
        xl: 'h-14 px-8 text-[16px]',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  },
)

export type ButtonVariants = VariantProps<typeof buttonVariants>

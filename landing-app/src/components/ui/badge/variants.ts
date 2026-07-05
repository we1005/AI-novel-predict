import { cva, type VariantProps } from 'class-variance-authority'

export const badgeVariants = cva(
  'inline-flex items-center gap-1.5 rounded-full border box-border font-mb-caps leading-none transition-colors',
  {
    variants: {
      variant: {
        seal: 'border-mb-seal/25 bg-mb-seal-soft text-mb-seal px-3 py-1.5',
        qing: 'border-mb-qing/25 bg-mb-qing-soft text-mb-qing px-3 py-1.5',
        outline: 'border-mb-line-2 bg-white/50 text-mb-ink-soft px-3 py-1.5',
      },
    },
    defaultVariants: { variant: 'outline' },
  },
)

export type BadgeVariants = VariantProps<typeof badgeVariants>

import { COMPOUND_LABEL, COMPOUND_COLOURS } from '@/lib/utils'

interface Props {
  compound: string | null
  size?: 'sm' | 'md'
}

export default function TyreChip({ compound, size = 'sm' }: Props) {
  if (!compound) return null
  const bg = COMPOUND_COLOURS[compound] ?? '#666'
  const label = COMPOUND_LABEL[compound] ?? compound[0]
  const textColour = compound === 'MEDIUM' || compound === 'HARD' ? '#000' : '#fff'
  const sz = size === 'sm' ? 'w-5 h-5 text-[10px]' : 'w-6 h-6 text-xs'

  return (
    <span
      className={`inline-flex items-center justify-center rounded-full font-mono font-bold ${sz}`}
      style={{ background: bg, color: textColour }}
    >
      {label}
    </span>
  )
}

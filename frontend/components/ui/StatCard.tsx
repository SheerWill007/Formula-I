interface Props {
  label: string
  value: string
  delta?: string
  deltaPositive?: boolean
  icon?: React.ReactNode
  mono?: boolean
}

export default function StatCard({ label, value, delta, deltaPositive, icon, mono }: Props) {
  return (
    <div className="bg-surface border border-border rounded-lg p-4 relative overflow-hidden">
      {/* Red top accent */}
      <div className="absolute top-0 left-0 right-0 h-0.5 bg-red" />

      <div className="flex items-start justify-between mb-2">
        <span className="text-[10px] font-medium tracking-widest text-zinc-500 uppercase">
          {label}
        </span>
        {icon && <span className="text-zinc-600">{icon}</span>}
      </div>

      <div className={`text-2xl font-bold text-white mb-1 ${mono ? 'font-mono' : 'font-display'}`}>
        {value}
      </div>

      {delta && (
        <div className={`text-xs font-medium ${deltaPositive ? 'text-green-400' : 'text-zinc-400'}`}>
          {delta}
        </div>
      )}
    </div>
  )
}

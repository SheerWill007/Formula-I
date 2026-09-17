export default function LoadingSpinner({ text = 'Loading...' }: { text?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-20 text-zinc-500">
      <div className="w-8 h-8 border-2 border-border border-t-red rounded-full animate-spin" />
      <span className="text-sm font-mono">{text}</span>
    </div>
  )
}

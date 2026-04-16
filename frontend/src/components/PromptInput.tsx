import { Send } from 'lucide-react'
import { DEMO_PROMPTS } from '../types'

interface Props {
  prompt: string
  loading: boolean
  onPromptChange: (value: string) => void
  onSubmit: (e: React.FormEvent) => void
}

export function PromptInput({ prompt, loading, onPromptChange, onSubmit }: Props) {
  return (
    <div className="bg-slate-900/80 border-t border-white/5 px-4 py-3 flex-shrink-0">
      {/* Demo prompt chips */}
      <div className="flex flex-wrap gap-1.5 mb-2">
        {DEMO_PROMPTS.map(({ label, prompt: p }) => (
          <button
            key={label}
            onClick={() => onPromptChange(p)}
            className="text-[10px] px-2.5 py-1 rounded-full bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200 transition-colors border border-slate-700/60"
          >
            {label}
          </button>
        ))}
      </div>

      <form onSubmit={onSubmit} className="flex gap-2 items-end">
        <textarea
          value={prompt}
          onChange={(e) => onPromptChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              if (prompt.trim() && !loading) onSubmit(e as unknown as React.FormEvent)
            }
          }}
          placeholder="Send a prompt — Aegis routes it to the optimal model automatically. Shift+Enter for new line."
          rows={2}
          className="flex-1 bg-slate-800/80 border border-slate-700/60 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-emerald-500/60 resize-none"
        />
        <button
          type="submit"
          disabled={loading || !prompt.trim()}
          className="bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-700 disabled:cursor-not-allowed text-white px-4 py-2 rounded-lg flex items-center gap-1.5 transition-colors text-sm font-medium flex-shrink-0 h-[68px]"
        >
          {loading ? (
            <span className="animate-spin text-base">⏳</span>
          ) : (
            <Send className="w-4 h-4" />
          )}
        </button>
      </form>
    </div>
  )
}

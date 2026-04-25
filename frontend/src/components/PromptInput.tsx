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
    <div className="bg-white border-t border-[#E5E2DC] px-4 py-3 flex-shrink-0">
      {/* Demo prompt chips */}
      <div className="mb-2">
        <p className="text-[10px] text-slate-500 uppercase tracking-wide mb-1.5">Try a demo:</p>
        <div className="flex flex-wrap gap-1.5">
          {DEMO_PROMPTS.map(({ label, prompt: p, tooltip }) => (
            <button
              key={label}
              onClick={() => onPromptChange(p)}
              title={tooltip}
              className="text-[10px] px-2.5 py-1 rounded-full bg-[#F1EFE9] hover:bg-[#E5E2DC] text-slate-600 hover:text-slate-900 transition-colors border border-[#E5E2DC]"
            >
              {label}
            </button>
          ))}
        </div>
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
          className="flex-1 bg-white border border-[#E5E2DC] rounded-lg px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-emerald-500 resize-none"
        />
        <button
          type="submit"
          disabled={loading || !prompt.trim()}
          className="bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-200 disabled:cursor-not-allowed text-white disabled:text-slate-400 px-4 py-2 rounded-lg flex items-center gap-1.5 transition-colors text-sm font-medium flex-shrink-0 h-[68px]"
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

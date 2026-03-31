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
    <div className="bg-slate-800/50 rounded-xl p-6 border border-slate-700">
      <h2 className="text-lg font-semibold text-white mb-4">Send a Prompt</h2>

      <div className="flex flex-wrap gap-2 mb-4">
        {DEMO_PROMPTS.map(({ label, prompt: p }) => (
          <button
            key={label}
            onClick={() => onPromptChange(p)}
            className="text-xs px-3 py-1.5 rounded-full bg-slate-700 hover:bg-slate-600 text-slate-300 hover:text-white transition-colors border border-slate-600"
          >
            {label}
          </button>
        ))}
      </div>

      <form onSubmit={onSubmit} className="space-y-4">
        <textarea
          value={prompt}
          onChange={(e) => onPromptChange(e.target.value)}
          placeholder="Enter your prompt here... Aegis will route it to the optimal model."
          className="w-full h-32 bg-slate-900 border border-slate-600 rounded-lg p-4 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 resize-none"
        />
        <button
          type="submit"
          disabled={loading || !prompt.trim()}
          className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-700 disabled:cursor-not-allowed text-white font-medium py-3 px-4 rounded-lg flex items-center justify-center gap-2 transition-colors"
        >
          {loading ? (
            <span className="animate-spin">⏳</span>
          ) : (
            <Send className="w-4 h-4" />
          )}
          {loading ? 'Processing...' : 'Send Prompt'}
        </button>
      </form>
    </div>
  )
}

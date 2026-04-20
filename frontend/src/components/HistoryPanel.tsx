import { useState } from 'react'
import { History, Zap, ChevronLeft, ChevronRight, AlertTriangle } from 'lucide-react'
import { HistoryItem, MODEL_COLORS } from '../types'

interface Props {
  history: HistoryItem[]
  onSelect: (item: HistoryItem) => void
  selectedId?: string
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const secs = Math.floor(diff / 1000)
  if (secs < 60) return `${secs}s ago`
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

const DOMAIN_STYLES: Record<string, string> = {
  legal:     'bg-blue-900/40 text-blue-300',
  medical:   'bg-red-900/40 text-red-300',
  financial: 'bg-amber-900/40 text-amber-300',
  general:   'bg-slate-700 text-slate-300',
}

const RISK_DOT: Record<string, string> = {
  SAFE:   'bg-emerald-400',
  MEDIUM: 'bg-amber-400',
  HIGH:   'bg-red-400',
}

export function HistoryPanel({ history, onSelect, selectedId }: Props) {
  const [collapsed, setCollapsed] = useState(false)

  if (collapsed) {
    return (
      <div className="hidden lg:flex flex-col items-center w-10 flex-shrink-0 pt-2 gap-2">
        <button
          onClick={() => setCollapsed(false)}
          className="p-1.5 rounded-lg bg-slate-800/60 hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
          title="Show history"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
        <History className="w-4 h-4 text-slate-600 rotate-0" />
      </div>
    )
  }

  return (
    <div className="hidden lg:flex flex-col w-[280px] flex-shrink-0 bg-slate-800/40 backdrop-blur-sm rounded-xl border border-white/5 ring-1 ring-white/5 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
        <div className="flex items-center gap-2">
          <History className="w-4 h-4 text-emerald-400" />
          <span className="text-sm font-semibold text-white">History</span>
          {history.length > 0 && (
            <span className="text-xs bg-slate-700 text-slate-400 rounded-full px-1.5 py-0.5">
              {history.length}
            </span>
          )}
        </div>
        <button
          onClick={() => setCollapsed(true)}
          className="p-1 rounded hover:bg-slate-700 text-slate-500 hover:text-white transition-colors"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {history.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 gap-2 text-slate-600">
            <History className="w-8 h-8 opacity-30" />
            <p className="text-xs">No requests yet</p>
          </div>
        ) : (
          <div className="p-2 space-y-1">
            {history.map((item) => {
              const modelColor = MODEL_COLORS[item.response.model_used] ?? '#6b7280'
              const domain = item.response.domain ?? 'general'
              const risk = item.response.risk_level ?? 'SAFE'
              const isSelected = item.id === selectedId

              return (
                <button
                  key={item.id}
                  onClick={() => onSelect(item)}
                  className={`w-full text-left rounded-lg p-3 transition-all border ${
                    isSelected
                      ? 'bg-emerald-900/30 border-emerald-700/50'
                      : 'bg-slate-900/40 border-transparent hover:bg-slate-700/50 hover:border-white/10'
                  }`}
                >
                  {/* Top row: time + risk dot + cache bolt + hallucination flag */}
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-xs text-slate-500">{relativeTime(item.timestamp)}</span>
                    <div className="flex items-center gap-1.5">
                      {item.response.causal_analysis?.is_hallucination && (
                        <AlertTriangle className="w-3 h-3 text-red-400" aria-label="Hallucination flagged" />
                      )}
                      {item.response.routing_decision.cache_hit && (
                        <Zap className="w-3 h-3 text-amber-400" aria-label="Cache hit" />
                      )}
                      <span
                        className={`w-2 h-2 rounded-full flex-shrink-0 ${RISK_DOT[risk] ?? 'bg-slate-500'}`}
                        aria-label={`Risk: ${risk}`}
                      />
                    </div>
                  </div>

                  {/* Prompt truncated */}
                  <p className="text-xs text-slate-300 leading-relaxed line-clamp-2 mb-2">
                    {item.prompt.length > 60 ? item.prompt.slice(0, 60) + '…' : item.prompt}
                  </p>

                  {/* Bottom row: model badge + domain pill */}
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span
                      className="text-xs px-1.5 py-0.5 rounded font-mono"
                      style={{ backgroundColor: modelColor + '22', color: modelColor }}
                    >
                      {item.response.model_used.split('-')[0]}
                    </span>
                    <span className={`text-xs px-1.5 py-0.5 rounded ${DOMAIN_STYLES[domain] ?? DOMAIN_STYLES.general}`}>
                      {domain}
                    </span>
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

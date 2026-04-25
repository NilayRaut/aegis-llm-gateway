import { CheckCircle } from 'lucide-react'
import { StreamStage } from '../types'

interface Props {
  stages: StreamStage[]
}

const STAGE_ICONS: Record<number, string> = {
  1: '🛡',
  2: '⚡',
  3: '📊',
  4: '🔀',
  5: '🤖',
  6: '🔍',
  7: '📋',
}

export function StreamingStatus({ stages }: Props) {
  if (stages.length === 0) return null

  return (
    <div className="bg-white border border-[#E5E2DC] shadow-sm rounded-xl p-5">
      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4">Pipeline</p>
      <div className="space-y-2.5">
        {stages.map((s, i) => (
          <div key={i} className="flex items-start gap-3">
            <div className="flex-shrink-0 mt-0.5">
              {s.done ? (
                <CheckCircle className="w-4 h-4 text-emerald-600" />
              ) : (
                <span className="w-4 h-4 flex items-center justify-center">
                  <span className="w-3 h-3 rounded-full border-2 border-indigo-600 border-t-transparent animate-spin block" />
                </span>
              )}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="text-sm">{STAGE_ICONS[s.stage] ?? '•'}</span>
                <span className={`text-xs font-semibold ${s.done ? 'text-slate-500' : 'text-slate-900'}`}>
                  {s.label}
                </span>
              </div>
              <p className={`text-xs mt-0.5 ${s.done ? 'text-slate-400' : 'text-slate-600'}`}>
                {s.message}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

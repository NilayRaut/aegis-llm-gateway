import { AlertTriangle } from 'lucide-react'
import { LLMResponse } from '../types'

interface Props {
  response: LLMResponse
}

export function ResponseCard({ response }: Props) {
  return (
    <div className="bg-slate-800/50 rounded-xl p-6 border border-slate-700 space-y-4">
      <h2 className="text-lg font-semibold text-white">Response</h2>

      <div className="bg-slate-900 rounded-lg p-4 text-slate-200 whitespace-pre-wrap">
        {response.response}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="bg-slate-900/50 rounded-lg p-3">
          <p className="text-xs text-slate-400 mb-1">Model Used</p>
          <p className="text-emerald-400 font-mono text-sm">{response.model_used}</p>
        </div>
        <div className="bg-slate-900/50 rounded-lg p-3">
          <p className="text-xs text-slate-400 mb-1">Cost</p>
          <p className="text-white">${response.cost.toFixed(6)}</p>
        </div>
        <div className="bg-slate-900/50 rounded-lg p-3">
          <p className="text-xs text-slate-400 mb-1">Latency</p>
          <p className="text-white">{response.latency_ms}ms</p>
        </div>
        <div className="bg-slate-900/50 rounded-lg p-3">
          <p className="text-xs text-slate-400 mb-1">Cache Hit</p>
          <p className={response.routing_decision.cache_hit ? 'text-emerald-400' : 'text-slate-400'}>
            {response.routing_decision.cache_hit ? '✓ Yes ($0.00)' : 'No'}
          </p>
        </div>
      </div>

      <div className="bg-slate-900/50 rounded-lg p-3">
        <p className="text-xs text-slate-400 mb-1">Routing Decision</p>
        <p className="text-xs text-slate-300">{response.routing_decision.reason}</p>
      </div>

      {response.causal_analysis && (
        <div className={`rounded-lg p-4 ${
          response.causal_analysis.is_hallucination
            ? 'bg-amber-900/30 border border-amber-700'
            : 'bg-emerald-900/30 border border-emerald-700'
        }`}>
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle className={`w-4 h-4 ${
              response.causal_analysis.is_hallucination ? 'text-amber-400' : 'text-emerald-400'
            }`} />
            <span className="font-medium text-white">
              {response.causal_analysis.is_hallucination
                ? 'Potential Hallucination Detected'
                : 'Response Verified'}
            </span>
          </div>
          <p className="text-sm text-slate-300">{response.causal_analysis.explanation}</p>
        </div>
      )}
    </div>
  )
}

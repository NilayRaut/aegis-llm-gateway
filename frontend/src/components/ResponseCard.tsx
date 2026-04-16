import { AlertTriangle, CheckCircle, Shield, Cpu, Globe, Activity } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { LLMResponse, MODEL_COLORS } from '../types'

interface Props {
  response: LLMResponse
}

const DOMAIN_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  legal:     { bg: 'bg-blue-900/40',   text: 'text-blue-300',   label: 'Legal' },
  medical:   { bg: 'bg-red-900/40',    text: 'text-red-300',    label: 'Medical' },
  financial: { bg: 'bg-amber-900/40',  text: 'text-amber-300',  label: 'Financial' },
  general:   { bg: 'bg-slate-700/60',  text: 'text-slate-300',  label: 'General' },
}

const RISK_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  SAFE:   { bg: 'bg-emerald-900/30', text: 'text-emerald-400', border: 'border-emerald-700/50' },
  MEDIUM: { bg: 'bg-amber-900/30',   text: 'text-amber-400',   border: 'border-amber-700/50' },
  HIGH:   { bg: 'bg-red-900/30',     text: 'text-red-400',     border: 'border-red-700/50' },
}

function complexityBarColor(score: number): string {
  if (score < 0.35) return 'bg-emerald-500'
  if (score < 0.65) return 'bg-amber-500'
  return 'bg-red-500'
}

function complexityLabel(score: number): string {
  if (score < 0.35) return 'Simple'
  if (score < 0.65) return 'Moderate'
  return 'Complex'
}

export function ResponseCard({ response }: Props) {
  const domain = response.domain ?? 'general'
  const risk = response.risk_level ?? 'SAFE'
  const complexity = response.complexity_score ?? 0
  const provider = response.provider ?? ''
  const modelColor = MODEL_COLORS[response.model_used] ?? '#6b7280'

  const domainStyle = DOMAIN_STYLES[domain] ?? DOMAIN_STYLES.general
  const riskStyle = RISK_STYLES[risk] ?? RISK_STYLES.SAFE

  return (
    <div className="bg-slate-800/40 backdrop-blur-sm rounded-xl border border-white/5 ring-1 ring-white/5 overflow-hidden">
      {/* Response text */}
      <div className="px-5 pt-5 pb-4">
        <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Model Response</h2>
        <div className="prose prose-invert prose-sm max-w-none bg-slate-900/60 rounded-lg p-4 text-slate-200">
          <ReactMarkdown>{response.response}</ReactMarkdown>
        </div>
      </div>

      {/* Metrics grid */}
      <div className="px-5 pb-4 grid grid-cols-2 gap-3">
        {/* Model */}
        <div className="bg-slate-900/50 rounded-lg p-3">
          <p className="text-xs text-slate-500 mb-1 flex items-center gap-1.5">
            <Cpu className="w-3 h-3" /> Model
          </p>
          <p className="font-mono text-xs font-medium truncate" style={{ color: modelColor }}>
            {response.model_used}
          </p>
        </div>

        {/* Cost */}
        <div className="bg-slate-900/50 rounded-lg p-3">
          <p className="text-xs text-slate-500 mb-1">Cost</p>
          <p className="text-white text-sm font-medium">${response.cost.toFixed(6)}</p>
        </div>

        {/* Latency */}
        <div className="bg-slate-900/50 rounded-lg p-3">
          <p className="text-xs text-slate-500 mb-1 flex items-center gap-1.5">
            <Activity className="w-3 h-3" /> Latency
          </p>
          <p className="text-white text-sm font-medium">{response.latency_ms}ms</p>
        </div>

        {/* Cache */}
        <div className="bg-slate-900/50 rounded-lg p-3">
          <p className="text-xs text-slate-500 mb-1">Deduplication</p>
          <p className={`text-sm font-medium ${response.routing_decision.cache_hit ? 'text-emerald-400' : 'text-slate-400'}`}>
            {response.routing_decision.cache_hit ? '⚡ Saved ($0.00)' : 'Miss'}
          </p>
        </div>

        {/* Complexity Score — full width */}
        <div className="bg-slate-900/50 rounded-lg p-3 col-span-2">
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs text-slate-500">Routing Confidence Score</p>
            <span className="text-xs text-slate-400">{complexityLabel(complexity)} — {complexity.toFixed(2)}</span>
          </div>
          <div className="w-full bg-slate-700/60 rounded-full h-1.5">
            <div
              className={`h-1.5 rounded-full transition-all duration-700 ${complexityBarColor(complexity)}`}
              style={{ width: `${Math.round(complexity * 100)}%` }}
            />
          </div>
        </div>

        {/* Domain */}
        <div className="bg-slate-900/50 rounded-lg p-3">
          <p className="text-xs text-slate-500 mb-1.5 flex items-center gap-1.5">
            <Globe className="w-3 h-3" /> Domain
          </p>
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${domainStyle.bg} ${domainStyle.text}`}>
            {domainStyle.label}
          </span>
        </div>

        {/* Risk Level */}
        <div className={`rounded-lg p-3 border ${riskStyle.bg} ${riskStyle.border}`}>
          <p className="text-xs text-slate-500 mb-1.5 flex items-center gap-1.5">
            <Shield className="w-3 h-3" /> Risk
          </p>
          <span className={`text-sm font-semibold ${riskStyle.text}`}>{risk}</span>
        </div>

        {/* Provider */}
        {provider && (
          <div className="bg-slate-900/50 rounded-lg p-3 col-span-2">
            <p className="text-xs text-slate-500 mb-1">Provider</p>
            <span className="text-xs px-2 py-0.5 rounded-full bg-slate-700/60 text-slate-300 font-mono">
              {provider}
            </span>
          </div>
        )}
      </div>

      {/* Routing reason */}
      <div className="px-5 pb-4">
        <div className="bg-slate-900/40 rounded-lg px-3 py-2.5">
          <p className="text-xs text-slate-500 mb-0.5">Routing Rationale</p>
          <p className="text-xs text-slate-300">{response.routing_decision.reason}</p>
        </div>
      </div>

      {/* Causal analysis */}
      {response.causal_analysis && (
        <div className="px-5 pb-5">
          <div className={`rounded-lg p-4 ${
            response.causal_analysis.is_hallucination
              ? 'bg-amber-900/30 border border-amber-700/50'
              : 'bg-emerald-900/20 border border-emerald-700/30'
          }`}>
            <div className="flex items-center gap-2 mb-2">
              {response.causal_analysis.is_hallucination ? (
                <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />
              ) : (
                <CheckCircle className="w-4 h-4 text-emerald-400 flex-shrink-0" />
              )}
              <span className="text-sm font-medium text-white">
                {response.causal_analysis.is_hallucination
                  ? 'Reliability Flag — Review Recommended'
                  : 'Reliability Verified'}
              </span>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">{response.causal_analysis.explanation}</p>
          </div>
        </div>
      )}
    </div>
  )
}

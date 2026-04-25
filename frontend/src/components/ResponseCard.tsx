import { AlertTriangle, CheckCircle, Shield, Cpu, Globe, Activity, TrendingDown } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { LLMResponse, MODEL_COLORS } from '../types'
import { RiskPill } from './RiskPill'

const GPT4O_BASELINE = 0.0025

interface Props {
  response: LLMResponse
}

const DOMAIN_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  legal:     { bg: 'bg-blue-50',   text: 'text-blue-700',   label: 'Legal' },
  medical:   { bg: 'bg-red-50',    text: 'text-red-700',    label: 'Medical' },
  financial: { bg: 'bg-amber-50',  text: 'text-amber-700',  label: 'Financial' },
  general:   { bg: 'bg-slate-100', text: 'text-slate-600',  label: 'General' },
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

  return (
    <div className="bg-white border border-[#E5E2DC] shadow-sm rounded-xl overflow-hidden">
      {/* Response text */}
      <div className="px-5 pt-5 pb-4">
        <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Model Response</h2>
        <div className="prose prose-slate prose-sm max-w-none bg-[#F8F7F4] rounded-lg p-4 text-slate-700">
          <ReactMarkdown>{response.response}</ReactMarkdown>
        </div>
        {domain === 'general' && (
          <p className="text-[10px] text-amber-600/80 mt-2 leading-relaxed">
            Note: Responses reflect each model's training cutoff. Verify time-sensitive information independently.
          </p>
        )}
      </div>

      {/* Metrics grid */}
      <div className="px-5 pb-4 grid grid-cols-2 gap-3">
        {/* Model */}
        <div className="bg-[#F1EFE9] rounded-lg p-3">
          <p className="text-xs text-slate-500 mb-1 flex items-center gap-1.5">
            <Cpu className="w-3 h-3" /> Model
          </p>
          <div className="flex items-center gap-1.5 flex-wrap">
            <p className="font-mono text-xs font-medium truncate" style={{ color: modelColor }}>
              {response.model_used}
            </p>
            {response.routing_decision.reason.toLowerCase().includes('fallback') && (
              <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200 flex-shrink-0">
                FALLBACK
              </span>
            )}
          </div>
        </div>

        {/* Cost */}
        <div className="bg-[#F1EFE9] rounded-lg p-3">
          <p className="text-xs text-slate-500 mb-1 flex items-center gap-1.5">
            <TrendingDown className="w-3 h-3" /> Cost
          </p>
          <p className="text-slate-900 text-sm font-medium font-mono">${response.cost.toFixed(6)}</p>
          {response.routing_decision.cache_hit ? (
            <p className="text-[10px] text-emerald-600 mt-0.5">100% saved (cache hit)</p>
          ) : GPT4O_BASELINE - response.cost > 0.000001 ? (
            <p className="text-[10px] text-emerald-600 mt-0.5">
              {Math.round(((GPT4O_BASELINE - response.cost) / GPT4O_BASELINE) * 100)}% vs GPT-4o baseline
            </p>
          ) : null}
        </div>

        {/* Latency */}
        <div className="bg-[#F1EFE9] rounded-lg p-3">
          <p className="text-xs text-slate-500 mb-1 flex items-center gap-1.5">
            <Activity className="w-3 h-3" /> Latency
          </p>
          <p className="text-slate-900 text-sm font-medium font-mono">{response.latency_ms}ms</p>
        </div>

        {/* Cache */}
        <div className="bg-[#F1EFE9] rounded-lg p-3">
          <p className="text-xs text-slate-500 mb-1">Deduplication</p>
          <p className={`text-sm font-medium ${response.routing_decision.cache_hit ? 'text-emerald-600' : 'text-slate-500'}`}>
            {response.routing_decision.cache_hit ? '⚡ Saved ($0.00)' : 'Miss'}
          </p>
        </div>

        {/* Complexity Score — full width */}
        <div className="bg-[#F1EFE9] rounded-lg p-3 col-span-2">
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs text-slate-500">Routing Confidence Score</p>
            <span className="text-xs text-slate-500 font-mono">{complexityLabel(complexity)} — {complexity.toFixed(2)}</span>
          </div>
          <div className="w-full bg-slate-200 rounded-full h-1.5">
            <div
              className={`h-1.5 rounded-full transition-all duration-700 ${complexityBarColor(complexity)}`}
              style={{ width: `${Math.round(complexity * 100)}%` }}
            />
          </div>
        </div>

        {/* Domain */}
        <div className="bg-[#F1EFE9] rounded-lg p-3">
          <p className="text-xs text-slate-500 mb-1.5 flex items-center gap-1.5">
            <Globe className="w-3 h-3" /> Domain
          </p>
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${domainStyle.bg} ${domainStyle.text}`}>
            {domainStyle.label}
          </span>
        </div>

        {/* Risk Level */}
        <div className="bg-[#F1EFE9] rounded-lg p-3">
          <p className="text-xs text-slate-500 mb-1.5 flex items-center gap-1.5">
            <Shield className="w-3 h-3" /> Risk
          </p>
          <RiskPill risk={risk} />
        </div>

        {/* Provider */}
        {provider && (
          <div className="bg-[#F1EFE9] rounded-lg p-3 col-span-2">
            <p className="text-xs text-slate-500 mb-1">Provider</p>
            <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 font-mono border border-slate-200">
              {provider}
            </span>
          </div>
        )}
      </div>

      {/* Routing reason */}
      <div className="px-5 pb-4">
        <div className="bg-[#F1EFE9] rounded-lg px-3 py-2.5">
          <p className="text-xs text-slate-500 mb-0.5">Routing Rationale</p>
          <p className="text-xs text-slate-700">{response.routing_decision.reason}</p>
        </div>
      </div>

      {/* Causal analysis */}
      {response.causal_analysis && (
        <div className="px-5 pb-5">
          <div className={`rounded-lg p-4 ${
            response.causal_analysis.is_hallucination
              ? 'bg-amber-50 border border-amber-200'
              : 'bg-emerald-50 border border-emerald-200'
          }`}>
            <div className="flex items-center gap-2 mb-2">
              {response.causal_analysis.is_hallucination ? (
                <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0" />
              ) : (
                <CheckCircle className="w-4 h-4 text-emerald-600 flex-shrink-0" />
              )}
              <span className="text-sm font-medium text-slate-900">
                {response.causal_analysis.is_hallucination
                  ? 'Reliability Flag — Review Recommended'
                  : 'Reliability Verified'}
              </span>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">{response.causal_analysis.explanation}</p>
          </div>
        </div>
      )}
    </div>
  )
}

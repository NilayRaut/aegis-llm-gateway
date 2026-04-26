import { LLMResponse, MODEL_COLORS } from '../types'

interface Props {
  response: LLMResponse | null
}

interface Step {
  label: string
  value: string
  color: string
  bg: string
  border: string
  active: boolean
}

function complexityColor(score: number): { text: string; bg: string; border: string } {
  if (score < 0.35) return { text: 'text-emerald-700', bg: 'bg-emerald-100', border: 'border-emerald-200' }
  if (score < 0.65) return { text: 'text-amber-700',   bg: 'bg-amber-100',   border: 'border-amber-200' }
  return              { text: 'text-red-700',     bg: 'bg-red-100',     border: 'border-red-200' }
}

const RISK_STYLE: Record<string, { text: string; bg: string; border: string }> = {
  SAFE:   { text: 'text-emerald-700', bg: 'bg-emerald-100', border: 'border-emerald-200' },
  MEDIUM: { text: 'text-amber-700',   bg: 'bg-amber-100',   border: 'border-amber-200' },
  HIGH:   { text: 'text-red-700',     bg: 'bg-red-100',     border: 'border-red-200' },
}

function buildSteps(response: LLMResponse | null): Step[] {
  if (!response) {
    return [
      { label: 'Input',      value: '—', color: 'text-slate-400', bg: 'bg-slate-100', border: 'border-slate-200', active: false },
      { label: 'Security',   value: '—', color: 'text-slate-400', bg: 'bg-slate-100', border: 'border-slate-200', active: false },
      { label: 'Cache',      value: '—', color: 'text-slate-400', bg: 'bg-slate-100', border: 'border-slate-200', active: false },
      { label: 'Classifier', value: '—', color: 'text-slate-400', bg: 'bg-slate-100', border: 'border-slate-200', active: false },
      { label: 'Model',      value: '—', color: 'text-slate-400', bg: 'bg-slate-100', border: 'border-slate-200', active: false },
      { label: 'Risk',       value: '—', color: 'text-slate-400', bg: 'bg-slate-100', border: 'border-slate-200', active: false },
    ]
  }

  const cacheHit = response.routing_decision.cache_hit
  const score = response.complexity_score ?? 0
  const risk = response.risk_level ?? 'SAFE'
  const model = response.model_used
  const complexityStyle = complexityColor(score)
  const riskStyle = RISK_STYLE[risk] ?? RISK_STYLE.SAFE
  const modelColor = MODEL_COLORS[model] ?? '#6b7280'

  const modelShort = (() => {
    if (model.startsWith('llama')) return 'Llama'
    if (model.startsWith('gemini')) return 'Gemini'
    if (model === 'gpt-4o-mini') return 'GPT-mini'
    if (model === 'gpt-4o') return 'GPT-4o'
    if (model.startsWith('claude')) return 'Claude'
    return model.split('-')[0]
  })()

  return [
    {
      label: 'Input',
      value: '✓',
      color: 'text-slate-700',
      bg: 'bg-slate-100',
      border: 'border-slate-200',
      active: true,
    },
    {
      label: 'Security',
      value: '✓ Pass',
      color: 'text-emerald-700',
      bg: 'bg-emerald-100',
      border: 'border-emerald-200',
      active: true,
    },
    {
      label: 'Cache',
      value: cacheHit ? 'HIT' : 'MISS',
      color: cacheHit ? 'text-amber-700' : 'text-slate-500',
      bg: cacheHit ? 'bg-amber-100' : 'bg-slate-100',
      border: cacheHit ? 'border-amber-200' : 'border-slate-200',
      active: true,
    },
    {
      label: 'Classifier',
      value: score.toFixed(2),
      color: complexityStyle.text,
      bg: complexityStyle.bg,
      border: complexityStyle.border,
      active: !cacheHit,
    },
    {
      label: response.routing_decision.reason.toLowerCase().includes('domain override') ||
             response.routing_decision.reason.toLowerCase().includes('hard-routed')
               ? 'Forced ⚡'
               : 'Model',
      value: modelShort,
      color: 'text-slate-900',
      bg: modelColor + '18',
      border: modelColor + '44',
      active: true,
    },
    {
      label: 'Risk',
      value: risk,
      color: riskStyle.text,
      bg: riskStyle.bg,
      border: riskStyle.border,
      active: true,
    },
  ]
}

export function RoutingFlow({ response }: Props) {
  const steps = buildSteps(response)

  return (
    <div className="bg-white border border-[#E5E2DC] shadow-sm rounded-xl p-4">
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Decision Pipeline</h3>
        {!response && (
          <span className="text-[10px] text-slate-400">Awaiting request</span>
        )}
      </div>
      <p className="text-[10px] text-slate-400 mb-3">
        Live trace of security, deduplication, complexity routing, and reliability verification stages.
      </p>
      <div className="flex items-center gap-1 overflow-x-auto pb-1">
        {steps.map((step, i) => (
          <div key={step.label} className="flex items-center gap-1">
            {/* Step pill */}
            <div
              className={`flex flex-col items-center px-2.5 py-1.5 rounded-lg border text-center transition-all duration-300 min-w-[56px] ${
                step.active ? `${step.bg} ${step.border}` : 'bg-slate-100 border-slate-200 opacity-40'
              }`}
              style={{ transitionDelay: `${i * 60}ms` }}
            >
              <span className="text-xs text-slate-400 leading-none mb-0.5">{step.label}</span>
              <span className={`text-xs font-semibold leading-none ${step.active ? step.color : 'text-slate-400'}`}>
                {step.value}
              </span>
            </div>
            {/* Arrow connector */}
            {i < steps.length - 1 && (
              <span className={`text-xs ${step.active ? 'text-slate-400' : 'text-slate-300'}`}>›</span>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

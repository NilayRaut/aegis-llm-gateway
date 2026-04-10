import { LLMResponse, MODEL_COLORS } from '../types'

interface Props {
  response: LLMResponse | null
}

interface Step {
  label: string
  value: string
  color: string    // Tailwind text color
  bg: string       // Tailwind bg color
  border: string   // Tailwind border color
  active: boolean
}

function complexityColor(score: number): { text: string; bg: string; border: string } {
  if (score < 0.35) return { text: 'text-emerald-300', bg: 'bg-emerald-900/40', border: 'border-emerald-600/50' }
  if (score < 0.65) return { text: 'text-amber-300',   bg: 'bg-amber-900/40',   border: 'border-amber-600/50' }
  return              { text: 'text-red-300',     bg: 'bg-red-900/40',     border: 'border-red-600/50' }
}

const RISK_STYLE: Record<string, { text: string; bg: string; border: string }> = {
  SAFE:   { text: 'text-emerald-300', bg: 'bg-emerald-900/40', border: 'border-emerald-600/50' },
  MEDIUM: { text: 'text-amber-300',   bg: 'bg-amber-900/40',   border: 'border-amber-600/50' },
  HIGH:   { text: 'text-red-300',     bg: 'bg-red-900/40',     border: 'border-red-600/50' },
}

function buildSteps(response: LLMResponse | null): Step[] {
  if (!response) {
    return [
      { label: 'Input',      value: '—',       color: 'text-slate-400', bg: 'bg-slate-800/40',  border: 'border-slate-700/40', active: false },
      { label: 'Security',   value: '—',       color: 'text-slate-400', bg: 'bg-slate-800/40',  border: 'border-slate-700/40', active: false },
      { label: 'Cache',      value: '—',       color: 'text-slate-400', bg: 'bg-slate-800/40',  border: 'border-slate-700/40', active: false },
      { label: 'Classifier', value: '—',       color: 'text-slate-400', bg: 'bg-slate-800/40',  border: 'border-slate-700/40', active: false },
      { label: 'Model',      value: '—',       color: 'text-slate-400', bg: 'bg-slate-800/40',  border: 'border-slate-700/40', active: false },
      { label: 'Risk',       value: '—',       color: 'text-slate-400', bg: 'bg-slate-800/40',  border: 'border-slate-700/40', active: false },
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
      color: 'text-slate-300',
      bg: 'bg-slate-800/60',
      border: 'border-slate-600/50',
      active: true,
    },
    {
      label: 'Security',
      value: '✓ Pass',
      color: 'text-emerald-300',
      bg: 'bg-emerald-900/30',
      border: 'border-emerald-700/50',
      active: true,
    },
    {
      label: 'Cache',
      value: cacheHit ? 'HIT' : 'MISS',
      color: cacheHit ? 'text-amber-300' : 'text-slate-400',
      bg: cacheHit ? 'bg-amber-900/30' : 'bg-slate-800/40',
      border: cacheHit ? 'border-amber-700/50' : 'border-slate-700/40',
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
      label: 'Model',
      value: modelShort,
      color: 'text-white',
      bg: modelColor + '22',
      border: modelColor + '55',
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
    <div className="bg-slate-800/40 backdrop-blur-sm rounded-xl border border-white/5 ring-1 ring-white/5 p-5">
      <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-4">Routing Pipeline</h3>
      <div className="flex items-center gap-1 overflow-x-auto pb-1">
        {steps.map((step, i) => (
          <div key={step.label} className="flex items-center gap-1">
            {/* Step pill */}
            <div
              className={`flex flex-col items-center px-2.5 py-1.5 rounded-lg border text-center transition-all duration-300 min-w-[56px] ${
                step.active ? `${step.bg} ${step.border}` : 'bg-slate-900/30 border-slate-800/40 opacity-40'
              }`}
              style={{ transitionDelay: `${i * 60}ms` }}
            >
              <span className="text-xs text-slate-500 leading-none mb-0.5">{step.label}</span>
              <span className={`text-xs font-semibold leading-none ${step.active ? step.color : 'text-slate-600'}`}>
                {step.value}
              </span>
            </div>
            {/* Arrow connector */}
            {i < steps.length - 1 && (
              <span className={`text-xs ${step.active ? 'text-slate-500' : 'text-slate-700'}`}>›</span>
            )}
          </div>
        ))}
      </div>
      {!response && (
        <p className="text-xs text-slate-600 mt-3">Send a prompt to see the routing pipeline.</p>
      )}
    </div>
  )
}

import { TrendingDown, Zap, AlertTriangle, Shield, Play } from 'lucide-react'

interface Props {
  onStartTour: () => void
}

const FEATURES = [
  {
    icon: TrendingDown,
    color: 'text-emerald-400',
    bg: 'bg-emerald-900/20',
    border: 'border-emerald-800/40',
    title: 'Cost Routing',
    desc: 'Scores complexity 0–1 and routes to the cheapest capable model — free Llama to GPT-4o.',
  },
  {
    icon: AlertTriangle,
    color: 'text-amber-400',
    bg: 'bg-amber-900/20',
    border: 'border-amber-800/40',
    title: 'Hallucination Detection',
    desc: 'Paraphrases your prompt 2×, compares responses at temp=0. Variance > θ=0.35 → flagged.',
  },
  {
    icon: Shield,
    color: 'text-red-400',
    bg: 'bg-red-900/20',
    border: 'border-red-800/40',
    title: 'Security Gate',
    desc: 'Blocks PII and injection attempts before any model call. Legal/medical/financial → always GPT-4o.',
  },
  {
    icon: Zap,
    color: 'text-blue-400',
    bg: 'bg-blue-900/20',
    border: 'border-blue-800/40',
    title: 'Semantic Cache',
    desc: 'Embeds every query with all-MiniLM-L6-v2. Same question twice = ≤5ms, $0.00.',
  },
]

export function EmptyState({ onStartTour }: Props) {
  return (
    <div className="space-y-4">
      {/* Feature cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {FEATURES.map(({ icon: Icon, color, bg, border, title, desc }) => (
          <div
            key={title}
            className={`${bg} border ${border} rounded-xl p-4 hover:-translate-y-0.5 transition-transform duration-200`}
          >
            <div className="flex items-center gap-2 mb-2">
              <Icon className={`w-4 h-4 ${color} flex-shrink-0`} />
              <p className={`text-sm font-semibold ${color}`}>{title}</p>
            </div>
            <p className="text-xs text-slate-400 leading-relaxed">{desc}</p>
          </div>
        ))}
      </div>

      {/* Tour CTA */}
      <div className="text-center py-2">
        <button
          onClick={onStartTour}
          className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium px-5 py-2.5 rounded-xl transition-colors"
        >
          <Play className="w-3.5 h-3.5" />
          Run the 5-step demo tour
        </button>
        <p className="text-xs text-slate-600 mt-2">or type your own prompt below</p>
      </div>
    </div>
  )
}

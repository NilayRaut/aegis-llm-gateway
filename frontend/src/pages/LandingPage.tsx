import { useNavigate } from 'react-router-dom'
import { Shield, TrendingDown, Zap, AlertTriangle, Play, ArrowRight } from 'lucide-react'
import { AegisLogo } from '../components/AegisLogo'

const STATS = [
  { value: '5', label: 'LLM providers' },
  { value: '≤5ms', label: 'cache hit latency' },
  { value: 'θ=0.35', label: 'hallucination threshold' },
  { value: '7', label: 'pipeline stages' },
]

const PIPELINE_STEPS = [
  { num: 1, title: 'Security Gate', desc: 'Regex PII scan + injection pattern match. Blocks before any API call — zero cost, zero leak.' },
  { num: 2, title: 'Semantic Cache', desc: 'Embeds the query with all-MiniLM-L6-v2. Cosine similarity ≥ 0.85 returns the cached response in ≤5ms.' },
  { num: 3, title: 'Complexity Scoring', desc: '4-factor weighted score (vocab richness, structure, question type, domain). Maps 0.00 → 1.00.' },
  { num: 4, title: 'Domain Hard Gate', desc: 'Legal, medical, or financial query? Always routed to GPT-4o — complexity score cannot override this.' },
  { num: 5, title: 'LLM Call', desc: 'Lowest-cost capable model selected: Llama 3.1 (free) → Gemini 2.5 Flash → Claude Haiku → GPT-4o-mini → GPT-4o.' },
  { num: 6, title: 'Hallucination Check', desc: 'Pearl Rung 2 intervention — do(rephrase(X)). Two paraphrases generated at temp=0. Variance > θ=0.35 → HIGH risk flag.' },
  { num: 7, title: 'Response + Audit Log', desc: 'Model response returned with cost, latency, risk level, and routing rationale. Every request logged to SQLite.' },
]

const FEATURE_CARDS = [
  {
    icon: TrendingDown,
    color: 'text-emerald-600',
    bg: 'bg-emerald-50',
    border: 'border-emerald-200',
    title: 'Cost Routing',
    desc: 'Scores complexity across 4 weighted factors. Routes simple queries to free Llama 3.1, complex ones to GPT-4o. 40–60% estimated cost reduction vs. always-GPT-4o.',
  },
  {
    icon: Zap,
    color: 'text-blue-600',
    bg: 'bg-blue-50',
    border: 'border-blue-200',
    title: 'Semantic Cache',
    desc: 'Embeds every query. Paraphrased duplicates hit the cache just like exact matches — cosine similarity ≥ 0.85. Same question twice = $0.00.',
  },
  {
    icon: AlertTriangle,
    color: 'text-amber-600',
    bg: 'bg-amber-50',
    border: 'border-amber-200',
    title: 'Hallucination Detection',
    desc: 'Generates two paraphrases of your prompt, runs all three at temperature=0, embeds the responses, and measures variance. Unstable answers are flagged — not guessed.',
  },
  {
    icon: Shield,
    color: 'text-red-600',
    bg: 'bg-red-50',
    border: 'border-red-200',
    title: 'Security Gate',
    desc: 'Deterministic regex detects PII (email, SSN, phone) and prompt injection patterns before any LLM call. Sensitive domains hard-routed to the safest model, unconditionally.',
  },
]

export function LandingPage() {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-[#F8F7F4] text-slate-900">
      {/* Nav */}
      <nav className="sticky top-0 z-20 border-b border-[#E5E2DC] bg-white/95 backdrop-blur-md shadow-sm">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AegisLogo size={24} />
            <span className="font-bold text-slate-900 tracking-tight text-lg font-heading">Aegis</span>
          </div>
          <button
            onClick={() => navigate('/app')}
            className="flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-900 border border-slate-300 hover:border-slate-400 px-4 py-2 rounded-lg transition-colors"
          >
            Open App <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </nav>

      {/* Hero */}
      <section className="max-w-5xl mx-auto px-6 pt-20 pb-16 text-center">
        <p className="text-xs font-semibold text-emerald-600 uppercase tracking-widest mb-5">
          Agentic LLM Gateway
        </p>
        <h1 className="text-4xl sm:text-5xl font-bold leading-tight mb-6 tracking-tight font-heading">
          Route every prompt to the{' '}
          <span className="bg-gradient-to-r from-emerald-600 to-blue-600 bg-clip-text text-transparent">
            right model, automatically.
          </span>
        </h1>
        <p className="text-lg text-slate-600 max-w-2xl mx-auto mb-10 leading-relaxed">
          Aegis scores complexity, blocks threats, detects hallucinations, and eliminates
          duplicate costs — before the user sees a single token.
        </p>

        {/* CTAs */}
        <div className="flex flex-wrap gap-3 justify-center mb-10">
          <button
            onClick={() => navigate('/app', { state: { startTour: true } })}
            className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white px-6 py-3 rounded-xl font-semibold transition-colors shadow-sm"
          >
            <Play className="w-4 h-4" /> Start Demo Tour
          </button>
          <button
            onClick={() => navigate('/app')}
            className="flex items-center gap-2 border border-slate-300 hover:border-slate-400 text-slate-600 hover:text-slate-900 px-6 py-3 rounded-xl font-semibold transition-colors"
          >
            Open App <ArrowRight className="w-4 h-4" />
          </button>
        </div>

        {/* Feature pills */}
        <div className="flex flex-wrap gap-2 justify-center">
          {['Cost Routing', 'Semantic Cache', 'Hallucination Detection', 'Security Gate', 'DoWhy Causal Analysis'].map((pill) => (
            <span
              key={pill}
              className="text-xs px-3 py-1 rounded-full bg-white border border-[#E5E2DC] text-slate-500 shadow-sm"
            >
              {pill}
            </span>
          ))}
        </div>
      </section>

      {/* Stats strip */}
      <div className="border-y border-[#E5E2DC] bg-white">
        <div className="max-w-5xl mx-auto px-6 py-10 grid grid-cols-2 sm:grid-cols-4 gap-8 text-center">
          {STATS.map(({ value, label }) => (
            <div key={label}>
              <p className="text-3xl font-bold text-slate-900 mb-1 font-mono">{value}</p>
              <p className="text-xs text-slate-500 uppercase tracking-wide">{label}</p>
            </div>
          ))}
        </div>
      </div>

      {/* How it works + Feature cards (two-column on desktop) */}
      <section className="max-w-5xl mx-auto px-6 py-16">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12">
          {/* Pipeline */}
          <div>
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-2">The Pipeline</p>
            <h2 className="text-2xl font-bold text-slate-900 mb-8 font-heading">How every request flows through Aegis</h2>
            <div className="space-y-5">
              {PIPELINE_STEPS.map(({ num, title, desc }) => (
                <div key={num} className="flex gap-4">
                  <div className="w-7 h-7 rounded-full bg-white border border-[#E5E2DC] shadow-sm flex items-center justify-center text-xs font-bold text-slate-600 flex-shrink-0 mt-0.5">
                    {num}
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-slate-900 mb-0.5">{title}</p>
                    <p className="text-xs text-slate-500 leading-relaxed">{desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Feature cards */}
          <div>
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-2">Capabilities</p>
            <h2 className="text-2xl font-bold text-slate-900 mb-8 font-heading">Four systems, one pipeline</h2>
            <div className="grid grid-cols-1 gap-4">
              {FEATURE_CARDS.map(({ icon: Icon, color, bg, border, title, desc }) => (
                <div
                  key={title}
                  className={`${bg} border ${border} rounded-xl p-5 hover:-translate-y-0.5 transition-transform duration-200`}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <Icon className={`w-4 h-4 ${color} flex-shrink-0`} />
                    <p className={`text-sm font-semibold ${color}`}>{title}</p>
                  </div>
                  <p className="text-xs text-slate-600 leading-relaxed">{desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Bottom CTA */}
      <div className="border-t border-[#E5E2DC] bg-white">
        <div className="max-w-5xl mx-auto px-6 py-14 text-center">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-3">See it live</p>
          <h2 className="text-2xl font-bold text-slate-900 mb-3 font-heading">Run the 5-step demo in under 2 minutes</h2>
          <p className="text-slate-500 text-sm mb-8 max-w-lg mx-auto">
            Simple routing → domain hard gate → semantic cache hit → hallucination flag → injection block.
            Each step auto-submits and shows you exactly what fired.
          </p>
          <button
            onClick={() => navigate('/app', { state: { startTour: true } })}
            className="inline-flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white px-8 py-3.5 rounded-xl font-semibold transition-colors text-sm shadow-sm"
          >
            <Play className="w-4 h-4" /> Start Demo Tour
          </button>
        </div>
      </div>

      {/* Footer */}
      <footer className="border-t border-[#E5E2DC] bg-white">
        <div className="max-w-5xl mx-auto px-6 py-6 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AegisLogo size={16} />
            <span className="text-sm text-slate-400">Aegis — INFO 7390 · Spring 2026</span>
          </div>
          <span className="text-xs text-slate-300">LangGraph · FastAPI · React · Vercel · Render</span>
        </div>
      </footer>
    </div>
  )
}

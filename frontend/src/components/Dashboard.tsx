import { TrendingDown, Clock, Shield, BarChart3 } from 'lucide-react'
import { DashboardStats } from '../types'

interface Props {
  stats: DashboardStats | null
}

export function Dashboard({ stats }: Props) {
  const modelDist = stats?.model_distribution ?? {}
  const totalRequests = Object.values(modelDist).reduce((a, b) => a + b, 0)
  const modelPct = (count: number) =>
    totalRequests > 0 ? Math.round((count / totalRequests) * 100) : 0

  return (
    <div className="space-y-6">
      <div className="bg-slate-800/50 rounded-xl p-6 border border-slate-700">
        <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-emerald-400" />
          Dashboard
        </h2>

        <div className="grid grid-cols-2 gap-4">
          <div className="bg-slate-900/50 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <TrendingDown className="w-4 h-4 text-emerald-400" />
              <span className="text-xs text-slate-400">Cost Savings</span>
            </div>
            <p className="text-2xl font-bold text-emerald-400">
              ${stats ? stats.cost_savings.toFixed(4) : '0.0000'}
            </p>
            <p className="text-xs text-slate-500">vs GPT-4o only</p>
          </div>

          <div className="bg-slate-900/50 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <Clock className="w-4 h-4 text-blue-400" />
              <span className="text-xs text-slate-400">Avg Latency</span>
            </div>
            <p className="text-2xl font-bold text-white">
              {stats ? stats.avg_latency_ms : 0}ms
            </p>
          </div>

          <div className="bg-slate-900/50 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <Shield className="w-4 h-4 text-amber-400" />
              <span className="text-xs text-slate-400">Risk Checks</span>
            </div>
            <p className="text-2xl font-bold text-amber-400">
              {stats ? stats.hallucinations_caught : 0}
            </p>
          </div>

          <div className="bg-slate-900/50 rounded-lg p-4">
            <p className="text-xs text-slate-400 mb-2">Cache Hit Rate</p>
            <p className="text-2xl font-bold text-white">
              {stats ? stats.cache_hit_rate.toFixed(1) : '0.0'}%
            </p>
          </div>
        </div>

        <div className="mt-6">
          <h3 className="text-sm font-medium text-slate-400 mb-3">Model Distribution</h3>
          <div className="space-y-2">
            {Object.entries(modelDist).map(([model, count]) => {
              const pct = modelPct(count)
              return (
                <div key={model} className="flex items-center gap-3">
                  <span className="text-xs text-slate-500 w-32 font-mono truncate">{model}</span>
                  <div className="flex-1 bg-slate-900 rounded-full h-2">
                    <div
                      className="bg-emerald-500 h-2 rounded-full transition-all duration-500"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="text-xs text-slate-400 w-10 text-right">{pct}%</span>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      <div className="bg-slate-800/50 rounded-xl p-6 border border-slate-700">
        <h2 className="text-lg font-semibold text-white mb-4">How It Works</h2>
        <div className="space-y-3 text-sm text-slate-300">
          <div className="flex items-start gap-3">
            <span className="bg-red-700 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center flex-shrink-0">1</span>
            <p><strong className="text-slate-200">Security gate</strong> — blocks PII, injection attempts, hard-routes legal/medical/financial to GPT-4o</p>
          </div>
          <div className="flex items-start gap-3">
            <span className="bg-blue-700 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center flex-shrink-0">2</span>
            <p><strong className="text-slate-200">Semantic cache</strong> — returns cached answer if similarity ≥ 85% (zero cost)</p>
          </div>
          <div className="flex items-start gap-3">
            <span className="bg-emerald-600 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center flex-shrink-0">3</span>
            <p><strong className="text-slate-200">Complexity routing</strong> — 5-tier model pool: Llama-3.1 → Gemini → GPT-4o-mini → Claude → GPT-4o</p>
          </div>
          <div className="flex items-start gap-3">
            <span className="bg-amber-600 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center flex-shrink-0">4</span>
            <p><strong className="text-slate-200">Causal risk check</strong> — variance threshold θ=0.35 calibrated via DoWhy on 1,000 synthetic tuples</p>
          </div>
        </div>
      </div>
    </div>
  )
}

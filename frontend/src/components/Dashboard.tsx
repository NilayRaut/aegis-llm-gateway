import { TrendingDown, Clock, Shield, BarChart3, Zap } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  AreaChart, Area, PieChart, Pie,
} from 'recharts'
import { DashboardStats, HistoryItem, MODEL_COLORS } from '../types'

interface Props {
  stats: DashboardStats | null
  history: HistoryItem[]
}

// Shorten model name for chart axis labels
function shortModel(m: string): string {
  if (m.startsWith('llama')) return 'Llama'
  if (m.startsWith('gemini')) return 'Gemini'
  if (m === 'gpt-4o-mini') return 'GPT-4o-mini'
  if (m === 'gpt-4o') return 'GPT-4o'
  if (m.startsWith('claude')) return 'Claude'
  return m.split('-')[0]
}

const RISK_COLORS: Record<string, string> = {
  SAFE:   '#10b981',
  MEDIUM: '#f59e0b',
  HIGH:   '#ef4444',
}

const TooltipStyle = {
  contentStyle: { background: '#1e293b', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, fontSize: 11 },
  labelStyle: { color: '#94a3b8' },
  itemStyle: { color: '#e2e8f0' },
}

export function Dashboard({ stats, history }: Props) {
  // ── Chart A: Model Distribution ───────────────────────────────────────────
  const modelDist = stats?.model_distribution ?? {}
  const modelChartData = Object.entries(modelDist)
    .filter(([, cnt]) => cnt > 0)
    .map(([model, count]) => ({ model: shortModel(model), fullModel: model, count }))

  // ── Chart B: Cost Over Time (cumulative savings) ───────────────────────────
  const GPT4O_BASELINE = 0.0025
  let cumulativeSavings = 0
  const costChartData = [...history].reverse().map((item, idx) => {
    cumulativeSavings += GPT4O_BASELINE - item.response.cost
    return { idx: idx + 1, savings: Math.max(0, parseFloat(cumulativeSavings.toFixed(4))) }
  })

  // ── Chart C: Latency by Model ──────────────────────────────────────────────
  const latencyMap: Record<string, { total: number; count: number }> = {}
  history.forEach((item) => {
    const m = item.response.model_used
    if (!latencyMap[m]) latencyMap[m] = { total: 0, count: 0 }
    latencyMap[m].total += item.response.latency_ms
    latencyMap[m].count += 1
  })
  const latencyChartData = Object.entries(latencyMap).map(([model, { total, count }]) => ({
    model: shortModel(model),
    fullModel: model,
    avgLatency: Math.round(total / count),
  }))

  // ── Chart D: Risk Breakdown Donut ─────────────────────────────────────────
  const riskCounts: Record<string, number> = { SAFE: 0, MEDIUM: 0, HIGH: 0 }
  history.forEach((item) => {
    const r = item.response.risk_level ?? 'SAFE'
    riskCounts[r] = (riskCounts[r] ?? 0) + 1
  })
  const riskChartData = Object.entries(riskCounts)
    .filter(([, v]) => v > 0)
    .map(([name, value]) => ({ name, value }))

  return (
    <div className="w-[360px] flex-shrink-0 space-y-4 overflow-y-auto">
      {/* ── KPI Cards ─────────────────────────────────────────────────── */}
      <div className="bg-slate-800/40 backdrop-blur-sm rounded-xl border border-white/5 ring-1 ring-white/5 p-5">
        <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-4 flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-emerald-400" />
          Dashboard
        </h2>

        <div className="grid grid-cols-2 gap-3">
          <div className="bg-slate-900/50 rounded-lg p-3">
            <div className="flex items-center gap-1.5 mb-1">
              <TrendingDown className="w-3.5 h-3.5 text-emerald-400" />
              <span className="text-xs text-slate-400">Cost Saved</span>
            </div>
            <p className="text-xl font-bold text-emerald-400">
              ${stats ? stats.cost_savings.toFixed(4) : '0.0000'}
            </p>
            <p className="text-xs text-slate-600 mt-0.5">vs GPT-4o only</p>
          </div>

          <div className="bg-slate-900/50 rounded-lg p-3">
            <div className="flex items-center gap-1.5 mb-1">
              <Clock className="w-3.5 h-3.5 text-blue-400" />
              <span className="text-xs text-slate-400">Avg Latency</span>
            </div>
            <p className="text-xl font-bold text-white">{stats ? stats.avg_latency_ms : 0}ms</p>
          </div>

          <div className="bg-slate-900/50 rounded-lg p-3">
            <div className="flex items-center gap-1.5 mb-1">
              <Shield className="w-3.5 h-3.5 text-amber-400" />
              <span className="text-xs text-slate-400">Risk Checks</span>
            </div>
            <p className="text-xl font-bold text-amber-400">{stats ? stats.hallucinations_caught : 0}</p>
          </div>

          <div className="bg-slate-900/50 rounded-lg p-3">
            <div className="flex items-center gap-1.5 mb-1">
              <Zap className="w-3.5 h-3.5 text-violet-400" />
              <span className="text-xs text-slate-400">Cache Hit</span>
            </div>
            <p className="text-xl font-bold text-white">{stats ? stats.cache_hit_rate.toFixed(1) : '0.0'}%</p>
          </div>
        </div>
      </div>

      {/* ── Chart A: Model Distribution ───────────────────────────────── */}
      <div className="bg-slate-800/40 backdrop-blur-sm rounded-xl border border-white/5 ring-1 ring-white/5 p-5">
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Model Distribution</h3>
        {modelChartData.length === 0 ? (
          <p className="text-xs text-slate-600 text-center py-8">No data yet</p>
        ) : (
          <div style={{ height: 180 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={modelChartData} margin={{ top: 4, right: 8, bottom: 36, left: -16 }}>
                <XAxis dataKey="model" tick={{ fontSize: 10, fill: '#64748b' }} angle={-30} textAnchor="end" interval={0} />
                <YAxis tick={{ fontSize: 10, fill: '#64748b' }} allowDecimals={false} />
                <Tooltip {...TooltipStyle} formatter={(v: number) => [v, 'Requests']} />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {modelChartData.map((entry) => (
                    <Cell key={entry.fullModel} fill={MODEL_COLORS[entry.fullModel] ?? '#6b7280'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* ── Chart B: Cumulative Cost Savings ──────────────────────────── */}
      <div className="bg-slate-800/40 backdrop-blur-sm rounded-xl border border-white/5 ring-1 ring-white/5 p-5">
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Cumulative Savings vs GPT-4o</h3>
        {costChartData.length < 2 ? (
          <p className="text-xs text-slate-600 text-center py-8">Need ≥2 requests</p>
        ) : (
          <div style={{ height: 140 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={costChartData} margin={{ top: 4, right: 8, bottom: 4, left: -16 }}>
                <XAxis dataKey="idx" tick={{ fontSize: 10, fill: '#64748b' }} label={{ value: 'Request #', position: 'insideBottom', offset: -2, fontSize: 10, fill: '#475569' }} />
                <YAxis tick={{ fontSize: 10, fill: '#64748b' }} />
                <Tooltip {...TooltipStyle} formatter={(v: number) => [`$${v.toFixed(4)}`, 'Saved']} />
                <defs>
                  <linearGradient id="savingsGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <Area type="monotone" dataKey="savings" stroke="#10b981" strokeWidth={2} fill="url(#savingsGrad)" dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* ── Chart C: Avg Latency by Model ─────────────────────────────── */}
      <div className="bg-slate-800/40 backdrop-blur-sm rounded-xl border border-white/5 ring-1 ring-white/5 p-5">
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Avg Latency by Model</h3>
        {latencyChartData.length === 0 ? (
          <p className="text-xs text-slate-600 text-center py-8">No data yet</p>
        ) : (
          <div style={{ height: 180 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={latencyChartData} margin={{ top: 4, right: 8, bottom: 36, left: -8 }}>
                <XAxis dataKey="model" tick={{ fontSize: 10, fill: '#64748b' }} angle={-30} textAnchor="end" interval={0} />
                <YAxis tick={{ fontSize: 10, fill: '#64748b' }} unit="ms" />
                <Tooltip {...TooltipStyle} formatter={(v: number) => [`${v}ms`, 'Avg Latency']} />
                <Bar dataKey="avgLatency" radius={[4, 4, 0, 0]}>
                  {latencyChartData.map((entry) => (
                    <Cell key={entry.fullModel} fill={MODEL_COLORS[entry.fullModel] ?? '#3b82f6'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* ── Chart D: Risk Breakdown Donut ─────────────────────────────── */}
      <div className="bg-slate-800/40 backdrop-blur-sm rounded-xl border border-white/5 ring-1 ring-white/5 p-5">
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Risk Breakdown</h3>
        {riskChartData.length === 0 ? (
          <p className="text-xs text-slate-600 text-center py-8">No data yet</p>
        ) : (
          <div style={{ height: 160 }} className="relative">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={riskChartData}
                  cx="50%"
                  cy="50%"
                  innerRadius={44}
                  outerRadius={64}
                  paddingAngle={3}
                  dataKey="value"
                  label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  labelLine={false}
                >
                  {riskChartData.map((entry) => (
                    <Cell key={entry.name} fill={RISK_COLORS[entry.name] ?? '#6b7280'} />
                  ))}
                </Pie>
                <Tooltip {...TooltipStyle} formatter={(v: number) => [v, 'Requests']} />
              </PieChart>
            </ResponsiveContainer>
            {/* Center label */}
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="text-center">
                <p className="text-lg font-bold text-white">{history.length}</p>
                <p className="text-xs text-slate-500">total</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

import { TrendingDown, Shield, CheckCircle, AlertTriangle, Activity, ShieldAlert } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, Cell,
  AreaChart, Area, PieChart, Pie,
} from 'recharts'
import { DashboardStats, HistoryItem, ProviderHealth, ProviderTestResult, SecurityEvent, MODEL_COLORS } from '../types'

interface Props {
  stats: DashboardStats | null
  history: HistoryItem[]
  providerHealth: ProviderHealth[]
  providerTest: Record<string, ProviderTestResult>
  securityEvents: SecurityEvent[]
}

const TEST_BADGE: Record<string, { label: string; cls: string }> = {
  ok:             { label: 'LIVE',     cls: 'bg-emerald-900/60 text-emerald-400 border border-emerald-700/50' },
  not_configured: { label: 'NO KEY',  cls: 'bg-slate-700/60 text-slate-500 border border-slate-600/40' },
  auth_error:     { label: 'AUTH ERR', cls: 'bg-red-900/50 text-red-400 border border-red-700/50' },
  unavailable:    { label: 'UNAVAIL', cls: 'bg-amber-900/40 text-amber-400 border border-amber-700/50' },
  pending:        { label: '...',     cls: 'bg-slate-700/40 text-slate-500 border border-slate-600/40' },
}

// Shorten model name for chart axis labels
function shortModel(m: string): string {
  if (m.startsWith('llama')) return 'Llama'
  if (m.startsWith('gemini')) return 'Gemini'
  if (m === 'gpt-4o-mini') return 'GPT-mini'
  if (m === 'gpt-4o') return 'GPT-4o'
  if (m.startsWith('claude')) return 'Claude'
  return m.split('-')[0]
}

const RISK_COLORS: Record<string, string> = {
  SAFE:   '#10b981',
  MEDIUM: '#f59e0b',
  HIGH:   '#ef4444',
}

const PROVIDER_DISPLAY: Record<string, string> = {
  openai:    'OpenAI',
  anthropic: 'Anthropic',
  google:    'Google',
  groq:      'Groq',
  ollama:    'Ollama',
}

const TooltipStyle = {
  contentStyle: { background: '#1e293b', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, fontSize: 11 },
  labelStyle: { color: '#94a3b8' },
  itemStyle: { color: '#e2e8f0' },
}

const GPT4O_BASELINE = 0.0025

export function Dashboard({ stats, history, providerHealth, providerTest, securityEvents }: Props) {
  // ── Panel A: Live Routing Trace (latest query) ─────────────────────────────
  const latest = history[0] ?? null

  // ── Savings Accumulator data ───────────────────────────────────────────────
  const totalQueries = stats?.total_requests ?? 0
  const cacheHitRate = stats?.cache_hit_rate ?? 0
  const cumulativeSavings = stats?.cost_savings ?? 0
  const reliabilityFlags = stats?.hallucinations_caught ?? 0

  const totalBaseline = totalQueries * GPT4O_BASELINE
  const actualCost = Math.max(totalBaseline - cumulativeSavings, 0)
  const savingsPct = totalBaseline > 0
    ? Math.round((cumulativeSavings / totalBaseline) * 100)
    : 0

  // ── Chart: Model Distribution ──────────────────────────────────────────────
  const modelTotals: Record<string, { count: number; cost: number }> = {}
  history.forEach((item) => {
    const label = shortModel(item.response.model_used)
    if (!modelTotals[label]) modelTotals[label] = { count: 0, cost: 0 }
    modelTotals[label].count += 1
    modelTotals[label].cost += item.response.cost
  })
  const totalHist = history.length
  const totalCost = Object.values(modelTotals).reduce((s, { cost }) => s + cost, 0)
  const modelChartData = Object.entries(modelTotals)
    .filter(([, { count }]) => count > 0)
    .map(([model, { count, cost }]) => ({
      model,
      requestPct: totalHist > 0 ? Math.round((count / totalHist) * 100) : 0,
      costPct: totalCost > 0 ? Math.round((cost / totalCost) * 100) : 0,
    }))

  // ── Chart: Cumulative savings over time ────────────────────────────────────
  let cumSavings = 0
  const costChartData = [...history].reverse().map((item, idx) => {
    cumSavings += GPT4O_BASELINE - item.response.cost
    return { idx: idx + 1, savings: Math.max(0, parseFloat(cumSavings.toFixed(4))) }
  })

  // ── Chart: Latency by model ────────────────────────────────────────────────
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

  // ── Chart: Risk donut ──────────────────────────────────────────────────────
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

      {/* ── A: Live Routing Trace ─────────────────────────────────────────── */}
      <div className="bg-slate-800/40 backdrop-blur-sm rounded-xl border border-white/5 ring-1 ring-white/5 p-4">
        <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-0.5 flex items-center gap-2">
          <Activity className="w-3.5 h-3.5 text-emerald-400" />
          Live Routing Trace
        </h2>
        <p className="text-[10px] text-slate-600 mb-3">
          Decision audit for the most recent request — confidence, model selection rationale, and cost delta.
        </p>

        {!latest ? (
          <p className="text-xs text-slate-600 text-center py-6">Send a prompt to see the routing trace.</p>
        ) : (() => {
          const r = latest.response
          const complexity = r.complexity_score ?? 0
          const confidence = r.routing_decision.confidence
          const cacheHit = r.routing_decision.cache_hit
          const hallucCheck = r.causal_analysis
          const actualCostQ = r.cost
          const savings = GPT4O_BASELINE - actualCostQ
          const savingsPctQ = savings > 0 ? Math.round((savings / GPT4O_BASELINE) * 100) : 0

          const complexityLabel = complexity < 0.45 ? 'Low' : complexity < 0.65 ? 'Moderate' : 'High'
          const complexityColor = complexity < 0.45 ? 'text-emerald-400' : complexity < 0.65 ? 'text-amber-400' : 'text-red-400'

          return (
            <div className="space-y-2 text-xs">
              {/* Confidence + complexity */}
              <div className="flex gap-2">
                <div className="flex-1 bg-slate-900/60 rounded-lg p-2.5">
                  <p className="text-slate-500 mb-1 text-[10px]">Routing Confidence</p>
                  <p className="text-white font-semibold">{(confidence * 100).toFixed(0)}%</p>
                </div>
                <div className="flex-1 bg-slate-900/60 rounded-lg p-2.5">
                  <p className="text-slate-500 mb-1 text-[10px]">Complexity Band</p>
                  <p className={`font-semibold ${complexityColor}`}>{complexityLabel} ({complexity.toFixed(2)})</p>
                </div>
              </div>

              {/* Model + why */}
              <div className="bg-slate-900/60 rounded-lg p-2.5">
                <p className="text-slate-500 mb-1 text-[10px]">Optimal Model (cost-adjusted)</p>
                <p className="font-mono font-medium" style={{ color: MODEL_COLORS[r.model_used] ?? '#94a3b8' }}>
                  {r.model_used}
                </p>
                <p className="text-slate-500 mt-1 leading-relaxed text-[10px]">{r.routing_decision.reason}</p>
              </div>

              {/* Cache + hallucination */}
              <div className="flex gap-2">
                <div className={`flex-1 rounded-lg p-2.5 ${cacheHit ? 'bg-amber-900/30 border border-amber-700/40' : 'bg-slate-900/60'}`}>
                  <p className="text-slate-500 mb-1 text-[10px]">Deduplication</p>
                  <p className={`font-semibold ${cacheHit ? 'text-amber-400' : 'text-slate-400'}`}>
                    {cacheHit ? '⚡ HIT' : 'MISS'}
                  </p>
                </div>
                <div className={`flex-1 rounded-lg p-2.5 ${
                  hallucCheck?.is_hallucination ? 'bg-amber-900/30 border border-amber-700/40' : 'bg-emerald-900/20 border border-emerald-800/40'
                }`}>
                  <p className="text-slate-500 mb-1 text-[10px]">Response Reliability</p>
                  <div className="flex items-center gap-1">
                    {hallucCheck?.is_hallucination ? (
                      <AlertTriangle className="w-3 h-3 text-amber-400" />
                    ) : (
                      <CheckCircle className="w-3 h-3 text-emerald-400" />
                    )}
                    <span className={`font-semibold ${hallucCheck?.is_hallucination ? 'text-amber-400' : 'text-emerald-400'}`}>
                      {hallucCheck?.is_hallucination ? 'FLAG' : 'PASS'}
                    </span>
                  </div>
                  {hallucCheck && (
                    <p className="text-[10px] text-slate-600 mt-0.5">
                      conf {(hallucCheck.confidence * 100).toFixed(0)}%
                    </p>
                  )}
                </div>
              </div>

              {/* Cost delta */}
              <div className="bg-slate-900/60 rounded-lg p-2.5">
                <div className="flex justify-between items-start">
                  <div>
                    <p className="text-slate-500 text-[10px] mb-1">Actual Cost</p>
                    <p className="text-white font-semibold">${actualCostQ.toFixed(6)}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-slate-500 text-[10px] mb-1">GPT-4o Baseline</p>
                    <p className="text-slate-400">${GPT4O_BASELINE.toFixed(4)}</p>
                  </div>
                </div>
                {savings > 0 && (
                  <div className="mt-2 pt-2 border-t border-white/5 flex items-center justify-between">
                    <span className="text-[10px] text-slate-500">Query savings</span>
                    <span className="text-emerald-400 font-semibold">{savingsPctQ}% (${savings.toFixed(6)})</span>
                  </div>
                )}
              </div>
            </div>
          )
        })()}
      </div>

      {/* ── B: Provider Health Board ──────────────────────────────────────── */}
      <div className="bg-slate-800/40 backdrop-blur-sm rounded-xl border border-white/5 ring-1 ring-white/5 p-4">
        <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-0.5 flex items-center gap-2">
          <Shield className="w-3.5 h-3.5 text-blue-400" />
          Provider Health Board
        </h2>
        <p className="text-[10px] text-slate-600 mb-3">
          Session-level availability and latency across all five model providers.
        </p>
        <div className="space-y-1.5">
          {(providerHealth.length > 0
            ? providerHealth
            : ['openai', 'anthropic', 'google', 'groq', 'ollama'].map(p => ({
                provider: p, status: 'unconfigured' as const,
                total_queries: 0, avg_latency_ms: 0, last_seen: null,
              }))
          ).map((ph) => {
            const test = providerTest[ph.provider]
            const badge = test ? (TEST_BADGE[test.status] ?? TEST_BADGE.pending) : null
            return (
              <div key={ph.provider} className="flex items-center gap-2 bg-slate-900/50 rounded-lg px-3 py-2">
                <span className={`w-2 h-2 rounded-full flex-shrink-0 ${
                  ph.status === 'active' ? 'bg-emerald-400' : 'bg-slate-600'
                }`} />
                <span className="text-xs text-slate-300 w-16 flex-shrink-0 font-medium">
                  {PROVIDER_DISPLAY[ph.provider] ?? ph.provider}
                </span>
                {badge && (
                  <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded flex-shrink-0 ${badge.cls}`}>
                    {badge.label}
                  </span>
                )}
                {ph.status === 'active' ? (
                  <>
                    <span className="text-[10px] text-slate-500 flex-1">{ph.avg_latency_ms}ms avg</span>
                    <span className="text-[10px] text-slate-600">{ph.total_queries} req</span>
                  </>
                ) : (
                  <span className="text-[10px] text-slate-600 flex-1">not yet used</span>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* ── C: Security Event Log ───────────────────────────────────────── */}
      <div className="bg-slate-800/40 backdrop-blur-sm rounded-xl border border-white/5 ring-1 ring-white/5 p-4">
        <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-0.5 flex items-center gap-2">
          <ShieldAlert className="w-3.5 h-3.5 text-red-400" />
          Security Event Log
          {securityEvents.length > 0 && (
            <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-red-900/50 text-red-400 border border-red-700/50">
              {securityEvents.length} blocked
            </span>
          )}
        </h2>
        <p className="text-[10px] text-slate-600 mb-3">
          Requests blocked by the security gate — prompt injection, PII, and policy violations.
        </p>
        {securityEvents.length === 0 ? (
          <p className="text-xs text-slate-600 text-center py-4">No security events</p>
        ) : (
          <div className="space-y-1.5 max-h-48 overflow-y-auto">
            {securityEvents.slice(0, 10).map((ev) => (
              <div key={ev.id} className="bg-red-950/30 border border-red-900/40 rounded-lg px-3 py-2">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="w-3 h-3 text-red-400 flex-shrink-0 mt-0.5" />
                  <div className="min-w-0">
                    <p className="text-[10px] text-red-300 leading-relaxed truncate">
                      {ev.security_reason}
                    </p>
                    <p className="text-[9px] text-slate-600 mt-0.5">
                      {new Date(ev.timestamp + 'Z').toLocaleTimeString()} · {ev.domain}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── D: Savings Accumulator ───────────────────────────────────────── */}
      <div className="bg-slate-800/40 backdrop-blur-sm rounded-xl border border-white/5 ring-1 ring-white/5 p-4">
        <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-0.5 flex items-center gap-2">
          <TrendingDown className="w-3.5 h-3.5 text-emerald-400" />
          Savings Accumulator
        </h2>
        <p className="text-[10px] text-slate-600 mb-3">
          Cumulative cost efficiency vs. a GPT-4o-only baseline across all routed requests.
        </p>

        <div className="grid grid-cols-2 gap-2 mb-3">
          <div className="bg-slate-900/60 rounded-lg p-2.5">
            <p className="text-[10px] text-slate-500 mb-1">Total Queries</p>
            <p className="text-lg font-bold text-white">{totalQueries}</p>
          </div>
          <div className="bg-slate-900/60 rounded-lg p-2.5">
            <p className="text-[10px] text-slate-500 mb-1">Deduplication Rate</p>
            <p className="text-lg font-bold text-amber-400">{cacheHitRate.toFixed(1)}%</p>
          </div>
          <div className="bg-emerald-900/30 border border-emerald-800/40 rounded-lg p-2.5 col-span-2">
            <div className="flex justify-between items-end">
              <div>
                <p className="text-[10px] text-slate-500 mb-1">Total Saved vs GPT-4o</p>
                <p className="text-xl font-bold text-emerald-400">${cumulativeSavings.toFixed(4)}</p>
              </div>
              <div className="text-right">
                <p className="text-[10px] text-slate-500 mb-1">Savings Rate</p>
                <p className="text-lg font-bold text-emerald-400">{savingsPct}%</p>
              </div>
            </div>
            <div className="mt-2 pt-2 border-t border-emerald-800/30 flex justify-between text-[10px] text-slate-500">
              <span>Actual cost: ${actualCost.toFixed(4)}</span>
              <span>Baseline: ${totalBaseline.toFixed(4)}</span>
            </div>
          </div>
          <div className="bg-slate-900/60 rounded-lg p-2.5">
            <p className="text-[10px] text-slate-500 mb-1">Reliability Incidents</p>
            <p className={`text-lg font-bold ${reliabilityFlags > 0 ? 'text-amber-400' : 'text-white'}`}>
              {reliabilityFlags}
            </p>
          </div>
          <div className="bg-slate-900/60 rounded-lg p-2.5">
            <p className="text-[10px] text-slate-500 mb-1">Avg Latency</p>
            <p className="text-lg font-bold text-white">{stats?.avg_latency_ms ?? 0}ms</p>
          </div>
        </div>
      </div>

      {/* ── Chart: Model Distribution ─────────────────────────────────────── */}
      <div className="bg-slate-800/40 backdrop-blur-sm rounded-xl border border-white/5 ring-1 ring-white/5 p-4">
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-0.5">Model Distribution</h3>
        <p className="text-[10px] text-slate-600 mb-3">
          Request volume vs. cost share — efficient routing concentrates volume on cheap models.
        </p>
        {modelChartData.length === 0 ? (
          <p className="text-xs text-slate-600 text-center py-8">No data yet</p>
        ) : (
          <div style={{ height: 200 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={modelChartData} margin={{ top: 4, right: 8, bottom: 36, left: -16 }}>
                <XAxis dataKey="model" tick={{ fontSize: 10, fill: '#64748b' }} angle={-30} textAnchor="end" interval={0} />
                <YAxis tick={{ fontSize: 10, fill: '#64748b' }} unit="%" domain={[0, 100]} />
                <Tooltip {...TooltipStyle} formatter={(v: number, name: string) => [`${v}%`, name]} />
                <Legend wrapperStyle={{ fontSize: 10, paddingTop: 4 }} />
                <Bar dataKey="requestPct" name="Requests %" fill="#10b981" radius={[3, 3, 0, 0]} />
                <Bar dataKey="costPct"    name="Cost %"     fill="#ef4444" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* ── Chart: Cumulative Savings ────────────────────────────────────── */}
      <div className="bg-slate-800/40 backdrop-blur-sm rounded-xl border border-white/5 ring-1 ring-white/5 p-4">
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

      {/* ── Chart: Avg Latency by Model ──────────────────────────────────── */}
      <div className="bg-slate-800/40 backdrop-blur-sm rounded-xl border border-white/5 ring-1 ring-white/5 p-4">
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

      {/* ── Chart: Risk Breakdown Donut ──────────────────────────────────── */}
      <div className="bg-slate-800/40 backdrop-blur-sm rounded-xl border border-white/5 ring-1 ring-white/5 p-4">
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-0.5">Reliability Distribution</h3>
        <p className="text-[10px] text-slate-600 mb-3">
          Share of requests by response reliability tier across the session.
        </p>
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

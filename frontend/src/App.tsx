import { useState, useEffect } from 'react'
import { Shield, Menu } from 'lucide-react'
import { LLMResponse, DashboardStats, HistoryItem, StoredHistory, ProviderHealth, ProviderTestResult, SecurityEvent, CausalAnalysisResult } from './types'
import { DemoTour, IntroCard, TOUR_STEPS } from './components/DemoTour'

const GPT4O_BASELINE = 0.0025

function accumulateStats(prev: DashboardStats | null, data: LLMResponse): DashboardStats {
  const base: DashboardStats = prev ?? {
    total_requests: 0, cache_hit_rate: 0, cost_savings: 0,
    avg_latency_ms: 0, hallucinations_caught: 0, model_distribution: {},
  }
  const newTotal = base.total_requests + 1
  const prevHits = Math.round(base.cache_hit_rate / 100 * base.total_requests)
  const newHits = prevHits + (data.routing_decision.cache_hit ? 1 : 0)
  return {
    total_requests: newTotal,
    cache_hit_rate: Math.round((newHits / newTotal) * 1000) / 10,
    cost_savings: base.cost_savings + Math.max(0, GPT4O_BASELINE - data.cost),
    avg_latency_ms: Math.round((base.avg_latency_ms * base.total_requests + data.latency_ms) / newTotal),
    hallucinations_caught: base.hallucinations_caught + (data.causal_analysis?.is_hallucination ? 1 : 0),
    model_distribution: {
      ...base.model_distribution,
      [data.model_used]: (base.model_distribution[data.model_used] ?? 0) + 1,
    },
  }
}
import { PromptInput } from './components/PromptInput'
import { ResponseCard } from './components/ResponseCard'
import { Dashboard } from './components/Dashboard'
import { HistoryPanel } from './components/HistoryPanel'
import { RoutingFlow } from './components/RoutingFlow'

const STORAGE_KEY = 'aegis_history'
const MAX_HISTORY = 50

function loadHistory(): HistoryItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed: StoredHistory = JSON.parse(raw)
    return parsed.version === 1 ? parsed.requests : []
  } catch {
    return []
  }
}

function saveHistory(items: HistoryItem[]): void {
  const stored: StoredHistory = { version: 1, requests: items.slice(0, MAX_HISTORY) }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(stored))
}

function App() {
  const [prompt, setPrompt] = useState('')
  const [response, setResponse] = useState<LLMResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [providerHealth, setProviderHealth] = useState<ProviderHealth[]>([])
  const [providerTest, setProviderTest] = useState<Record<string, ProviderTestResult>>({})
  const [securityEvents, setSecurityEvents] = useState<SecurityEvent[]>([])
  const [history, setHistory] = useState<HistoryItem[]>(loadHistory)
  const [selectedHistoryId, setSelectedHistoryId] = useState<string | undefined>()
  const [mobileHistoryOpen, setMobileHistoryOpen] = useState(false)
  const [causalAnalysis, setCausalAnalysis] = useState<CausalAnalysisResult | null>(null)
  const [tourStep, setTourStep] = useState<number | null>(null)
  const [introVisible, setIntroVisible] = useState(() => !localStorage.getItem('aegis_intro_dismissed'))

  const fetchCausalAnalysis = async () => {
    try {
      const res = await fetch('/api/causal-analysis')
      if (res.ok) setCausalAnalysis(await res.json())
    } catch {
      // non-critical
    }
  }

  const fetchStats = async () => {
    try {
      const [statsRes, healthRes, testRes, securityRes] = await Promise.all([
        fetch('/api/stats'),
        fetch('/api/provider-health'),
        fetch('/api/provider-test'),
        fetch('/api/security/events'),
      ])
      if (statsRes.ok) setStats(await statsRes.json())
      if (healthRes.ok) setProviderHealth(await healthRes.json())
      if (testRes.ok) setProviderTest(await testRes.json())
      if (securityRes.ok) setSecurityEvents(await securityRes.json())
    } catch {
      // non-critical
    }
  }

  useEffect(() => { fetchStats(); fetchCausalAnalysis() }, [])
  useEffect(() => { if (response) { fetchStats(); fetchCausalAnalysis() } }, [response])

  const doSubmit = async (promptText: string) => {
    if (!promptText.trim()) return
    setLoading(true)
    setError('')
    setSelectedHistoryId(undefined)
    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: promptText }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Request failed' }))
        throw new Error(err.detail || 'Request failed')
      }
      const data: LLMResponse = await res.json()
      setResponse(data)
      setStats((prev) => accumulateStats(prev, data))
      const item: HistoryItem = {
        id: data.request_id,
        timestamp: new Date().toISOString(),
        prompt: promptText,
        response: data,
      }
      setHistory((prev) => {
        const updated = [item, ...prev].slice(0, MAX_HISTORY)
        saveHistory(updated)
        return updated
      })
      setSelectedHistoryId(data.request_id)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to get response.'
      setError(msg)
      setResponse(null)
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await doSubmit(prompt)
  }

  const startTour = () => {
    localStorage.setItem('aegis_intro_dismissed', '1')
    setIntroVisible(false)
    setTourStep(0)
    const p = TOUR_STEPS[0].prompt
    setPrompt(p)
    doSubmit(p)
  }

  const advanceTour = () => {
    if (tourStep === null) return
    const next = tourStep + 1
    if (next >= TOUR_STEPS.length) {
      setTourStep(null)
      return
    }
    setTourStep(next)
    const p = TOUR_STEPS[next].prompt
    setPrompt(p)
    doSubmit(p)
  }

  const exitTour = () => setTourStep(null)

  const handleHistorySelect = (item: HistoryItem) => {
    setResponse(item.response)
    setPrompt(item.prompt)
    setSelectedHistoryId(item.id)
    setMobileHistoryOpen(false)
  }

  return (
    <div className="h-screen overflow-hidden flex flex-col bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950">
      {/* ── Header ───────────────────────────────────────────────────── */}
      <header className="border-b border-white/5 bg-slate-900/70 backdrop-blur-md flex-shrink-0 z-20">
        <div className="max-w-[1600px] mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setMobileHistoryOpen((o) => !o)}
              className="lg:hidden p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-700 transition-colors"
            >
              <Menu className="w-4 h-4" />
            </button>
            <Shield className="w-7 h-7 text-emerald-400" />
            <div>
              <h1 className="text-lg font-bold text-white tracking-tight">Aegis</h1>
              <p className="text-xs text-slate-500 leading-none">Agentic LLM Gateway</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={startTour}
              className="text-xs font-medium px-3 py-1.5 rounded-lg bg-indigo-700 hover:bg-indigo-600 text-indigo-100 transition-colors"
            >
              Demo Tour
            </button>
            {Object.entries(providerTest).some(([, v]) => v.status === 'auth_error') ? (
              <>
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                <span className="text-xs text-amber-500">Provider key error — check dashboard</span>
              </>
            ) : (
              <>
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                <span className="text-xs text-slate-500">Live</span>
              </>
            )}
            {stats && (
              <span className="text-xs text-slate-600 ml-1">{stats.total_requests} requests</span>
            )}
          </div>
        </div>
      </header>

      {/* ── Page description ─────────────────────────────────────────── */}
      <div className="border-b border-white/5 bg-slate-900/40">
        <div className="max-w-[1600px] mx-auto px-4 py-2">
          <p className="text-xs text-slate-500 leading-relaxed">
            Aegis routes each request to the lowest-cost capable model using complexity scoring,
            applies semantic deduplication caching, and runs multi-tier reliability verification
            on every response.
          </p>
        </div>
      </div>

      {/* ── 3-Panel Layout ───────────────────────────────────────────── */}
      <div className="flex-1 min-h-0 max-w-[1600px] mx-auto w-full px-4 py-4 flex gap-4 overflow-hidden">

        {/* Panel 1: History sidebar */}
        <HistoryPanel
          history={history}
          onSelect={handleHistorySelect}
          selectedId={selectedHistoryId}
        />

        {/* Mobile history drawer */}
        {mobileHistoryOpen && (
          <div className="lg:hidden fixed inset-0 z-30 flex">
            <div className="w-72 bg-slate-900 border-r border-white/10 overflow-y-auto p-3 flex flex-col">
              <button
                onClick={() => setMobileHistoryOpen(false)}
                className="text-xs text-slate-400 hover:text-white mb-3 text-left"
              >
                ← Close
              </button>
              {history.length === 0 ? (
                <p className="text-xs text-slate-600 text-center mt-10">No history yet</p>
              ) : (
                history.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => handleHistorySelect(item)}
                    className="w-full text-left text-xs text-slate-300 bg-slate-800/50 rounded-lg p-3 mb-1 hover:bg-slate-700 transition-colors"
                  >
                    <p className="text-slate-500 mb-1">{new Date(item.timestamp).toLocaleTimeString()}</p>
                    <p className="truncate">{item.prompt}</p>
                  </button>
                ))
              )}
            </div>
            <div className="flex-1 bg-black/40" onClick={() => setMobileHistoryOpen(false)} />
          </div>
        )}

        {/* Panel 2: Main interaction — response area top, input pinned bottom */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {/* Scrollable response area */}
          <div className="flex-1 overflow-y-auto space-y-4 pr-1 pb-2">
            {/* Intro card — shown once per session */}
            {introVisible && tourStep === null && (
              <IntroCard
                onDismiss={() => {
                  localStorage.setItem('aegis_intro_dismissed', '1')
                  setIntroVisible(false)
                }}
                onStartTour={startTour}
              />
            )}

            {/* Guided demo tour overlay */}
            {tourStep !== null && (
              <DemoTour
                step={tourStep}
                loading={loading}
                onNext={advanceTour}
                onExit={exitTour}
              />
            )}

            {/* Routing pipeline — always visible */}
            <RoutingFlow response={loading ? null : response} />

            {error && (
              <div className="bg-red-900/30 border border-red-700/50 rounded-xl p-4 text-sm text-red-400">
                {error}
              </div>
            )}

            {/* Skeleton while loading */}
            {loading && (
              <div className="bg-slate-800/40 backdrop-blur-sm rounded-xl border border-white/5 p-5 space-y-3 animate-pulse">
                <div className="h-2.5 bg-slate-700 rounded w-1/5" />
                <div className="h-32 bg-slate-700/50 rounded" />
                <div className="grid grid-cols-2 gap-3">
                  <div className="h-14 bg-slate-700/50 rounded" />
                  <div className="h-14 bg-slate-700/50 rounded" />
                  <div className="h-14 bg-slate-700/50 rounded" />
                  <div className="h-14 bg-slate-700/50 rounded" />
                </div>
              </div>
            )}

            {!loading && response && <ResponseCard response={response} />}
          </div>

          {/* Input bar pinned to bottom */}
          <PromptInput
            prompt={prompt}
            loading={loading}
            onPromptChange={setPrompt}
            onSubmit={handleSubmit}
          />
        </div>

        {/* Panel 3: Dashboard */}
        <Dashboard stats={stats} history={history} providerHealth={providerHealth} providerTest={providerTest} securityEvents={securityEvents} causalAnalysis={causalAnalysis} />
      </div>
    </div>
  )
}

export default App

import { useState, useEffect } from 'react'
import { Menu } from 'lucide-react'
import { AegisLogo } from '../components/AegisLogo'
import { useLocation, useNavigate } from 'react-router-dom'
import { LLMResponse, DashboardStats, HistoryItem, StoredHistory, ProviderHealth, ProviderTestResult, SecurityEvent, CausalAnalysisResult, StreamStage } from '../types'
import { DemoTour, TOUR_STEPS } from '../components/DemoTour'
import { EmptyState } from '../components/EmptyState'
import { StreamingStatus } from '../components/StreamingStatus'
import { PromptInput } from '../components/PromptInput'
import { ResponseCard } from '../components/ResponseCard'
import { Dashboard } from '../components/Dashboard'
import { HistoryPanel } from '../components/HistoryPanel'
import { RoutingFlow } from '../components/RoutingFlow'

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

export function AppPage() {
  const location = useLocation()
  const navigate = useNavigate()

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
  const [streamStages, setStreamStages] = useState<StreamStage[]>([])
  const [activeTab, setActiveTab] = useState<'chat' | 'dashboard'>('chat')

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

  useEffect(() => {
    const state = location.state as { startTour?: boolean } | null
    if (state?.startTour) startTour()
  }, [])

  const doSubmit = async (promptText: string) => {
    if (!promptText.trim()) return
    setLoading(true)
    setError('')
    setResponse(null)
    setStreamStages([])
    setSelectedHistoryId(undefined)

    try {
      const res = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: promptText }),
      })

      if (!res.ok || !res.body) {
        const err = await res.json().catch(() => ({ detail: 'Request failed' }))
        throw new Error(err.detail || 'Request failed')
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const evt = JSON.parse(line.slice(6))

          if (evt.type === 'status') {
            setStreamStages((prev) => {
              const idx = prev.findIndex((s) => s.stage === evt.stage && s.label === evt.label)
              const updated = { stage: evt.stage, label: evt.label, message: evt.message, done: evt.done ?? false }
              if (idx >= 0) {
                const next = [...prev]
                next[idx] = updated
                return next
              }
              return [...prev, updated]
            })
          } else if (evt.type === 'done') {
            const data: LLMResponse = evt.data
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
          } else if (evt.type === 'error') {
            setError(evt.message)
          }
        }
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to get response.'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await doSubmit(prompt)
  }

  const startTour = () => {
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
    <div className="h-screen overflow-hidden flex flex-col bg-[#F8F7F4]">
      {/* ── Header ───────────────────────────────────────────────────── */}
      <header className="border-b border-[#E5E2DC] bg-white shadow-sm flex-shrink-0 z-20">
        <div className="max-w-[1600px] mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setMobileHistoryOpen((o) => !o)}
              className="lg:hidden p-1.5 rounded-lg text-slate-500 hover:text-slate-900 hover:bg-[#F1EFE9] transition-colors"
            >
              <Menu className="w-4 h-4" />
            </button>
            <button onClick={() => navigate('/')} className="flex items-center gap-2 hover:opacity-80 transition-opacity">
              <AegisLogo size={28} />
              <div className="text-left">
                <h1 className="text-lg font-bold text-slate-900 tracking-tight leading-none font-heading">Aegis</h1>
                <p className="text-xs text-slate-400 leading-none">Agentic LLM Gateway</p>
              </div>
            </button>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={startTour}
              className="text-xs font-medium px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white transition-colors"
            >
              Demo Tour
            </button>
            {Object.entries(providerTest).some(([, v]) => v.status === 'auth_error') ? (
              <>
                <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
                <span className="text-xs text-amber-600">Provider key error — check dashboard</span>
              </>
            ) : (
              <>
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                <span className="text-xs text-slate-400">Live</span>
              </>
            )}
            {stats && (
              <span className="text-xs text-slate-400 ml-1 font-mono">{stats.total_requests} requests</span>
            )}
          </div>
        </div>
      </header>

      {/* ── Mobile Tab Strip ─────────────────────────────────────────── */}
      <div className="border-b border-[#E5E2DC] bg-white flex-shrink-0 lg:hidden">
        <div className="flex">
          {(['chat', 'dashboard'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-5 py-2.5 text-sm font-medium capitalize border-b-2 transition-colors ${
                activeTab === tab
                  ? 'border-emerald-600 text-emerald-700'
                  : 'border-transparent text-slate-500 hover:text-slate-700'
              }`}
            >
              {tab}
            </button>
          ))}
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
            <div className="w-72 bg-white border-r border-[#E5E2DC] overflow-y-auto p-3 flex flex-col shadow-lg">
              <button
                onClick={() => setMobileHistoryOpen(false)}
                className="text-xs text-slate-500 hover:text-slate-900 mb-3 text-left"
              >
                ← Close
              </button>
              {history.length === 0 ? (
                <p className="text-xs text-slate-400 text-center mt-10">No history yet</p>
              ) : (
                history.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => handleHistorySelect(item)}
                    className="w-full text-left text-xs text-slate-700 bg-[#F1EFE9] rounded-lg p-3 mb-1 hover:bg-[#E5E2DC] transition-colors"
                  >
                    <p className="text-slate-400 mb-1">{new Date(item.timestamp).toLocaleTimeString()}</p>
                    <p className="truncate">{item.prompt}</p>
                  </button>
                ))
              )}
            </div>
            <div className="flex-1 bg-black/20" onClick={() => setMobileHistoryOpen(false)} />
          </div>
        )}

        {/* Panel 2: Main interaction — response area top, input pinned bottom */}
        <div className={`flex-1 flex-col min-w-0 overflow-hidden ${activeTab !== 'chat' ? 'hidden lg:flex' : 'flex'}`}>
          {/* Scrollable response area */}
          <div className="flex-1 overflow-y-auto space-y-4 pr-1 pb-2">
            {/* Guided demo tour overlay */}
            {tourStep !== null && (
              <DemoTour
                step={tourStep}
                loading={loading}
                onNext={advanceTour}
                onExit={exitTour}
              />
            )}

            {/* Empty state — shown before first interaction */}
            {!response && !loading && tourStep === null && (
              <EmptyState onStartTour={startTour} />
            )}

            {/* Pipeline streaming status */}
            {streamStages.length > 0 && <StreamingStatus stages={streamStages} />}

            {/* Routing flow — shown once response arrives */}
            {response && <RoutingFlow response={response} />}

            {error && (
              <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-600">
                {error}
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
        <div className={`${activeTab !== 'dashboard' ? 'hidden lg:flex' : 'flex'} flex-col w-full lg:w-auto flex-shrink-0 min-h-0`}>
          <Dashboard stats={stats} history={history} providerHealth={providerHealth} providerTest={providerTest} securityEvents={securityEvents} causalAnalysis={causalAnalysis} />
        </div>
      </div>
    </div>
  )
}

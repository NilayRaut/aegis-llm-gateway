import { useState, useEffect } from 'react'
import { Shield, Send, TrendingDown, Clock, AlertTriangle, BarChart3 } from 'lucide-react'

interface LLMResponse {
  response: string
  model_used: string
  cost: number
  latency_ms: number
  routing_decision: {
    model: string
    reason: string
    confidence: number
    cache_hit: boolean
  }
  causal_analysis?: {
    confidence: number
    is_hallucination: boolean
    explanation: string
  }
  request_id: string
}

interface DashboardStats {
  total_requests: number
  cache_hit_rate: number
  cost_savings: number
  avg_latency_ms: number
  hallucinations_caught: number
  model_distribution: Record<string, number>
}

// Demo prompts — one per routing tier + a legal domain example
const DEMO_PROMPTS = [
  { label: 'Simple', prompt: 'What time is it currently in Tokyo, Japan?' },
  { label: 'Technical', prompt: 'Explain how gradient descent works in machine learning.' },
  { label: 'Complex', prompt: 'Design a microservices architecture with event sourcing and CQRS for a high-traffic e-commerce platform.' },
  { label: '⚠ Legal', prompt: 'Is a non-compete agreement enforceable in California under current law?' },
  { label: '⚠ Medical', prompt: 'What is the recommended dosage and treatment protocol for hypertension in adults?' },
]

function App() {
  const [prompt, setPrompt] = useState('')
  const [response, setResponse] = useState<LLMResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [stats, setStats] = useState<DashboardStats | null>(null)

  const fetchStats = async () => {
    try {
      const res = await fetch('/api/stats')
      if (res.ok) setStats(await res.json())
    } catch {
      // stats fetch failure is non-critical
    }
  }

  // Fetch stats on mount
  useEffect(() => { fetchStats() }, [])

  // Refresh stats after every response
  useEffect(() => { if (response) fetchStats() }, [response])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!prompt.trim()) return

    setLoading(true)
    setError('')
    setResponse(null)

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt })
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Request failed' }))
        throw new Error(err.detail || 'Request failed')
      }

      const data = await res.json()
      setResponse(data)
    } catch (err: any) {
      setError(err.message || 'Failed to get response. Make sure the backend is running.')
    } finally {
      setLoading(false)
    }
  }

  // Compute model distribution percentages
  const modelDist = stats?.model_distribution ?? {}
  const totalRequests = Object.values(modelDist).reduce((a, b) => a + b, 0)
  const modelPct = (count: number) =>
    totalRequests > 0 ? Math.round((count / totalRequests) * 100) : 0

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      {/* Header */}
      <header className="border-b border-slate-700 bg-slate-900/50 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Shield className="w-8 h-8 text-emerald-400" />
            <div>
              <h1 className="text-xl font-bold text-white">Aegis</h1>
              <p className="text-xs text-slate-400">Agentic LLM Gateway</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            <span className="text-xs text-slate-400">Live</span>
            {stats && (
              <span className="ml-3 text-xs text-slate-500">{stats.total_requests} requests</span>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-8">
        <div className="grid lg:grid-cols-2 gap-8">
          {/* Left Column - Input & Response */}
          <div className="space-y-6">
            {/* Prompt Input */}
            <div className="bg-slate-800/50 rounded-xl p-6 border border-slate-700">
              <h2 className="text-lg font-semibold text-white mb-4">Send a Prompt</h2>

              {/* Demo prompt buttons */}
              <div className="flex flex-wrap gap-2 mb-4">
                {DEMO_PROMPTS.map(({ label, prompt: p }) => (
                  <button
                    key={label}
                    onClick={() => setPrompt(p)}
                    className="text-xs px-3 py-1.5 rounded-full bg-slate-700 hover:bg-slate-600 text-slate-300 hover:text-white transition-colors border border-slate-600"
                  >
                    {label}
                  </button>
                ))}
              </div>

              <form onSubmit={handleSubmit} className="space-y-4">
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="Enter your prompt here... Aegis will route it to the optimal model."
                  className="w-full h-32 bg-slate-900 border border-slate-600 rounded-lg p-4 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 resize-none"
                />
                <button
                  type="submit"
                  disabled={loading || !prompt.trim()}
                  className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-700 disabled:cursor-not-allowed text-white font-medium py-3 px-4 rounded-lg flex items-center justify-center gap-2 transition-colors"
                >
                  {loading ? (
                    <span className="animate-spin">⏳</span>
                  ) : (
                    <Send className="w-4 h-4" />
                  )}
                  {loading ? 'Processing...' : 'Send Prompt'}
                </button>
              </form>
            </div>

            {/* Error Display */}
            {error && (
              <div className="bg-red-900/30 border border-red-700 rounded-xl p-4 text-red-400">
                {error}
              </div>
            )}

            {/* Response Display */}
            {response && (
              <div className="bg-slate-800/50 rounded-xl p-6 border border-slate-700 space-y-4">
                <h2 className="text-lg font-semibold text-white">Response</h2>

                <div className="bg-slate-900 rounded-lg p-4 text-slate-200 whitespace-pre-wrap">
                  {response.response}
                </div>

                {/* Routing Info */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="bg-slate-900/50 rounded-lg p-3">
                    <p className="text-xs text-slate-400 mb-1">Model Used</p>
                    <p className="text-emerald-400 font-mono text-sm">{response.model_used}</p>
                  </div>
                  <div className="bg-slate-900/50 rounded-lg p-3">
                    <p className="text-xs text-slate-400 mb-1">Cost</p>
                    <p className="text-white">${response.cost.toFixed(6)}</p>
                  </div>
                  <div className="bg-slate-900/50 rounded-lg p-3">
                    <p className="text-xs text-slate-400 mb-1">Latency</p>
                    <p className="text-white">{response.latency_ms}ms</p>
                  </div>
                  <div className="bg-slate-900/50 rounded-lg p-3">
                    <p className="text-xs text-slate-400 mb-1">Cache Hit</p>
                    <p className={response.routing_decision.cache_hit ? 'text-emerald-400' : 'text-slate-400'}>
                      {response.routing_decision.cache_hit ? '✓ Yes ($0.00)' : 'No'}
                    </p>
                  </div>
                </div>

                {/* Routing reason */}
                <div className="bg-slate-900/50 rounded-lg p-3">
                  <p className="text-xs text-slate-400 mb-1">Routing Decision</p>
                  <p className="text-xs text-slate-300">{response.routing_decision.reason}</p>
                </div>

                {/* Causal Analysis */}
                {response.causal_analysis && (
                  <div className={`rounded-lg p-4 ${
                    response.causal_analysis.is_hallucination
                      ? 'bg-amber-900/30 border border-amber-700'
                      : 'bg-emerald-900/30 border border-emerald-700'
                  }`}>
                    <div className="flex items-center gap-2 mb-2">
                      <AlertTriangle className={`w-4 h-4 ${
                        response.causal_analysis.is_hallucination ? 'text-amber-400' : 'text-emerald-400'
                      }`} />
                      <span className="font-medium text-white">
                        {response.causal_analysis.is_hallucination
                          ? 'Potential Hallucination Detected'
                          : 'Response Verified'}
                      </span>
                    </div>
                    <p className="text-sm text-slate-300">{response.causal_analysis.explanation}</p>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Right Column - Dashboard Stats */}
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
                    <span className="text-xs text-slate-400">Risk Flags</span>
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

              {/* Model Distribution */}
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

            {/* How It Works */}
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
                  <p><strong className="text-slate-200">Complexity routing</strong> — 5-tier model pool: Llama-3 → Gemini → GPT-4o-mini → Claude → GPT-4o</p>
                </div>
                <div className="flex items-start gap-3">
                  <span className="bg-amber-600 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center flex-shrink-0">4</span>
                  <p><strong className="text-slate-200">Causal risk check</strong> — variance threshold θ=0.35 calibrated via DoWhy on 1,000 synthetic tuples</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}

export default App

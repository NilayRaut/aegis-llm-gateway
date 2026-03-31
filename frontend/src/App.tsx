import { useState, useEffect } from 'react'
import { Shield } from 'lucide-react'
import { LLMResponse, DashboardStats } from './types'
import { PromptInput } from './components/PromptInput'
import { ResponseCard } from './components/ResponseCard'
import { Dashboard } from './components/Dashboard'

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

  useEffect(() => { fetchStats() }, [])
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

      setResponse(await res.json())
    } catch (err: any) {
      setError(err.message || 'Failed to get response. Make sure the backend is running.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
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
          <div className="space-y-6">
            <PromptInput
              prompt={prompt}
              loading={loading}
              onPromptChange={setPrompt}
              onSubmit={handleSubmit}
            />

            {error && (
              <div className="bg-red-900/30 border border-red-700 rounded-xl p-4 text-red-400">
                {error}
              </div>
            )}

            {response && <ResponseCard response={response} />}
          </div>

          <Dashboard stats={stats} />
        </div>
      </main>
    </div>
  )
}

export default App

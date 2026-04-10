export interface RoutingDecision {
  model: string
  reason: string
  confidence: number
  cache_hit: boolean
}

export interface CausalAnalysis {
  confidence: number
  is_hallucination: boolean
  explanation: string
}

export interface LLMResponse {
  response: string
  model_used: string
  cost: number
  latency_ms: number
  routing_decision: RoutingDecision
  causal_analysis?: CausalAnalysis
  request_id: string
  complexity_score?: number
  domain?: string
  risk_level?: string
  provider?: string
}

export interface DashboardStats {
  total_requests: number
  cache_hit_rate: number
  cost_savings: number
  avg_latency_ms: number
  hallucinations_caught: number
  model_distribution: Record<string, number>
}

export interface HistoryItem {
  id: string
  timestamp: string  // ISO string
  prompt: string
  response: LLMResponse
}

export interface StoredHistory {
  version: 1
  requests: HistoryItem[]
}

// Shared color map for models — used in HistoryPanel, Dashboard, RoutingFlow
export const MODEL_COLORS: Record<string, string> = {
  'llama-3.1-8b-instant': '#10b981',
  'llama3.1':             '#10b981',
  'gemini-1.5-flash':     '#3b82f6',
  'gpt-4o-mini':          '#8b5cf6',
  'claude-haiku-3-5-sonnet-20241022': '#f59e0b',
  'gpt-4o':               '#ef4444',
}

export const DEMO_PROMPTS = [
  { label: 'Simple', prompt: 'What time is it currently in Tokyo, Japan?' },
  { label: 'Technical', prompt: 'Explain how gradient descent works in machine learning.' },
  { label: 'Complex', prompt: 'Design a microservices architecture with event sourcing and CQRS for a high-traffic e-commerce platform.' },
  { label: '⚠ Legal', prompt: 'Is a non-compete agreement enforceable in California under current law?' },
  { label: '⚠ Medical', prompt: 'What is the recommended dosage and treatment protocol for hypertension in adults?' },
]

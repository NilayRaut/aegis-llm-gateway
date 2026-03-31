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
}

export interface DashboardStats {
  total_requests: number
  cache_hit_rate: number
  cost_savings: number
  avg_latency_ms: number
  hallucinations_caught: number
  model_distribution: Record<string, number>
}

export const DEMO_PROMPTS = [
  { label: 'Simple', prompt: 'What time is it currently in Tokyo, Japan?' },
  { label: 'Technical', prompt: 'Explain how gradient descent works in machine learning.' },
  { label: 'Complex', prompt: 'Design a microservices architecture with event sourcing and CQRS for a high-traffic e-commerce platform.' },
  { label: '⚠ Legal', prompt: 'Is a non-compete agreement enforceable in California under current law?' },
  { label: '⚠ Medical', prompt: 'What is the recommended dosage and treatment protocol for hypertension in adults?' },
]

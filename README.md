# 🛡️ Aegis - Agentic LLM Gateway & Production Firewall

> **Intelligent LLM routing with causal hallucination detection**

Aegis is an end-to-end production system that automatically routes prompts to the optimal LLM based on complexity, while detecting and flagging potential hallucinations using causal inference techniques.

## 🎯 Problem Statement

**The "Real World" Question:**  
Organizations using LLMs face a critical tradeoff: GPT-4o delivers quality but at $0.005/1K tokens, while simpler queries waste budget. Meanwhile, LLM hallucinations—confident but false responses—pose real risks in production systems.

**Why This Requires Advanced Data Science:**  
- Basic regression cannot solve this—routing requires understanding semantic complexity
- Hallucination detection needs causal reasoning, not just pattern matching
- Real-time constraints demand intelligent caching and model selection

**Cost of "Garbage Out":**
- Routing errors waste budget (overkill) or degrade quality (underkill)
- Undetected hallucinations in medical/legal/financial domains can cause real harm
- Silent failures erode user trust

## ✨ Key Features

- **Intelligent Routing**: Classifies prompt complexity → routes to Llama-3 (free), GPT-4o-mini ($0.00015/1K), or GPT-4o ($0.005/1K)
- **Causal Hallucination Detection**: Uses DoWhy to identify correlation-not-causation patterns
- **Semantic Caching**: Reduces costs by caching similar queries
- **Real-time Dashboard**: Visualizes cost savings, latency, and hallucination catches

## 🏗️ Architecture

```
User Prompt
    │
    ▼
┌─────────────────┐
│  LangGraph      │  ← Agentic orchestration
│  Router Agent   │
└────────┬────────┘
         │
    ┌────┴────┬──────────┐
    ▼         ▼          ▼
┌───────┐ ┌─────────┐ ┌────────┐
│Llama-3│ │GPT-4o-  │ │ GPT-4o │
│(local)│ │ mini    │ │        │
└───┬───┘ └────┬────┘ └───┬────┘
    │          │          │
    └────┬─────┴──────────┘
         ▼
┌─────────────────┐
│  DoWhy Causal   │  ← Hallucination detection
│  Analysis       │
└─────────────────┘
         │
         ▼
    Response + Metadata
```

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- OpenAI API key

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# Run the server
uvicorn main:app --reload
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev
```

### Access the Application
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

## 📊 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat` | POST | Send prompt, get routed response |
| `/api/stats` | GET | Dashboard statistics |
| `/health` | GET | Health check for deployment |

## 🧪 Testing

```bash
# Backend tests
cd backend
pytest

# Frontend tests
cd frontend
npm test
```

## 🚢 Deployment

### Backend (Render)
1. Connect GitHub repo to Render
2. Select the `backend` directory
3. Set environment variables
4. Deploy!

### Frontend (Vercel)
1. Connect GitHub repo to Vercel
2. Select the `frontend` directory
3. Deploy!

## 📈 The Nine Pillars of AI Fluency

This project implements:

1. **Stochastic Reasoning**: Probabilistic routing based on prompt complexity scores
2. **Causal Reasoning**: DoWhy-based hallucination detection via causal DAGs
3. **Ethical Reasoning**: Transparent cost/quality tradeoffs, no hidden routing
4. **Systems Thinking**: End-to-end pipeline from prompt to validated response

## 🔬 Technical Approach

### Prompt Complexity Classification
```python
complexity_score = classifier.analyze(prompt)
# Features: length, domain_terms, reasoning_required, factual_complexity

if complexity_score < 0.3:
    route_to("llama-3")      # Free, local
elif complexity_score < 0.7:
    route_to("gpt-4o-mini")  # $0.00015/1K tokens
else:
    route_to("gpt-4o")       # $0.005/1K tokens
```

### Causal Hallucination Detection
Uses DoWhy to model:
- Treatment: LLM response claim
- Outcome: Factual accuracy
- Confounders: Prompt phrasing, domain, model temperature

Identifies when correlations in training data may cause false causal claims.

## 📁 Project Structure

```
aegis-project/
├── backend/
│   ├── app/
│   │   ├── api/routes.py      # FastAPI endpoints
│   │   ├── agents/            # LangGraph agents
│   │   ├── models/schemas.py  # Pydantic models
│   │   └── services/          # Business logic
│   ├── main.py                # App entry point
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx            # Main React component
│   │   └── components/        # UI components
│   ├── package.json
│   └── vite.config.ts
└── README.md
```

## 📝 License

MIT License - See LICENSE file for details.

## 🙏 Acknowledgments

- INFO 7390 - Advances in Data Science
- LangGraph for agentic orchestration
- DoWhy for causal inference
- OpenAI for LLM APIs
# Udaipur Travel Planner

Voice-first AI travel planning assistant for Udaipur. Streamlit app with Grok/Groq LLM, MCP tools (POI search, itinerary builder, travel calculator), file-based RAG, and optional n8n automation.

## Features

- **Voice + text input** — Browser mic (Streamlit mic recorder) or chat
- **LLM** — Grok API (xAI) or Groq (Llama) with function calling
- **POIs** — Overpass API (live) + static `data/knowledge/` (guide, tips, `pois.json`)
- **RAG** — File-based retrieval (no vector DB)
- **Tools** — POI search, itinerary builder, travel time/distance
- **Evaluations** — Feasibility, grounding, edit correctness (in-app)
- **Optional** — n8n webhook for PDF/email

## Requirements

- Python 3.10+
- See `requirements.txt`

## Quick start

```bash
cd travel-planner
python -m venv venv
venv\Scripts\activate   # Windows
# source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set GROK_API_KEY or GROQ_API_KEY (and optionally N8N_WEBHOOK_URL)
streamlit run app.py
```

Open the URL shown (default `http://localhost:8501`). The app runs without `.env` for POI search and RAG; add keys when you use Grok/Groq or n8n.

**After changing `.env`:** Restart the Streamlit process so new values are loaded.

## Deploy on Streamlit Community Cloud

**If the “Continue to sign-in” button on the deploy page doesn’t work**, sign in first, then create the app:

1. Open **[share.streamlit.io](https://share.streamlit.io)** (main page, not the deploy link).
2. Click **Sign in** (top right) and sign in with **GitHub** (or Google / email).
3. After signing in, click **New app**.
4. Choose repository: `duttaneha201-ux/Voice-first-AI-travel-planning-assistant-`, branch `main`.
5. Set **Main file path** to: `travel-planner/app.py`.
6. In **Advanced settings**, set **Working directory** to: `travel-planner` (if shown).
7. Click **Deploy**. The app will use `travel-planner/requirements.txt` automatically.

**One-click deploy** (use only if sign-in works for you):  
[![Deploy](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io/deploy?repository=duttaneha201-ux/Voice-first-AI-travel-planning-assistant-)

**Sign-in issues:** Try the top-right **Sign in** link instead of the blue button; use a normal (non-incognito) window and allow cookies for `share.streamlit.io`. If you get a 403, see [Streamlit’s troubleshooting](https://docs.streamlit.io/knowledge-base/deploy/login-attempt-to-streamlit-community-cloud-fails-with-error-403) or contact support@streamlit.io.

**Secrets (optional)**  
   In the app’s **Settings → Secrets**, add the same keys you use in `.env` (e.g. `GROK_API_KEY`, `GROQ_API_KEY`, `N8N_WEBHOOK_URL`). Without secrets, POI search and RAG still work; add keys when you want Grok/Groq or n8n.

## Environment variables

| Variable | Description |
|----------|-------------|
| `LLM_PROVIDER` | `grok` (default) or `groq` |
| `GROK_API_KEY` | xAI API key (when using Grok) |
| `GROQ_API_KEY` | Groq API key (when using Groq) |
| `N8N_WEBHOOK_URL` | Optional n8n webhook for PDF/email |

Copy `.env.example` to `.env` and fill in the keys you need.

## Project structure

```
travel-planner/
├── app.py                 # Streamlit entry point
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── CURSOR_MCP_SETUP.md    # Optional: Cursor + n8n MCP setup
├── N8N_IMPORT_WORKFLOW.md # Optional: Import n8n workflows
├── n8n_workflow.json      # Optional: n8n workflow template
├── n8n_workflow_puppeteer.json
├── verify_n8n_mcp.py      # Optional: Verify n8n MCP
├── src/
│   ├── ui/                # Itinerary display, follow-ups
│   ├── orchestration/     # Conversation manager, Grok client
│   ├── domains/mcp/       # MCP tools + registry (POI, itinerary, travel calc)
│   ├── infrastructure/    # Overpass client, POI repo, RAG knowledge base
│   ├── services/rag/      # RAG retriever
│   ├── data/              # Re-exports (Overpass, POI repo) for compatibility
│   ├── mcp/               # Re-exports (MCP registry/tools) for compatibility
│   ├── rag/               # Re-exports (knowledge base, retriever)
│   ├── evaluations/       # Feasibility, grounding, edit correctness
│   ├── automation/        # n8n client
│   ├── utils/             # Config, logger, link generator
│   └── __init__.py
├── data/
│   ├── knowledge/         # udaipur_guide.txt, udaipur_tips.txt, pois.json
│   └── cache/             # Overpass cache (gitkept, cache files ignored)
└── tests/
```

## Running tests

```bash
pip install -r requirements-dev.txt   # includes pytest
pytest tests/
# or
python -m pytest tests/
```

## MCP tools

- **poi_search** — Search POIs by city, interests (food, heritage, etc.), and constraints.
- **itinerary_builder** — Build day-by-day itineraries from POIs and preferences.
- **travel_calculator** — Estimate travel time and distance between points.

## Data

- **Overpass API** — Live POIs; results cached under `data/cache/`.
- **data/knowledge/** — Static `udaipur_guide.txt`, `udaipur_tips.txt`, `pois.json`.

## License

MIT.

# Auto Dev Orchestrator - Projekt-Analyse

**Stand:** 2025-10-05
**Version:** 0.1.0

---

## 1. Executive Summary

Auto Dev Orchestrator ist ein produktionsreifes Python-Framework zur Orchestrierung automatisierter Software-Delivery. Das System kombiniert FastAPI, Celery, SQLite und LLM-Provider (OpenAI/Ollama) zu einem durchgängigen Workflow: Task-Planung durch einen CTO-Agenten, schrittweise Code-Implementierung durch einen Coder-Agenten und automatische PR-Erstellung via GitHub-Integration.

**Kernmerkmale:**
- Multi-Agent-System (CTO, Coder, Archivist, Curator)
- Context Engine mit Just-in-Time-Retrieval aus 6 Quellen
- Budget- und Request-Limits mit Cost-Tracking
- Gradio Web-UI
- Windows- und Linux-Support

---

## 2. Modulübersicht

### 2.1 Verzeichnisstruktur

```
auto-dev-orchestrator/
├── app/                          # Hauptanwendung
│   ├── agents/                   # Agent-Implementierungen
│   │   ├── archivist_agent.py    # Memory-Kompaktierung
│   │   ├── coder.py              # Code-Implementierung
│   │   ├── cto.py                # Task-Planung
│   │   ├── curator_agent.py      # Prompt-Hints-Generierung
│   │   └── prompts.py            # AGENTS.md Parser & Prompt-Builder
│   ├── context/                  # Context Engine System
│   │   ├── compactor.py          # Token-Budget-Kompaktierung
│   │   ├── curator.py            # BM25+Embedding-Ranking
│   │   ├── engine.py             # Zentrale Context-Orchestrierung
│   │   ├── memory_store.py       # Memory CRUD
│   │   ├── notes.py              # Notizschema-Validierung
│   │   └── retrievers/           # Multi-Source-Retrieval
│   │       ├── artifacts.py      # Job-Artefakte (context_*.json)
│   │       ├── external.py       # Externe Docs (Embedding-basiert)
│   │       ├── history.py        # Message-Summaries
│   │       └── repo.py           # Repository-Snippets
│   ├── core/                     # Kernfunktionalität
│   │   ├── config.py             # Pydantic-Settings (AppSettings)
│   │   ├── diffs.py              # Unified-Diff-Parser & File-Writer
│   │   ├── logging.py            # Structlog-Konfiguration
│   │   ├── pricing.py            # LLM-Kostenberechnung
│   │   └── shell.py              # Shell-Kommando-Wrapper
│   ├── db/                       # Datenbankschicht
│   │   ├── engine.py             # SQLAlchemy-Engine & Session
│   │   ├── models.py             # ORM-Modelle (Job, Step, Cost, Memory, etc.)
│   │   └── repo.py               # CRUD-Operationen
│   ├── embeddings/               # Embedding-Provider
│   │   ├── openai_embed.py       # OpenAI text-embedding-3-large
│   │   ├── provider.py           # Base-Provider-Interface
│   │   └── store.py              # SQLite-basierter Vektor-Store
│   ├── git/                      # Git-Integration
│   │   ├── github_client.py      # PyGithub-Wrapper (PR-Erstellung)
│   │   └── repo_ops.py           # GitPython-Wrapper (Clone, Branch, Commit)
│   ├── llm/                      # LLM-Provider
│   │   ├── ollama_provider.py    # Ollama-Integration (optional)
│   │   ├── openai_provider.py    # OpenAI-Chat-Completion
│   │   └── provider.py           # Base-Provider + Token-Estimator
│   ├── routers/                  # FastAPI-Endpunkte
│   │   ├── context_api.py        # /context/build
│   │   ├── health.py             # /health
│   │   ├── jobs.py               # /jobs/{id}, /jobs/{id}/cancel, /jobs/{id}/context
│   │   ├── memory.py             # /memory/{job_id}/notes, /memory/{job_id}/files
│   │   └── tasks.py              # POST /tasks (Job-Erstellung)
│   ├── telemetry/                # Monitoring
│   │   └── metrics.py            # Prometheus-kompatible Metriken
│   ├── workers/                  # Celery-Worker
│   │   ├── celery_app.py         # Celery-App-Konfiguration
│   │   └── job_worker.py         # execute_job Task (CTO+Coder-Workflow)
│   ├── deps.py                   # FastAPI-Dependencies (DB-Session)
│   └── main.py                   # FastAPI-App-Entrypoint
├── db/migrations/                # SQL-Migrationen
│   └── 202405290001_add_context.sql
├── scripts/                      # Automatisierungsskripte
│   ├── run.ps1                   # Windows: Start API+Worker
│   ├── run.sh                    # Linux: Start API+Worker
│   ├── seed-context.ps1          # Windows: Context-Demo
│   ├── seed-demo.ps1             # Windows: Job-Demo
│   ├── seed-demo.sh              # Linux: Job-Demo
│   ├── setup.ps1                 # Windows: uv sync + Redis
│   └── setup.sh                  # Linux: uv sync + Redis
├── tests/                        # Test-Suite
│   ├── e2e_context_test.py       # End-to-End Context-Engine-Test
│   ├── e2e_demo_test.py          # End-to-End Job-Workflow-Test
│   └── unit/                     # Unit-Tests
│       ├── compactor_budget_test.py
│       ├── curator_score_test.py
│       ├── embeddings_store_test.py
│       ├── memory_crud_test.py
│       ├── test_diffs.py
│       ├── test_limits.py
│       └── test_pricing.py
├── webui/                        # Gradio Web-UI
│   └── app_gradio.py             # UI-Entrypoint (unabhängig von app/)
├── AGENTS.md                     # Agent-Spezifikation (System-Policy)
├── docker-compose.yml            # Redis-Container
├── LICENSE                       # MIT-Lizenz
├── pricing.json                  # LLM-Preise (USD/1K-Tokens)
├── pyproject.toml                # Projekt-Metadaten & Dependencies
├── README.md                     # Projektdokumentation
└── uv.lock                       # Locked Dependencies
```

---

## 3. Architektur

### 3.1 Systemübersicht

```
┌──────────────────────────────────────────────────────────────────┐
│                         Client Layer                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │  Gradio UI   │    │  REST Client │    │  curl/Postman│       │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘       │
│         │                   │                    │                │
└─────────┼───────────────────┼────────────────────┼────────────────┘
          │                   │                    │
          └───────────────────┼────────────────────┘
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                      FastAPI Application                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Routers: /tasks, /jobs, /health, /memory, /context     │    │
│  └────────────────────────┬─────────────────────────────────┘    │
│                           │                                       │
│  ┌────────────────────────▼─────────────────────────────────┐    │
│  │  Dependencies: DB-Session, AgentsSpec, Config            │    │
│  └────────────────────────┬─────────────────────────────────┘    │
└───────────────────────────┼───────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│                       Celery Worker                               │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Task: execute_job(job_id)                              │    │
│  │  ┌──────────────────────────────────────────────────┐   │    │
│  │  │  1. CTO-Agent: Plan erstellen (JSON)             │   │    │
│  │  │  2. Context Engine: Kontext kuratieren           │   │    │
│  │  │  3. Coder-Agent: Steps implementieren (Diffs)    │   │    │
│  │  │  4. Git: Branch, Commit, Push, PR                │   │    │
│  │  └──────────────────────────────────────────────────┘   │    │
│  └────────────────────────┬─────────────────────────────────┘    │
└───────────────────────────┼───────────────────────────────────────┘
                            │
          ┌─────────────────┼─────────────────┐
          ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   SQLite DB  │  │  Redis Queue │  │  GitHub API  │
│  ┌─────────┐ │  │  (Celery)    │  │  (PyGithub)  │
│  │ Jobs    │ │  └──────────────┘  └──────────────┘
│  │ Steps   │ │
│  │ Memory  │ │  ┌──────────────┐  ┌──────────────┐
│  │ Context │ │  │  OpenAI API  │  │  File System │
│  │ Costs   │ │  │  (LLM+Embed) │  │  (Artifacts) │
│  └─────────┘ │  └──────────────┘  └──────────────┘
└──────────────┘
```

### 3.2 Datenfluss: Task → Pull Request

```
1. POST /tasks
   └─> JobModel erstellt (status=PENDING)
   └─> Celery-Task: execute_job(job_id)

2. execute_job: CTO-Phase
   └─> Context Engine: Gather (Task, Memory, History)
   └─> CTO-Agent: create_plan(task)
       └─> LLM-Request (MODEL_CTO, z.B. gpt-4.1-mini)
       └─> JSON-StepPlan: [{"title", "rationale", "acceptance", "files", "commands"}]
   └─> JobStepModel(type="plan") für jeden Step erstellt

3. execute_job: Coder-Phase (Loop über Steps)
   └─> Context Engine: Gather (Task, Step, Memory, Repo, Artifacts, History, Docs)
   └─> Coder-Agent: implement_step(task, step)
       └─> LLM-Request (MODEL_CODER, z.B. gpt-4.1)
       └─> Unified Diff
   └─> Diff anwenden (apply_unified_diff)
   └─> Git-Commit (commit_all)
   └─> Cost-Tracking, Memory-Update, Step=completed

4. execute_job: PR-Phase
   └─> Git: push_branch(feature_branch)
   └─> GitHub: open_pull_request(title, body, head, base)
   └─> JobModel: pr_links.append(pr_url), status=COMPLETED
```

### 3.3 Context Engine: Multi-Source-Retrieval

Die Context Engine ist das Herzstück der Token-Budget-Verwaltung:

```
ContextEngine.build_context(job_id, step_id, role, task, step, base_messages)
  │
  ├─> 1. Archivist: maintain(job_id)
  │     └─> Kompaktiert Memory wenn >80% Limit
  │
  ├─> 2. Gather Candidates (6 Quellen):
  │     ├─> Task (Pflicht)
  │     ├─> Step (Pflicht)
  │     ├─> Memory Notes (MemoryStore)
  │     ├─> Repo Snippets (step["files"] oder rglob)
  │     ├─> Artifacts (./artifacts/{job_id}/*.json)
  │     ├─> History (MessageSummaryModel, letzte 10)
  │     └─> External Docs (Embedding-Similarity-Search)
  │
  ├─> 3. Curator: rank(query, candidates)
  │     └─> BM25 + Embedding-Cosine → Score
  │     └─> TopK (CURATOR_TOPK=12), MinScore (CURATOR_MIN_SCORE=0.12)
  │
  ├─> 4. Compactor: compact_candidates(ranked, budget, threshold)
  │     └─> Wenn über threshold_ratio → Kompaktierung (z.B. erste 1000 Zeichen)
  │
  ├─> 5. Budget-Fitting:
  │     └─> Verfügbares Budget = CONTEXT_BUDGET_TOKENS - OUTPUT_RESERVE
  │     └─> Kandidaten bis Budget-Limit hinzufügen, Rest clippen
  │
  ├─> 6. Hard-Cap-Drop:
  │     └─> Wenn Gesamt-Tokens > CONTEXT_HARD_CAP_TOKENS → Letzte Items droppen
  │
  ├─> 7. Curator-Agent: build_hints(query, selected)
  │     └─> Human-readable Hints (z.B. "[repo score=0.85] main.py: def foo()...")
  │
  ├─> 8. Diagnostics persistieren:
  │     └─> ContextMetricModel (DB)
  │     └─> ./artifacts/{job_id}/context_{step_id}.json
  │
  └─> Return: ContextBuildResult(messages, diagnostics, candidates, hints)
```

**Budget-Parameter:**
- `CONTEXT_BUDGET_TOKENS` (64000): Haupt-Token-Budget
- `CONTEXT_OUTPUT_RESERVE_TOKENS` (8000): Reserve für LLM-Output
- `CONTEXT_HARD_CAP_TOKENS` (70000): Absolute Obergrenze
- `CONTEXT_COMPACT_THRESHOLD_RATIO` (0.6): Kompaktierung ab 60% Budget

---

## 4. Implementierte Agenten

### 4.1 CTOAgent (`app/agents/cto.py`)

**Verantwortung:** Task-Analyse und StepPlan-Erstellung

**Workflow:**
1. Empfängt Task-Beschreibung
2. Baut Prompt aus AGENTS.md Sektion "CTO-AI"
3. LLM-Request (MODEL_CTO)
4. Parse JSON-Array: `[{"title", "rationale", "acceptance", "files", "commands"}]`

**Dry-Run-Modus:**
- Gibt Mock-Plan zurück ohne LLM-Call

**Fehlerbehandlung:**
- JSON-Parse-Fehler → Exception mit Logging

**Code-Referenz:** `app/agents/cto.py:21-50`

---

### 4.2 CoderAgent (`app/agents/coder.py`)

**Verantwortung:** Step-Implementierung als Unified Diff

**Workflow:**
1. Empfängt Task + Step
2. Baut Prompt aus AGENTS.md Sektion "CODER-AI"
3. LLM-Request (MODEL_CODER)
4. Returned Dict: `{"diff", "summary", "tokens_in", "tokens_out"}`

**Diff-Format:**
- Unified Diff (`---`, `+++`, `@@`)
- Oder Full-File-Marker `<FILE>::FULL`

**Dry-Run-Modus:**
- Gibt leeren Diff zurück

**Code-Referenz:** `app/agents/coder.py:21-43`

---

### 4.3 ArchivistAgent (`app/agents/archivist_agent.py`)

**Verantwortung:** Memory-Kompaktierung bei >80% Limit

**Workflow:**
1. `maintain(session, job_id)` prüft Memory-Itemanzahl
2. Wenn >80% von `MEMORY_MAX_ITEMS_PER_JOB` (2000):
   - Erstellt Snapshot der ältesten Items (alle außer letzten 10)
   - Speichert als `memory/{job_id}/archive_{timestamp}.json`
   - Löscht archivierte Notes aus DB

**Notizschema:**
```json
{
  "type": "Decision|Constraint|Todo|Glossary|Link",
  "title": "string",
  "body": "string",
  "tags": ["string"],
  "stepId": "string"
}
```

**Code-Referenz:** `app/agents/archivist_agent.py:22-46`

---

### 4.4 CuratorAgent (`app/agents/curator_agent.py`)

**Verantwortung:** Human-readable Hints für finale Prompts

**Workflow:**
1. Empfängt Query + RankedCandidates
2. Generiert Hints im Format: `[{source} score={score}] {title} {snippet}`
3. Snippet = erste 3 Zeilen des Contents

**Beispiel-Output:**
```
[repo score=0.85] main.py def create_app(): FastAPI app factory
[memory score=0.72] Decision Use PostgreSQL for production
[history score=0.65] cto-plan Analyzed task: Add OAuth2 login
```

**Code-Referenz:** `app/agents/curator_agent.py:15-28`

---

## 5. Datenbank-Schema

### 5.1 Modelle

#### JobModel
- **Primärschlüssel:** id (UUID)
- **Felder:** task, repo_owner, repo_name, branch_base, status, budget_usd, max_requests, max_minutes, model_cto, model_coder, cost_usd, tokens_in, tokens_out, requests_made, started_at, finished_at, cancelled, last_action, pr_links (JSON), agents_hash
- **Beziehungen:** steps (1:N), costs (1:N)

#### JobStepModel
- **Primärschlüssel:** id (UUID)
- **Felder:** job_id (FK), name, step_type (plan|execution), status, details, started_at, finished_at
- **Beziehungen:** job (N:1)

#### CostEntryModel
- **Primärschlüssel:** id (UUID)
- **Felder:** job_id (FK), provider, model, tokens_in, tokens_out, cost_usd
- **Beziehungen:** job (N:1)

#### MemoryItemModel
- **Primärschlüssel:** id (UUID)
- **Felder:** job_id (FK), kind (note|file), key, content

#### MemoryFileModel
- **Primärschlüssel:** id (UUID)
- **Felder:** job_id (FK), path, bytes (LargeBinary)

#### MessageSummaryModel
- **Primärschlüssel:** id (UUID)
- **Felder:** job_id (FK), step_id, role, summary, tokens

#### EmbeddingIndexModel
- **Primärschlüssel:** id (UUID)
- **Felder:** scope (doc|code), ref_id, text, vector (JSON)

#### ContextMetricModel
- **Primärschlüssel:** id (UUID)
- **Felder:** job_id (FK), step_id, tokens_final, tokens_clipped, compact_ops, details (JSON)

**Code-Referenz:** `app/db/models.py:1-138`

---

## 6. API-Endpoints

### 6.1 Health (`/health`)
- **GET /health**
  - Response: `{"ok": true, "db": "ok", "redis": "ok", "version": "0.1.0"}`

### 6.2 Tasks (`/tasks`)
- **POST /tasks**
  - Body: `TaskCreateRequest`
  - Response: `{"job_id": "uuid"}` (202 Accepted)
  - Enqueued Celery-Task: `execute_job(job_id)`

### 6.3 Jobs (`/jobs`)
- **GET /jobs/{job_id}**
  - Response: `JobResponse` (status, cost, progress, pr_links)
- **POST /jobs/{job_id}/cancel**
  - Sets `job.cancelled=True`
- **GET /jobs/{job_id}/context**
  - Response: `ContextDiagnosticsResponse` (tokens, sources, hints)

### 6.4 Memory (`/memory`)
- **GET /memory/{job_id}/notes**
  - Returns: List of Memory Notes
- **POST /memory/{job_id}/notes**
  - Body: Note-Schema JSON
- **GET /memory/{job_id}/files**
  - Returns: List of Memory Files
- **POST /memory/{job_id}/files**
  - Upload File (bytes)

### 6.5 Context (`/context`)
- **POST /context/build**
  - Body: `{"job_id", "step_id", "role", "task", "step"}`
  - Response: `ContextBuildResult`

**Code-Referenz:** `app/routers/*.py`

---

## 7. Konfiguration

### 7.1 Umgebungsvariablen (`.env`)

```bash
# API
APP_PORT=3000

# Redis
REDIS_URL=redis://localhost:6379/0

# Database
DB_PATH=./data/orchestrator.db

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
MODEL_CTO=gpt-4.1-mini
MODEL_CODER=gpt-4.1

# GitHub
GITHUB_TOKEN=ghp_...
GITHUB_OWNER=your-org
GITHUB_REPO=your-repo

# Budgets
BUDGET_USD_MAX=5.0
MAX_REQUESTS=300
MAX_WALLCLOCK_MINUTES=720

# Merge Strategy
MERGE_CONFLICT_BEHAVIOR=pr  # pr|theirs|direct_push
ALLOW_DIRECT_PUSH=false
ALLOW_UNSAFE_AUTOMERGE=false

# Debug
DRY_RUN=false
LOG_LEVEL=info

# Context Engine
CONTEXT_ENGINE_ENABLED=true
EMBEDDING_MODEL=text-embedding-3-large
CONTEXT_BUDGET_TOKENS=64000
CONTEXT_OUTPUT_RESERVE_TOKENS=8000
CONTEXT_HARD_CAP_TOKENS=70000
CONTEXT_COMPACT_THRESHOLD_RATIO=0.6

# Memory
MEMORY_MAX_ITEMS_PER_JOB=2000
MEMORY_MAX_BYTES_PER_ITEM=20000

# Retriever
RETRIEVER_MAX_FILES=200
RETRIEVER_MAX_SNIPPET_TOKENS=2000

# Curator
JIT_ENABLE=true
CURATOR_TOPK=12
CURATOR_MIN_SCORE=0.12
```

**Code-Referenz:** `app/core/config.py:11-73`

---

## 8. Deployment

### 8.1 Setup (Erstmaliges Setup)

**Windows:**
```powershell
pwsh -File scripts/setup.ps1
```

**Linux:**
```bash
./scripts/setup.sh
```

**Was passiert:**
1. Python-Interpreter-Auswahl (bevorzugt 3.12/3.13)
2. uv installiert `.venv`
3. `uv sync --extra tests`
4. Redis via Docker Compose gestartet
5. SQLite-DB initialisiert

### 8.2 Laufzeit

**Terminal 1 (API + Worker):**
```bash
# Windows
pwsh -File scripts/run.ps1

# Linux
./scripts/run.sh
```

**Terminal 2 (Gradio UI - optional):**
```bash
uv run python -m webui.app_gradio
```

**Demo-Job starten:**
```bash
# Windows
pwsh -File scripts/seed-demo.ps1

# Linux
./scripts/seed-demo.sh
```

### 8.3 Docker (Redis)

```yaml
services:
  orchestrator-redis:
    image: redis:7-alpine
    container_name: orchestrator-redis
    ports:
      - "6379:6379"
    command: ["redis-server", "--appendonly", "yes"]
    restart: unless-stopped
```

**Start:**
```bash
docker compose up -d
```

**Code-Referenz:** `docker-compose.yml`, `scripts/setup.*`, `scripts/run.*`

---

## 9. Tests

### 9.1 Test-Struktur

```
tests/
├── e2e_context_test.py      # Context Engine End-to-End
├── e2e_demo_test.py         # Full Job-Workflow (Dry-Run)
└── unit/
    ├── compactor_budget_test.py
    ├── curator_score_test.py
    ├── embeddings_store_test.py
    ├── memory_crud_test.py
    ├── test_diffs.py
    ├── test_limits.py
    └── test_pricing.py
```

### 9.2 Ausführung

```bash
uv run pytest
```

**pytest.ini_options:**
- `testpaths = ["tests"]`
- `norecursedirs = ["webui"]`

**Code-Referenz:** `pyproject.toml:33-38`, `tests/**/*.py`

---

## 10. Fehlende Features & TODOs

### 10.1 AGENTS.md-Policy nicht vollständig implementiert

**Merge-Strategien:**
- ✅ `MERGE_CONFLICT_BEHAVIOR=pr` → Implementiert
- ❌ `theirs` (lokale Konfliktlösung) → Nicht implementiert
- ❌ `direct_push` (ohne PR) → `ALLOW_DIRECT_PUSH` existiert, aber keine Logik

**Empfehlung:**
- In `app/workers/job_worker.py:279-305` Merge-Logik erweitern

### 10.2 Fehlende `.env.example`

**Problem:**
- README.md:23 erwähnt `.env.example`, aber Datei existiert nicht

**Empfehlung:**
- `.env.example` erstellen mit allen Variablen (ohne Secrets)

### 10.3 Ollama-Provider nicht genutzt

**Status:**
- `app/llm/ollama_provider.py` existiert
- `job_worker.py:30-33` nutzt nur OpenAI oder DryRun

**Empfehlung:**
- Config-Option `LLM_PROVIDER=openai|ollama` hinzufügen
- Provider-Selection erweitern

### 10.4 Keine Prometheus-Metriken exportiert

**Status:**
- `app/telemetry/metrics.py` existiert (leer oder minimal)
- Kein `/metrics` Endpoint

**Empfehlung:**
- `prometheus_client` Integration
- Metriken: `jobs_total`, `jobs_failed`, `llm_requests_total`, `context_tokens_total`

### 10.5 Keine Retry-Logik bei LLM-Failures

**Problem:**
- `provider.generate()` wirft Exception bei Timeout/Rate-Limit
- Keine automatische Retry (exponential backoff)

**Empfehlung:**
- `tenacity` Library nutzen
- Retry-Decorator für `BaseLLMProvider.generate()`

### 10.6 Keine Multi-Repo-Unterstützung

**Problem:**
- Job-Modell: 1 Job = 1 Repo
- Kein Support für Monorepos oder Cross-Repo-Changes

**Empfehlung:**
- `JobModel.repos` als JSON-Array
- Retriever erweitern für Multi-Repo-Snippets

### 10.7 Fehlende Dokumentation

**Status:**
- Kein `docs/` Verzeichnis
- Keine ADRs (Architecture Decision Records)
- Keine API-Docs außer FastAPI-Auto-Docs

**Empfehlung:**
- `docs/architecture/` für ADRs
- `docs/api/` für erweiterte API-Docs
- `docs/deployment/` für Production-Deployment-Guide

### 10.8 Keine GitHub Actions CI/CD

**Problem:**
- Keine `.github/workflows/` für Tests/Linting

**Empfehlung:**
- CI-Pipeline: `pytest`, `ruff`, `mypy`
- CD-Pipeline: Docker-Build, Release-Tags

### 10.9 Keine Observability (Tracing)

**Problem:**
- Strukturierte Logs vorhanden (structlog)
- Keine Distributed Tracing (OpenTelemetry)

**Empfehlung:**
- OpenTelemetry-Integration
- Trace-IDs durch CTO → Coder → Git-Workflow

### 10.10 Memory-Compaction nur nach Item-Count

**Problem:**
- `ArchivistAgent.maintain()` prüft nur `len(notes)`
- Ignoriert Byte-Size (obwohl `MEMORY_MAX_BYTES_PER_ITEM` existiert)

**Empfehlung:**
- Zusätzliche Byte-Size-Prüfung
- Kompaktierung bei >80% Byte-Limit

---

## 11. Empfohlene Verbesserungen

### 11.1 Kurzfristig (Sprint 1-2)

1. **`.env.example` erstellen**
   - Priorität: Hoch
   - Aufwand: 30 Min

2. **Ollama-Provider aktivieren**
   - Priorität: Mittel
   - Aufwand: 2h

3. **Retry-Logik für LLM-Calls**
   - Priorität: Hoch
   - Aufwand: 4h

4. **GitHub Actions CI**
   - Priorität: Hoch
   - Aufwand: 4h

### 11.2 Mittelfristig (Sprint 3-5)

5. **Merge-Strategien "theirs" und "direct_push"**
   - Priorität: Mittel
   - Aufwand: 8h

6. **Prometheus-Metriken**
   - Priorität: Mittel
   - Aufwand: 6h

7. **Multi-Repo-Support**
   - Priorität: Niedrig
   - Aufwand: 16h

8. **Dokumentation (`docs/architecture/`, `docs/api/`)**
   - Priorität: Hoch
   - Aufwand: 12h

### 11.3 Langfristig (Sprint 6+)

9. **OpenTelemetry Tracing**
   - Priorität: Niedrig
   - Aufwand: 12h

10. **Memory-Compaction Byte-Size**
    - Priorität: Niedrig
    - Aufwand: 4h

11. **Web-UI: Job-Logs in Echtzeit (WebSocket)**
    - Priorität: Mittel
    - Aufwand: 16h

12. **PostgreSQL-Support (alternative zu SQLite)**
    - Priorität: Niedrig
    - Aufwand: 8h

---

## 12. Technische Schulden

### 12.1 Hardcoded Werte

**Locations:**
- `app/context/engine.py:293` → Hard-Cap-Drop-Logic (while-loop ohne Max-Iterationen)
- `app/context/retrievers/history.py:10` → `limit=10` hardcoded

**Empfehlung:**
- Config-Variablen `CONTEXT_MAX_DROP_ITERATIONS=100`
- Config-Variable `RETRIEVER_HISTORY_LIMIT=10`

### 12.2 Fehlende Type-Hints

**Locations:**
- `app/context/curator.py:15` → `build_hints` keine Return-Type
- `app/workers/job_worker.py:58` → `_run_coro` keine Generics

**Empfehlung:**
- `mypy --strict` aktivieren
- Schrittweise Type-Hints ergänzen

### 12.3 Threading-Workaround in Celery-Worker

**Location:**
- `app/workers/job_worker.py:58-79` → `_run_coro()` nutzt Thread für asyncio.run()

**Problem:**
- Fragil, wenn Celery bereits Event-Loop hat

**Empfehlung:**
- Celery 5.4+ nutzt `eventlet` oder `gevent`
- Entweder: `celery[gevent]` oder Async-Celery-Tasks

### 12.4 SQLite-Concurrency-Risiko

**Problem:**
- SQLite hat `BEGIN IMMEDIATE` nicht per Default
- Mehrere Worker könnten zu `database is locked` führen

**Empfehlung:**
- `connect_args={"timeout": 20, "check_same_thread": False}` in `engine.py`
- Oder: PostgreSQL für Production

---

## 13. Sicherheitsanalyse

### 13.1 Secrets-Management

**Gut:**
- `.env` für Secrets (nicht committed)
- `pyproject.toml` keine Secrets

**Risiko:**
- Keine `.env` Verschlüsselung
- Secrets in Memory (RAM) durch Celery-Worker

**Empfehlung:**
- HashiCorp Vault oder AWS Secrets Manager
- `cryptography` Library für lokale `.env` Encryption

### 13.2 Input-Validierung

**Gut:**
- Pydantic-Modelle für alle API-Requests
- `Field(..., ge=0)` für Budget/Requests

**Risiko:**
- `task` Field ist unbegrenzter Text → DoS-Risiko
- Keine Rate-Limiting auf API-Ebene

**Empfehlung:**
- `task` Field: `Field(..., max_length=10000)`
- FastAPI Rate-Limiting via `slowapi`

### 13.3 Code-Injection via Unified Diff

**Risiko:**
- LLM generiert Diff → `apply_unified_diff()` schreibt Files
- Keine Sandbox → Beliebiger Code-Execution möglich

**Empfehlung:**
- Whitelisting erlaubter Dateipfade (z.B. nur innerhalb Repo)
- `pathlib.resolve()` gegen Path-Traversal

**Code-Referenz:** `app/core/diffs.py:53-87`

### 13.4 GitHub-Token-Berechtigung

**Risiko:**
- `GITHUB_TOKEN` benötigt `repo`-Scope
- Könnte für Missbrauch genutzt werden (z.B. Branch-Deletion)

**Empfehlung:**
- Fine-grained Personal Access Token (nur PR-Erstellung)
- GitHub App statt PAT

---

## 14. Performance-Analyse

### 14.1 Bottlenecks

**Identifizierte:**
1. **LLM-Latenz:** CTO-Plan + N*Coder-Steps → 10-60s pro Step
2. **Context-Engine:** Embedding-Similarity-Search bei `JIT_ENABLE=true`
3. **Git-Clone:** Große Repos (>100MB) → 5-30s Clone-Zeit

**Empfehlung:**
1. **LLM-Streaming:** OpenAI Streaming-API nutzen (reduziert Time-to-First-Token)
2. **Embedding-Cache:** In-Memory-Cache für wiederholte Queries
3. **Git-Shallow-Clone:** `--depth 1` für Feature-Branch

### 14.2 Skalierung

**Aktuell:**
- 1 Celery-Worker → 1 Job parallel
- SQLite → Single-Writer-Lock

**Für Production:**
- N Celery-Worker (horizontal scaling)
- PostgreSQL statt SQLite
- Redis-Cluster für Celery-Broker

**Code-Referenz:** `docker-compose.yml` (nur Redis, kein Worker-Scaling)

---

## 15. Zusammenfassung

### 15.1 Stärken

✅ **Vollständige Multi-Agent-Pipeline:** CTO → Coder → Git → PR
✅ **Production-ready Config:** Budget-Limits, Cost-Tracking, Strukturierte Logs
✅ **Context Engine:** 6-Source-Retrieval mit Budget-Management
✅ **Plattformübergreifend:** Windows + Linux Support (PowerShell + Bash)
✅ **Testing:** Unit + E2E-Tests vorhanden
✅ **Web-UI:** Gradio-basiertes Interface

### 15.2 Schwächen

❌ **Fehlende Produktionsreife:** Keine CI/CD, keine Observability
❌ **SQLite-Limitation:** Nicht für Multi-Worker-Deployments
❌ **Unvollständige AGENTS.md-Policy:** Merge-Strategien fehlen
❌ **Keine Retry-Logik:** LLM-Failures führen zu Job-Abbruch
❌ **Sicherheitsrisiken:** Code-Injection via Diff, keine Secrets-Verschlüsselung

### 15.3 Nächste Schritte

**Sofort (Woche 1):**
1. `.env.example` erstellen
2. GitHub Actions CI/CD einrichten
3. Retry-Logik für LLM-Calls

**Kurzfristig (Monat 1):**
4. Ollama-Provider aktivieren
5. Prometheus-Metriken
6. Dokumentation (`docs/`)

**Mittelfristig (Quartal 1):**
7. Multi-Repo-Support
8. PostgreSQL-Migration
9. OpenTelemetry-Tracing

---

**Analysiert von:** Claude Code
**Datum:** 2025-10-05
**Version:** 1.0

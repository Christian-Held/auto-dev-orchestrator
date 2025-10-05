# Auto Dev Orchestrator (Python)

Auto Dev Orchestrator ist ein FastAPI- und Celery-basiertes Grundgerüst, das automatisierte Softwarelieferung orchestriert. Das System liest zur Laufzeit **AGENTS.md**, um CTO- und Coder-Agenten anzuleiten, überwacht Budget- und Request-Limits und erstellt Pull Requests mit GitHub-Integration.

## Features
- FastAPI REST-API (`/tasks`, `/jobs/{id}`, `/jobs/{id}/cancel`, `/health`).
- Celery Worker mit Redis-Broker für die schrittweise Ausführung (`plan → code → verify → pr`).
- SQLite-Datenbank (SQLAlchemy) zur Nachverfolgung von Jobs, Steps und Kosten.
- Strukturierte JSON-Logs über structlog.
- LLM-Provider-Abstraktion (OpenAI, Ollama optional) mit Kosten-Tracking.
- GitHub-Integration über PyGithub und GitPython.
- Windows-freundliche PowerShell-Skripte (`scripts/`).
- Tests mit pytest (Unit & E2E-Dry-Run).

## Voraussetzungen
- Windows 11 oder Linux mit laufendem Docker (Docker Desktop bzw. Docker Engine).
- Python 3.12 oder 3.13 wird empfohlen. 3.11 und 3.14 funktionieren im Best-Effort-Modus.
- [uv](https://docs.astral.sh/uv/) (wird bei Bedarf automatisch über den aktiven Interpreter installiert).
- Windows: PowerShell 7+ (`pwsh`).
- Linux: Bash 4+.

## Quickstart
1. Kopiere `.env.example` zu `.env` und fülle die benötigten Schlüssel (`OPENAI_API_KEY`, `GITHUB_TOKEN`, `GITHUB_OWNER`, `GITHUB_REPO`, `REDIS_URL`, `DB_PATH`, Limits usw.).
2. Führe das Setup-Skript für deine Plattform aus:
   - **Windows (PowerShell 7+)**: `pwsh -File scripts/setup.ps1`
   - **Linux (Bash)**: `./scripts/setup.sh`
   Beide Skripte wählen automatisch einen kompatiblen Python-Interpreter (bevorzugt 3.12/3.13), legen eine lokale `.venv` im Repo an, synchronisieren Laufzeit- **und Testabhängigkeiten** via `uv sync --extra tests` und starten Redis über Docker Compose.
3. Starte API und Worker aus dem Repo-Root:
   - **Windows**: `pwsh -File scripts/run.ps1`
   - **Linux**: `./scripts/run.sh`
   Die Skripte laden `.env`, protokollieren den ausgewählten Interpreter und starten `uv run uvicorn app.main:app` sowie `uv run celery -A app.workers.celery_app worker -l info`.

   **Hinweis**: Der Worker findet Tasks automatisch ohne `--include` Flag. Git-Push verwendet automatisch `GITHUB_TOKEN` aus `.env` für Authentication.
4. Öffne für die Weboberfläche ein neues Terminal und starte `uv run python -m webui.app_gradio`. Die UI läuft unabhängig vom Backend und nutzt dieselben REST-Endpunkte.
5. Optional kannst du nach erfolgreichem Health-Check die Demo-Seed-Skripte verwenden:
   - **Windows**: `pwsh -File scripts/seed-demo.ps1`
   - **Linux**: `./scripts/seed-demo.sh`
   Sie warten auf `/health`, legen einen Demo-Task an und verfolgen den Job inkl. Kosten und PR-Links.

## Tests
```powershell
uv run pytest
```

Unter Linux funktioniert derselbe Befehl. Die Tests sind so konfiguriert, dass das `webui`-Verzeichnis von der Discovery ausgeschlossen bleibt.

## Troubleshooting
- Aktive Python-Version prüfen: `python --version`
- Verfügbare Interpreter anzeigen: `uv python list`
- Kompatible Interpreter per uv auffinden (ohne Downgrade-Zwang): `uv python find 'cpython>=3.12,<3.14'`
- Falls mehrere Python-Versionen installiert sind, kannst du mit `uv sync --python <pfad-zum-interpreter>` explizit wählen, ohne die Minor-Version global zu pinnen.

## Gradio Web UI
Die Weboberfläche befindet sich in `webui/app_gradio.py` und bleibt vom Python-Paket `app` getrennt. Sie nutzt Gradio Blocks mit separaten Accordions für Secrets und Settings, kann `.env` lokal speichern und interagiert mit dem Backend über die REST-Endpunkte (`/health`, `/tasks`, `/jobs/{id}`).

```powershell
uv run python -m webui.app_gradio
```

## Architektur
Siehe `AGENTS.md` für Richtlinien der Agents. Die Anwendung speichert den Hash der Datei in der Datenbank und referenziert ihn in Pull-Requests.

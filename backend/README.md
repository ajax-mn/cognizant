# Text-to-SQL Analytics — Backend

FastAPI service that converts natural language questions into safe, read-only
PostgreSQL `SELECT` queries using Gemini / Claude Haiku with automatic local
Ollama fallback (`qwen2.5-coder:7b`) when offline, rate limited, or unconfigured,
executes them, and returns the results.


## Setup

1. Create a virtual    environment and install dependencies:
   ```
   python -m venv .venv
   .venv\Scripts\activate   (Windows)
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in:
   - `DATABASE_URL` — e.g. `postgresql+psycopg://user:password@localhost:5432/text_to_sql_db`
   - `ANTHROPIC_API_KEY` — your Anthropic API key

3. Create the database and load sample data:
   ```
   createdb text_to_sql_db
   psql "$env:DATABASE_URL" -f sample_schema.sql
   ```
   (Adjust connection details for your `psql` install/PATH.)

4. Run the server:
cd D:\cogni\backend
cd D:\cogni\frontend
   ```
   uvicorn main:app --reload
   cmd /c "npm run dev"
   ```
   The API will be available at http://localhost:8000 (docs at `/docs`).

## API

- `GET /health` — liveness check
- `GET /schema` — introspects and returns the database schema
- `POST /query` — `{ "question": "..." }` → generates SQL via Claude, validates
  it, executes it, and returns `{ question, sql, columns, rows, row_count }`
- `POST /execute-sql` — `{ "sql": "SELECT ..." }` → validates and runs a
  hand-written SELECT query directly

## Safety

All generated/submitted SQL passes through `sql_validator.py`, which requires
the statement to start with `SELECT`, rejects a fixed list of mutating
keywords (`DROP`, `ALTER`, `DELETE`, `INSERT`, `UPDATE`, `CREATE TABLE`,
`TRUNCATE`, `GRANT`, `REVOKE`), and rejects multi-statement input.

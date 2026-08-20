# Text-to-SQL Analytics — Backend

FastAPI service that converts natural language questions into safe SQL queries using Gemini or Claude Haiku, executes them against relational databases, and caches them in Redis with fine-grained schema-aware invalidation.

## Setup

1. **Create a virtual environment and install dependencies**:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate   # Windows
   # source .venv/bin/activate # macOS/Linux
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in:
   - `DATABASE_URL` — e.g. `postgresql+psycopg://user:password@localhost:5432/text_to_sql_db`
   - `GEMINI_API_KEY` — your Google Gemini API key
   - `GEMINI_MODEL` — optional model name (defaults to `gemini-2.5-flash`)

3. Create the database and load sample data:
   ```
   Fill in:
   - `DATABASE_URL` — PostgreSQL connection string
   - `GEMINI_API_KEY` or `ANTHROPIC_API_KEY` — LLM API Key
   - `REDIS_HOST` (default: `localhost`), `REDIS_PORT` (default: `6379`)

4. Run the server:
   ```
   uvicorn main:app --reload
   ```
   The API will be available at http://localhost:8000 (docs at `/docs`).
3. **Start Redis Server (Required for Caching)**:
   Choose **one** of the following options:

   - **Option A (Docker - Easiest & Recommended)**:
     From repository root:
     ```bash
     docker compose up -d
     ```
   - **Option B (Windows via Winget or WSL)**:
     ```bash
     winget install Redis.Redis
     # Or using WSL:
     # sudo apt install redis-server && sudo service redis-server start
     ```
   - **Option C (macOS)**:
     ```bash
     brew install redis && brew services start redis
     ```
   - **Option D (Free Cloud Redis - e.g. Upstash or Redis.com)**:
     Set your cloud Redis endpoint and password in `backend/.env`:
     ```env
     REDIS_HOST=your-redis-cloud-endpoint.com
     REDIS_PORT=6379
     REDIS_PASSWORD=your_password
     ```

- `GET /health` — liveness check
- `GET /schema` — introspects and returns the database schema
- `POST /query` — `{ "question": "..." }` → generates SQL via Gemini, validates
  it, executes it, and returns `{ question, sql, columns, rows, row_count }`
- `POST /execute-sql` — `{ "sql": "SELECT ..." }` → validates and runs a
  hand-written SELECT query directly
4. **Run the Backend Server**:
   ```bash
   uvicorn main:app --reload
   ```
   The API will be available at http://localhost:8000 (Swagger docs at `http://localhost:8000/docs`).

## API Endpoints

- `GET /health` — Health check
- `GET /schema` — Introspects database schema & relationships
- `POST /query` — Converts natural language to SQL, checks Redis cache, executes query
- `POST /execute-sql` — Runs a raw SQL query directly
- `POST /database/upload` — Upload ad-hoc SQLite database
- `GET /analytics/cache` — Observability metrics for cache hit rate, cost saved, and audit log

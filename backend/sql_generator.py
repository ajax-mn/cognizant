import os
import json
import logging
import urllib.request
import urllib.error
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _strip_markdown_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    if text.lower().startswith("sql\n"):
        text = text[4:].strip()
    return text


_SENTINEL = "INSUFFICIENT_DATA"


def _check_sentinel(sql: str) -> None:
    """Raise a user-friendly RuntimeError when the LLM signals it cannot
    answer the question from the schema (returns our sentinel string)."""
    if sql.strip().upper() == _SENTINEL:
        raise RuntimeError(
            "Your question doesn't seem to be about the available data. "
            "Please ask something specific, e.g. 'Show all orders' or "
            "'Total revenue by country'."
        )


def _generate_sql_using_gemini(question: str, schema_context: str, api_key: str) -> tuple[str, int]:
    prompt = f"""You are a SQL expert. Convert the following natural language question into a valid PostgreSQL query.

Database Schema:
{schema_context}

User Question: {question}

IMPORTANT RULES:
1. Return ONLY the SQL query, no markdown, no explanation.
2. Generate the most appropriate SQL statement (SELECT, INSERT, UPDATE, DELETE, ALTER, etc.).
3. Use appropriate JOINs, WHERE, GROUP BY, ORDER BY, LIMIT as needed.
4. If the question is ambiguous, make reasonable assumptions.
5. Ensure the query is syntactically correct.
6. If the question is NOT related to the database schema (e.g. greetings, random words, off-topic requests),
   respond with exactly the word: INSUFFICIENT_DATA — nothing else.

SQL Query:"""

    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    data = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 1000
        }
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            res_data_raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode("utf-8")
        try:
            err_json = json.loads(error_msg)
            if "error" in err_json and "message" in err_json["error"]:
                error_msg = err_json["error"]["message"]
        except Exception:
            pass

        if e.code == 429:
            raise RuntimeError("Gemini API quota exhausted. Please try again later.")
        elif e.code == 400:
            raise RuntimeError(f"Gemini API request error (400): {error_msg}")
        elif e.code == 403:
            raise RuntimeError("Gemini API key does not have permission. Check your API key.")
        else:
            raise RuntimeError(f"Gemini API error {e.code}: {error_msg}")
    except Exception as e:
        raise RuntimeError(f"Could not reach the Gemini API: {e}")

    try:
        res_data = json.loads(res_data_raw)
        candidates = res_data.get("candidates", [])
        if not candidates:
            raise RuntimeError("No candidates returned from Gemini API.")
        
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            raise RuntimeError("Empty content returned from Gemini API candidate.")
        
        sql = parts[0].get("text", "").strip()
        tokens_used = res_data.get("usageMetadata", {}).get("totalTokenCount", 0)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Failed to parse Gemini response: {e}")

    sql = _strip_markdown_fences(sql)
    _check_sentinel(sql)
    return sql, tokens_used


def _generate_sql_using_ollama(question: str, schema_context: str) -> tuple[str, int]:
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")

    prompt = f"""You are a SQL expert. Convert the following natural language question into a valid PostgreSQL query.

Database Schema:
{schema_context}

User Question: {question}

IMPORTANT RULES:
1. Return ONLY the SQL query, no markdown, no explanation.
2. Generate the most appropriate SQL statement (SELECT, INSERT, UPDATE, DELETE, ALTER, etc.).
3. Use appropriate JOINs, WHERE, GROUP BY, ORDER BY, LIMIT as needed.
4. If the question is ambiguous, make reasonable assumptions.
5. Ensure the query is syntactically correct.
6. If the question is NOT related to the database schema (e.g. greetings, random words, off-topic requests),
   respond with exactly the word: INSUFFICIENT_DATA — nothing else.

SQL Query:"""

    url = f"{ollama_base_url}/api/generate"
    data = {
        "model": ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1
        }
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            sql = res_data.get("response", "").strip()
            if not sql:
                raise RuntimeError("Empty response received from Ollama.")
            eval_count = res_data.get("eval_count") or 0
            prompt_eval_count = res_data.get("prompt_eval_count") or 0
            tokens_used = eval_count + prompt_eval_count
            sql = _strip_markdown_fences(sql)
            _check_sentinel(sql)
            return sql, tokens_used
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode("utf-8")
        raise RuntimeError(f"Ollama API request failed: {e.code} - {error_msg}")
    except Exception as e:
        raise RuntimeError(f"Failed to generate SQL using Ollama ({ollama_model}): {e}")


def generate_sql_from_question(question: str, schema_context: str) -> tuple[str, int]:
    """Generate SQL for `question`. Returns (sql, tokens_used).
    Primary generator: Google Gemini API (gemini-2.5-flash).
    Fallback generator: Local Ollama if Gemini is unconfigured or fails.
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    attempt_errors: list[str] = []

    # 1. Try Gemini if configured
    if gemini_key and gemini_key.strip() and not gemini_key.startswith("your_gemini_api_key") and not gemini_key.startswith("your_api_key"):
        try:
            return _generate_sql_using_gemini(question, schema_context, gemini_key.strip())
        except Exception as e:
            msg = f"Gemini error: {e}"
            logger.warning(f"{msg}. Falling back to local Ollama...")
            attempt_errors.append(msg)

    # 2. Fallback to Local Ollama
    try:
        print("ParleG Sindabad")
        return _generate_sql_using_ollama(question, schema_context)
    except Exception as ollama_err:
        attempt_errors.append(f"Ollama error: {ollama_err}")
        if len(attempt_errors) == 1 and not gemini_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Add GEMINI_API_KEY to backend/.env, or ensure local Ollama is running."
            )
        raise RuntimeError(
            f"SQL generation failed. Attempts: {'; '.join(attempt_errors)}"
        )

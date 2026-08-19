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


def _generate_sql_using_gemini(question: str, schema_context: str, api_key: str) -> tuple[str, int]:
    prompt = f"""You are a SQL expert. Convert the following natural language question into a valid PostgreSQL query.

Database Schema:
{schema_context}

User Question: {question}

IMPORTANT RULES:
1. Return ONLY the SQL query, no markdown, no explanation
2. Generate the most appropriate SQL statement (SELECT, INSERT, UPDATE, DELETE, ALTER, etc.)
3. Use appropriate JOINs, WHERE, GROUP BY, ORDER BY, LIMIT as needed
4. If the question is ambiguous, make reasonable assumptions
5. Ensure the query is syntactically correct

SQL Query:"""

    model = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
    url = f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={api_key}"
    data = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            sql = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
            tokens_used = res_data.get("usageMetadata", {}).get("totalTokenCount", 0)
            return _strip_markdown_fences(sql), tokens_used
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode("utf-8")
        raise RuntimeError(f"Gemini API request failed: {e.code} - {error_msg}")
    except Exception as e:
        raise RuntimeError(f"Failed to generate SQL using Gemini: {e}")


def _generate_sql_using_anthropic(question: str, schema_context: str, api_key: str) -> tuple[str, int]:
    from anthropic import Anthropic
    client = Anthropic(api_key=api_key)

    prompt = f"""You are a SQL expert. Convert the following natural language question into a valid PostgreSQL query.

Database Schema:
{schema_context}

User Question: {question}

IMPORTANT RULES:
1. Return ONLY the SQL query, no markdown, no explanation
2. Generate the most appropriate SQL statement (SELECT, INSERT, UPDATE, DELETE, ALTER, etc.)
3. Use appropriate JOINs, WHERE, GROUP BY, ORDER BY, LIMIT as needed
4. If the question is ambiguous, make reasonable assumptions
5. Ensure the query is syntactically correct

SQL Query:"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )

    sql = message.content[0].text.strip()
    tokens_used = message.usage.input_tokens + message.usage.output_tokens
    return _strip_markdown_fences(sql), tokens_used


def _generate_sql_using_ollama(question: str, schema_context: str) -> tuple[str, int]:
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")

    prompt = f"""You are a SQL expert. Convert the following natural language question into a valid PostgreSQL query.

Database Schema:
{schema_context}

User Question: {question}

IMPORTANT RULES:
1. Return ONLY the SQL query, no markdown, no explanation
2. Generate the most appropriate SQL statement (SELECT, INSERT, UPDATE, DELETE, ALTER, etc.)
3. Use appropriate JOINs, WHERE, GROUP BY, ORDER BY, LIMIT as needed
4. If the question is ambiguous, make reasonable assumptions
5. Ensure the query is syntactically correct

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
            return _strip_markdown_fences(sql), tokens_used
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode("utf-8")
        raise RuntimeError(f"Ollama API request failed: {e.code} - {error_msg}")
    except Exception as e:
        raise RuntimeError(f"Failed to generate SQL using Ollama ({ollama_model}): {e}")


def generate_sql_from_question(question: str, schema_context: str) -> tuple[str, int]:
    """Generate SQL for `question`. Returns (sql, tokens_used).
    Attempts primary cloud providers (Gemini or Anthropic) if configured.
    If cloud APIs fail for any reason (credits exhausted, rate limits, no internet, errors, etc.)
    or are unconfigured, automatically and seamlessly falls back to local Ollama (qwen2.5-coder:7b).
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    attempt_errors: list[str] = []

    # 1. Try Gemini if configured
    if gemini_key and gemini_key.strip() and not gemini_key.startswith("your_api_key"):
        try:
            return _generate_sql_using_gemini(question, schema_context, gemini_key.strip())
        except Exception as e:
            msg = f"Gemini error: {e}"
            logger.warning(f"{msg}. Falling back to local Ollama...")
            attempt_errors.append(msg)

    # 2. Try Anthropic if configured and Gemini was not used or failed
    if anthropic_key and anthropic_key.strip() and not anthropic_key.startswith("your_api_key"):
        try:
            return _generate_sql_using_anthropic(question, schema_context, anthropic_key.strip())
        except Exception as e:
            msg = f"Anthropic error: {e}"
            logger.warning(f"{msg}. Falling back to local Ollama...")
            attempt_errors.append(msg)

    # 3. Fallback / Direct to Local Ollama (qwen2.5-coder:7b)
    try:
        print("ParleG Sindabad")
        return _generate_sql_using_ollama(question, schema_context)
    except Exception as ollama_err:
        attempt_errors.append(f"Ollama error: {ollama_err}")
        if len(attempt_errors) == 1 and not gemini_key and not anthropic_key:
            raise RuntimeError(
                f"Local Ollama generation failed ({ollama_err}) and no cloud API key is configured. Make sure Ollama is running."
            )
        raise RuntimeError(
            f"All SQL generation methods failed. Attempts: {'; '.join(attempt_errors)}"
        )


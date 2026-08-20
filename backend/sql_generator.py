import os
import json
import urllib.request
import urllib.error
from dotenv import load_dotenv

load_dotenv()


def _strip_markdown_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
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

    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-3.5-flash:generateContent?key={api_key}"
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
        with urllib.request.urlopen(req) as response:
            res_data_raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise RuntimeError("Gemini API quota exhausted. Please try again later.")
        elif e.code == 400:
            raise RuntimeError("Gemini API key is invalid or the request was malformed.")
        elif e.code == 403:
            raise RuntimeError("Gemini API key does not have permission. Check your API key.")
        else:
            raise RuntimeError(f"Gemini API error {e.code}. Please try again.")
    except Exception:
        raise RuntimeError("Could not reach the Gemini API. Check your connection and API key.")

    try:
        res_data = json.loads(res_data_raw)
        sql = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
        tokens_used = res_data.get("usageMetadata", {}).get("totalTokenCount", 0)
    except (KeyError, IndexError, json.JSONDecodeError):
        raise RuntimeError("The model refused to answer or returned an unexpected response.")

    sql = _strip_markdown_fences(sql)
    _check_sentinel(sql)
    return sql, tokens_used


def generate_sql_from_question(question: str, schema_context: str) -> tuple[str, int]:
    """Generate SQL for `question`. Returns (sql, tokens_used) - tokens_used is a
    best-effort count taken from whichever provider's API response reports it."""
    gemini_key = os.getenv("GEMINI_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    if gemini_key:
        return _generate_sql_using_gemini(question, schema_context, gemini_key)
    elif anthropic_key:
        from anthropic import Anthropic
        client = Anthropic(api_key=anthropic_key)

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

        try:
            message = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:
            err = str(e).lower()
            if "rate_limit" in err or "rate limit" in err:
                raise RuntimeError("Claude API rate limit reached. Please wait and try again.")
            elif "overloaded" in err:
                raise RuntimeError("Claude API is overloaded. Please try again in a moment.")
            elif "authentication" in err or "invalid x-api-key" in err:
                raise RuntimeError("Anthropic API key is invalid. Check your configuration.")
            else:
                raise RuntimeError("Could not reach the Claude API. Check your connection and API key.")

        sql = message.content[0].text.strip()
        tokens_used = message.usage.input_tokens + message.usage.output_tokens
        sql = _strip_markdown_fences(sql)
        _check_sentinel(sql)
        return sql, tokens_used
    else:
        raise RuntimeError("No AI API key configured. Set GEMINI_API_KEY or ANTHROPIC_API_KEY in backend/.env.")

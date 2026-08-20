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


def _build_prompt(
    question: str,
    schema_context: str,
    previous_sql: str | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    dialect: str = "postgresql",
) -> str:
    context_sections = []
    is_sqlite = dialect.lower() == "sqlite"
    dialect_name = "SQLite" if is_sqlite else "PostgreSQL"

    if conversation_history:
        history_lines = []
        for msg in conversation_history:
            role = msg.get("role", "user").capitalize()
            content = msg.get("content", "")
            history_lines.append(f"{role}: {content}")
        if history_lines:
            context_sections.append("Conversation History:\n" + "\n".join(history_lines))

    if previous_sql:
        context_sections.append(f"Previous SQL Query:\n{previous_sql}")
        task_instruction = (
            f"You are a SQL expert. Modify or extend the previous {dialect_name} SELECT query based on the user's follow-up request.\n"
            "Preserve existing filters, joins, groupings, and column projections unless the follow-up request specifically asks to change, replace, or remove them."
        )
    else:
        task_instruction = f"You are a SQL expert. Convert the following natural language question into a {dialect_name} SELECT query."

    extra_context = ("\n\n" + "\n\n".join(context_sections)) if context_sections else ""
    user_label = "User Follow-up Request" if previous_sql else "User Question"

    date_guidance = (
        "6. For SQLite date/time manipulation, use strftime(...) (e.g. strftime('%Y-%m', col) for months, strftime('%Y', col) for years) or DATE_TRUNC."
        if is_sqlite
        else "6. Use standard PostgreSQL date/time functions as appropriate."
    )

    return f"""{task_instruction}

Database Schema:
{schema_context}{extra_context}

{user_label}: {question}

IMPORTANT RULES:
1. Return ONLY the SQL query, no markdown, no explanation
2. Generate ONLY SELECT queries
3. Use appropriate JOINs, WHERE, GROUP BY, ORDER BY, LIMIT as needed
4. If the question is ambiguous, make reasonable assumptions
5. Ensure the query is syntactically correct
{date_guidance}

SQL Query:"""


def _generate_sql_using_gemini(
    question: str,
    schema_context: str,
    api_key: str,
    previous_sql: str | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    dialect: str = "postgresql",
) -> tuple[str, int]:
    prompt = _build_prompt(
        question, schema_context, previous_sql, conversation_history, dialect=dialect
    )

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
            res_data = json.loads(response.read().decode("utf-8"))
            sql = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
            tokens_used = res_data.get("usageMetadata", {}).get("totalTokenCount", 0)
            return _strip_markdown_fences(sql), tokens_used
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode("utf-8")
        raise RuntimeError(f"Gemini API request failed: {e.code} - {error_msg}")
    except Exception as e:
        raise RuntimeError(f"Failed to generate SQL using Gemini: {e}")


def generate_sql_from_question(
    question: str,
    schema_context: str,
    previous_sql: str | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    dialect: str = "postgresql",
) -> tuple[str, int]:
    """Generate SQL for `question`. Returns (sql, tokens_used) - tokens_used is a
    best-effort count taken from whichever provider's API response reports it."""
    gemini_key = os.getenv("GEMINI_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    if gemini_key:
        return _generate_sql_using_gemini(
            question,
            schema_context,
            gemini_key,
            previous_sql=previous_sql,
            conversation_history=conversation_history,
            dialect=dialect,
        )
    elif anthropic_key:
        from anthropic import Anthropic
        client = Anthropic(api_key=anthropic_key)

        prompt = _build_prompt(
            question, schema_context, previous_sql, conversation_history, dialect=dialect
        )

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )

        sql = message.content[0].text.strip()
        tokens_used = message.usage.input_tokens + message.usage.output_tokens
        return _strip_markdown_fences(sql), tokens_used
    else:
        raise RuntimeError(
            "Neither GEMINI_API_KEY nor ANTHROPIC_API_KEY is set. Add one to backend/.env"
        )



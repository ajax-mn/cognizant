"""
question_validator.py

Lightweight pre-LLM guard. Only rejects inputs that are so trivially
invalid that sending them to the AI is pointless (and wastes quota).

Deeper relevance checking (greetings, off-topic questions, etc.) is
handled by the LLM itself via the INSUFFICIENT_DATA sentinel in the prompt.
"""


def validate_question(question: str, tables=None) -> None:
    """Raise ValueError for inputs that should never reach the LLM.

    Checks (in order):
    1. Too short — less than 4 characters after stripping whitespace.
    2. No alphabetic content — only digits, punctuation, or whitespace.

    The `tables` argument is accepted for API compatibility but unused.
    """
    q = question.strip()

    # 1. Too short to be a meaningful question
    if len(q) < 4:
        raise ValueError(
            "Invalid Query"
        )

    # 2. No alphabetic characters at all (e.g. "123", "???", "!!!!")
    if not any(c.isalpha() for c in q):
        raise ValueError("Invalid Query")

    # 3. Single word — must have at least one space (two or more tokens)
    if " " not in q:
        raise ValueError("Invalid Query")

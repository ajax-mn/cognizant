from sqlalchemy import inspect
from sqlalchemy.engine import Engine


def get_database_schema(engine: Engine) -> dict:
    """Introspect the database and return table/column metadata."""
    inspector = inspect(engine)
    tables = {}

    for table_name in inspector.get_table_names():
        columns = inspector.get_columns(table_name)
        tables[table_name] = [
            {"name": col["name"], "type": str(col["type"])}
            for col in columns
        ]

    return tables


def format_schema_for_context(tables: dict) -> str:
    """Format schema as readable text for LLM context."""
    schema_text = ""
    for table_name, columns in tables.items():
        schema_text += f"\nTable: {table_name}\n"
        for col in columns:
            schema_text += f"  - {col['name']} ({col['type']})\n"
    return schema_text

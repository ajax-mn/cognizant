from sqlalchemy import inspect
from sqlalchemy.engine import Engine

INTERNAL_APP_TABLES = ["query_cache", "dynamic_query_cache", "cache_audit_log"]


def get_database_schema(engine: Engine) -> dict:
    """Introspect the database and return table/column metadata, primary keys, and relationships,

    filtering out internal application tables and system tables.
    """
    inspector = inspect(engine)
    tables = {}
    relationships = []

    excluded_set = {t.lower() for t in INTERNAL_APP_TABLES}

    # Get all table names, excluding internal sqlite system tables and app cache tables
    all_tables = [
        t for t in inspector.get_table_names()
        if not t.startswith("sqlite_") and t.lower() not in excluded_set
    ]

    # Pre-collect foreign keys to identify FK columns and build relationships list
    table_fks: dict[str, list[dict]] = {}
    for table_name in all_tables:
        try:
            fks = inspector.get_foreign_keys(table_name)
            table_fks[table_name] = fks or []
            for fk in table_fks[table_name]:
                referred_table = fk.get("referred_table")
                constrained_cols = fk.get("constrained_columns") or []
                referred_cols = fk.get("referred_columns") or []

                # Ignore foreign keys that point to excluded internal tables
                if (
                    referred_table
                    and referred_table.lower() not in excluded_set
                    and not referred_table.startswith("sqlite_")
                ):
                    for s_col, t_col in zip(constrained_cols, referred_cols):
                        if s_col and t_col:
                            relationships.append({
                                "id": f"{table_name}.{s_col}->{referred_table}.{t_col}",
                                "source_table": table_name,
                                "source_column": s_col,
                                "target_table": referred_table,
                                "target_column": t_col,
                                "constraint_name": fk.get("name"),
                            })
        except Exception:
            table_fks[table_name] = []

    # Extract column definitions and primary keys for each table
    for table_name in all_tables:
        try:
            columns = inspector.get_columns(table_name)
        except Exception:
            columns = []

        try:
            pk_constraint = inspector.get_pk_constraint(table_name)
            pk_columns = set(pk_constraint.get("constrained_columns") or [])
        except Exception:
            pk_columns = set()

        # Set of foreign key column names in this table
        fk_columns = set()
        for fk in table_fks.get(table_name, []):
            referred_table = fk.get("referred_table")
            if (
                referred_table
                and referred_table.lower() not in excluded_set
                and not referred_table.startswith("sqlite_")
            ):
                for col in fk.get("constrained_columns") or []:
                    fk_columns.add(col)

        table_columns = []
        for col in columns:
            col_name = col["name"]
            is_pk = (col_name in pk_columns) or bool(col.get("primary_key", False))
            is_fk = col_name in fk_columns

            table_columns.append({
                "name": col_name,
                "type": str(col["type"]),
                "primary_key": is_pk,
                "is_foreign_key": is_fk,
                "nullable": bool(col.get("nullable", True)),
            })

        tables[table_name] = table_columns

    return {
        "tables": tables,
        "relationships": relationships,
    }


def format_schema_for_context(schema_data: dict) -> str:
    """Format schema as readable text for AI context, including PKs and FK relationships."""
    if not isinstance(schema_data, dict):
        return ""

    tables = schema_data.get("tables", schema_data) if "tables" in schema_data else schema_data
    relationships = schema_data.get("relationships", []) if "relationships" in schema_data else []

    schema_text = ""
    for table_name, columns in tables.items():
        schema_text += f"\nTable: {table_name}\n"
        for col in columns:
            pk_tag = " [PRIMARY KEY]" if col.get("primary_key") else ""
            fk_tag = " [FOREIGN KEY]" if col.get("is_foreign_key") else ""
            schema_text += f"  - {col['name']} ({col['type']}){pk_tag}{fk_tag}\n"

    if relationships:
        schema_text += "\nExplicit Relationships (Foreign Keys):\n"
        for rel in relationships:
            schema_text += (
                f"  - {rel['source_table']}.{rel['source_column']} -> "
                f"{rel['target_table']}.{rel['target_column']}\n"
            )

    return schema_text

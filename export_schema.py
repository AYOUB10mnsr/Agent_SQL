import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "Chinook_Sqlite.sqlite"
OUTPUT_PATH = ROOT / "knowledge" / "schema.json"


def quote_identifier(name):
    return '"' + name.replace('"', '""') + '"'


def main():
    if not DB_PATH.is_file():
        raise FileNotFoundError(DB_PATH)

    connection = sqlite3.connect(
        DB_PATH.as_uri() + "?mode=ro",
        uri=True,
    )

    try:
        tables = connection.execute("""
            SELECT name, sql
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """).fetchall()

        schema = {
            "dialect": "sqlite",
            "tables": {},
        }

        for table_name, create_sql in tables:
            quoted_name = quote_identifier(table_name)

            columns = connection.execute(
                f"PRAGMA table_info({quoted_name})"
            ).fetchall()

            foreign_keys = connection.execute(
                f"PRAGMA foreign_key_list({quoted_name})"
            ).fetchall()

            schema["tables"][table_name] = {
                "create_sql": create_sql,
                "columns": [
                    {
                        "name": column[1],
                        "type": column[2],
                        "not_null_declared": bool(column[3]),
                        "default": column[4],
                        "primary_key_position": column[5],
                    }
                    for column in columns
                ],
                "foreign_keys": [
                    {
                        "constraint_id": key[0],
                        "column_position": key[1],
                        "target_table": key[2],
                        "source_column": key[3],
                        "target_column": key[4],
                    }
                    for key in foreign_keys
                ],
            }

        date_min, date_max = connection.execute("""
            SELECT MIN(InvoiceDate), MAX(InvoiceDate)
            FROM Invoice
        """).fetchone()

        schema["invoice_date_range"] = {
            "min": date_min,
            "max": date_max,
        }

        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(
            json.dumps(schema, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(f"Tables exportées : {len(schema['tables'])}")
        print(f"Période des factures : {date_min} → {date_max}")
        print(f"Schéma enregistré : {OUTPUT_PATH}")

    finally:
        connection.close()


if __name__ == "__main__":
    main()
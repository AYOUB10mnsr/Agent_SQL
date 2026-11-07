import sqlite3
from pathlib import Path

# Chemin relatif à ce script, indépendant du dossier du terminal.
DB_PATH = Path(__file__).resolve().parent / "data" / "Chinook_Sqlite.sqlite"


def quote_identifier(name):
    """Protège un nom de table ou de colonne dans une requête."""
    return '"' + name.replace('"', '""') + '"'


def main():
    if not DB_PATH.is_file():
        raise FileNotFoundError(f"Base introuvable : {DB_PATH}")

    # Lecture seule : échoue si la base n'existe pas.
    connection = sqlite3.connect(
        DB_PATH.as_uri() + "?mode=ro",
        uri=True,
    )

    try:
        tables = connection.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """).fetchall()

        print(f"Nombre de tables : {len(tables)}")

        for (table_name,) in tables:
            table = quote_identifier(table_name)

            count = connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]

            print(f"\n{'=' * 60}")
            print(f"TABLE : {table_name} | {count} lignes")
            print("Colonnes :")

            columns = connection.execute(
                f"PRAGMA table_info({table})"
            ).fetchall()

            for _, name, data_type, not_null, _, primary_key in columns:
                details = []
                if primary_key:
                    details.append(f"clé primaire, position {primary_key}")
                if not_null:
                    details.append("NOT NULL")

                suffix = f" ({', '.join(details)})" if details else ""
                print(f"  - {name}: {data_type}{suffix}")

            relations = connection.execute(
                f"PRAGMA foreign_key_list({table})"
            ).fetchall()

            print("Relations :")
            if not relations:
                print("  Aucune clé étrangère déclarée.")

            for relation in relations:
                target_table = relation[2]
                source_column = relation[3]
                target_column = relation[4]
                print(
                    f"  - {table_name}.{source_column}"
                    f" → {target_table}.{target_column}"
                )

    finally:
        connection.close()


if __name__ == "__main__":
    main()
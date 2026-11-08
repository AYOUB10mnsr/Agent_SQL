import json
import sqlite3
import sys
from pathlib import Path

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "Chinook_Sqlite.sqlite"
SCHEMA_PATH = ROOT / "knowledge" / "schema.json"

# Liste limitée aux fonctions utiles pour notre prototype.
ALLOWED_FUNCTIONS = {
    "sum", "count", "avg", "min", "max",
    "round", "abs",
    "coalesce", "ifnull", "nullif",
    "lower", "upper", "length",
    "substr", "substring", "trim", "ltrim", "rtrim",
    "replace", "instr", "like",
    "date", "datetime", "strftime",
    "julianday", "unixepoch",
}

BLOCKED_NODE_TYPES = {
    "insert", "update", "delete", "merge",
    "create", "drop", "alter", "into",
    "command", "pragma", "attach", "detach",
    "transaction", "commit", "rollback",
    "copy", "grant", "revoke", "execute",
}


class SQLValidationError(ValueError):
    pass


def open_controlled_connection():
    """
    Ouvrir la base en lecture seule et limiter les opérations autorisées.

    Cette politique autorise les tables du schéma de démonstration.
    Elle ne définit pas encore des droits différents par employé.
    """
    if not DB_PATH.is_file():
        raise FileNotFoundError(DB_PATH)

    schema = json.loads(
        SCHEMA_PATH.read_text(encoding="utf-8-sig")
    )

    allowed_columns = {
        table_name.casefold(): {
            column["name"].casefold()
            for column in table_info["columns"]
        }
        for table_name, table_info in schema["tables"].items()
    }

    connection = sqlite3.connect(
        DB_PATH.as_uri() + "?mode=ro",
        uri=True,
    )

    try:
        connection.execute("PRAGMA query_only = ON")

        def authorizer(action, arg1, arg2, database, source):
            if action == sqlite3.SQLITE_SELECT:
                return sqlite3.SQLITE_OK

            if action == sqlite3.SQLITE_READ:
                table = (arg1 or "").casefold()
                column = (arg2 or "").casefold()

                if database not in {None, "main"}:
                    return sqlite3.SQLITE_DENY

                if table not in allowed_columns:
                    return sqlite3.SQLITE_DENY

                # SQLite peut signaler une colonne vide pour COUNT(*).
                if column and column not in allowed_columns[table]:
                    return sqlite3.SQLITE_DENY

                return sqlite3.SQLITE_OK

            if action == sqlite3.SQLITE_FUNCTION:
                function_name = (arg2 or arg1 or "").casefold()

                if function_name in ALLOWED_FUNCTIONS:
                    return sqlite3.SQLITE_OK

                return sqlite3.SQLITE_DENY

            # Tout ce qui n'est pas explicitement permis est refusé.
            return sqlite3.SQLITE_DENY

        connection.set_authorizer(authorizer)
        return connection

    except Exception:
        connection.close()
        raise


def validate_sql(sql, parameters=None):
    if not isinstance(sql, str) or not sql.strip():
        raise SQLValidationError("Requête vide.")

    if len(sql) > 10_000:
        raise SQLValidationError("Requête trop longue pour ce prototype.")

    if parameters is None:
        parameters = {}

    if not isinstance(parameters, dict):
        raise SQLValidationError("Les paramètres doivent être un dictionnaire.")

    if any(not isinstance(name, str) for name in parameters):
        raise SQLValidationError("Les noms de paramètres doivent être des chaînes.")

    try:
        statements = sqlglot.parse(sql, read="sqlite")
    except (ParseError, RecursionError) as error:
        raise SQLValidationError("Structure SQL non reconnue.") from error

    if len(statements) != 1 or statements[0] is None:
        raise SQLValidationError("Une seule instruction SQL est autorisée.")

    tree = statements[0]

    # Première version : SELECT, avec ou sans WITH.
    # Les requêtes UNION à la racine ne sont pas encore prises en charge.
    if not isinstance(tree, exp.Select):
        raise SQLValidationError("Seule une requête SELECT est autorisée.")

    nodes = list(tree.walk())

    if len(nodes) > 1_500:
        raise SQLValidationError("Requête trop complexe pour ce prototype.")

    for node in nodes:
        if node.key in BLOCKED_NODE_TYPES:
            raise SQLValidationError(
                f"Construction SQL interdite : {node.key}."
            )

        if isinstance(node, exp.With) and node.args.get("recursive"):
            raise SQLValidationError("Les CTE récursives sont interdites.")

        if isinstance(node, exp.Table):
            if node.catalog or (
                node.db and node.db.casefold() != "main"
            ):
                raise SQLValidationError(
                    "Accès à une autre base ou à un autre schéma interdit."
                )

        # Autoriser COUNT(*), mais pas SELECT *.
        if isinstance(node, exp.Star):
            if not isinstance(node.parent, exp.Count):
                raise SQLValidationError(
                    "SELECT * est interdit : indique les colonnes utiles."
                )

    expected_parameters = set()

    for placeholder in tree.find_all(exp.Placeholder):
        name = placeholder.this

        if not isinstance(name, str) or not name:
            raise SQLValidationError(
                "Utilise des paramètres nommés comme :date_start."
            )

        expected_parameters.add(name)

    # Refuser les autres formes de variables reconnues par SQLGlot.
    if any(isinstance(node, exp.Parameter) for node in nodes):
        raise SQLValidationError(
            "Seuls les paramètres nommés avec ':' sont pris en charge."
        )

    provided_parameters = set(parameters)

    if expected_parameters != provided_parameters:
        missing = sorted(expected_parameters - provided_parameters)
        extra = sorted(provided_parameters - expected_parameters)

        raise SQLValidationError(
            f"Paramètres manquants : {missing}. "
            f"Paramètres supplémentaires : {extra}."
        )

    warnings = []

    limit = tree.args.get("limit")

    if limit is None:
        warnings.append(
            "Pas de LIMIT global : l'exécuteur devra plafonner "
            "le nombre de lignes renvoyées."
        )
    else:
        value = limit.expression

        if (
            not isinstance(value, exp.Literal)
            or value.is_string
            or not str(value.this).isdigit()
        ):
            raise SQLValidationError(
                "Pour cette version, LIMIT doit être un entier littéral."
            )

        if not 1 <= int(value.this) <= 100:
            raise SQLValidationError("LIMIT doit être compris entre 1 et 100.")

    connection = open_controlled_connection()

    try:
        # Préparer et lire le plan, pas les résultats de la requête.
        connection.execute(
            "EXPLAIN QUERY PLAN " + sql,
            parameters,
        ).fetchall()

    except sqlite3.Error as error:
        raise SQLValidationError(
            f"Préparation SQLite refusée : {error}"
        ) from error

    finally:
        connection.close()

    return {
        "sql": sql,
        "parameters": dict(parameters),
        "warnings": warnings,
    }


def self_test():
    # Ces tests utilisent la base locale en lecture seule.
    # Aucun appel Gemini et aucune modification de la base.
    cases = [
        (
            "Comptage autorisé",
            "SELECT COUNT(*) FROM Invoice",
            {},
            True,
        ),
        (
            "Dates paramétrées autorisées",
            """
            SELECT SUM(Total)
            FROM Invoice
            WHERE InvoiceDate >= :start
              AND InvoiceDate < :end
            """,
            {"start": "2010-01-01", "end": "2011-01-01"},
            True,
        ),
        (
            "CTE de lecture autorisée",
            """
            WITH totals AS (
                SELECT CustomerId, SUM(Total) AS amount
                FROM Invoice
                GROUP BY CustomerId
            )
            SELECT CustomerId, amount FROM totals LIMIT 5
            """,
            {},
            True,
        ),
        (
            "Suppression bloquée",
            "DELETE FROM Invoice",
            {},
            False,
        ),
        (
            "Deux instructions bloquées",
            "SELECT COUNT(*) FROM Invoice; DELETE FROM Invoice",
            {},
            False,
        ),
        (
            "Colonne inexistante bloquée",
            "SELECT UnknownColumn FROM Invoice LIMIT 5",
            {},
            False,
        ),
        (
            "Paramètre manquant bloqué",
            "SELECT Total FROM Invoice WHERE CustomerId = :id LIMIT 5",
            {},
            False,
        ),
        (
            "Fonction dangereuse bloquée",
            "SELECT load_extension(:path)",
            {"path": "example"},
            False,
        ),
        (
            "Table système bloquée",
            "SELECT name FROM sqlite_master LIMIT 5",
            {},
            False,
        ),
        (
            "Lecture globale bloquée",
            "SELECT * FROM Customer LIMIT 5",
            {},
            False,
        ),
        (
            "Limite excessive bloquée",
            "SELECT InvoiceId FROM Invoice LIMIT 1000",
            {},
            False,
        ),
    ]

    failures = 0

    for name, sql, parameters, expected in cases:
        try:
            validate_sql(sql, parameters)
            accepted = True
        except SQLValidationError:
            accepted = False

        if accepted == expected:
            print(f"OK : {name}")
        else:
            failures += 1
            print(f"ÉCHEC : {name}")

    print(f"\nBilan : {len(cases) - failures}/{len(cases)} tests réussis.")

    if failures:
        raise SystemExit(1)


def main():
    # Importer ici permet de tester le validateur sans appel au modèle.
    from generate_sql import generate_sql

    question = input("Ta question : ").strip()
    if not question:
        return

    proposal = generate_sql(question)

    if proposal.status != "ready":
        print(
            proposal.clarification_question
            or proposal.explanation
        )
        return

    parameters = {
        item.name: item.value
        for item in proposal.parameters
    }

    try:
        result = validate_sql(proposal.sql, parameters)

    except SQLValidationError as error:
        print(f"\nVALIDATION REFUSÉE : {error}")
        return

    print("\nCONTRÔLES TECHNIQUES RÉUSSIS — SQL NON EXÉCUTÉ")
    print("\nSQL :")
    print(result["sql"])

    print("\nParamètres :")
    print(json.dumps(result["parameters"], ensure_ascii=False, indent=2))

    for warning in result["warnings"]:
        print(f"\nAttention : {warning}")

    print("\nLa justesse métier du calcul reste à vérifier.")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        main()
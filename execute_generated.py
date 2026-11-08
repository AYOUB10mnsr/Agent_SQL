import json
import sqlite3
import time

from date_guard import check_sql_period, PeriodValidationError
from validate_sql import (
    SQLValidationError,
    open_controlled_connection,
    validate_sql,
)


class SQLExecutionError(RuntimeError):
    pass


def execute_generated_sql(sql, parameters=None):
    # 1. Refaire la validation technique avant chaque exécution.
    validated = validate_sql(sql, parameters)

    # 2. Contrôler la période réellement présente dans le SQL.
    try:
        period = check_sql_period(
            validated["sql"],
            validated["parameters"],
        )

    except PeriodValidationError as error:
        raise SQLExecutionError(
            f"Contrôle de période : {error}"
        ) from error

    if period["status"] == "outside":
        raise SQLExecutionError(period["message"])

    if period["message"]:
        validated["warnings"].append(period["message"])

    # 3. Ouvrir une connexion en lecture seule,
    # avec les autorisations définies dans validate_sql.py.
    connection = open_controlled_connection()

    started = time.perf_counter()
    timeout_seconds = 3.0
    max_rows = 100
    deadline = started + timeout_seconds
    timed_out = False

    def check_deadline():
        nonlocal timed_out

        if time.perf_counter() >= deadline:
            timed_out = True
            return 1

        return 0

    # Contrôle périodique pendant le traitement SQLite.
    # Ce mécanisme n'est pas une garantie de durée exacte.
    connection.set_progress_handler(check_deadline, 1000)

    try:
        # 4. Exécuter uniquement la requête validée.
        cursor = connection.execute(
            validated["sql"],
            validated["parameters"],
        )

        columns = [
            description[0]
            for description in cursor.description
        ]

        # Lire une ligne supplémentaire pour détecter
        # si l'affichage doit être tronqué.
        fetched_rows = cursor.fetchmany(max_rows + 1)

        truncated = len(fetched_rows) > max_rows
        rows = [
            list(row)
            for row in fetched_rows[:max_rows]
        ]

        warnings = list(validated["warnings"])

        if truncated:
            warnings.append(
                "Affichage limité aux 100 premières lignes. "
                "Le résultat présenté est incomplet."
            )

        return {
            "sql": validated["sql"],
            "parameters": validated["parameters"],
            "columns": columns,
            "rows": rows,
            "rows_returned": len(rows),
            "truncated": truncated,
            "seconds": round(time.perf_counter() - started, 3),
            "warnings": warnings,
            "period_status": period["status"],
        }

    except sqlite3.Error as error:
        if timed_out:
            raise SQLExecutionError(
                "Calcul interrompu après dépassement "
                "du délai configuré de 3 secondes."
            ) from error

        raise SQLExecutionError(
            f"Exécution SQLite refusée : {error}"
        ) from error

    finally:
        connection.set_progress_handler(None, 0)
        connection.close()


def main():
    from generate_sql import generate_sql

    print("Génération → validation → contrôle des dates → exécution")
    question = input("\nTa question : ").strip()

    if not question:
        print("Saisis une question non vide.")
        return

    proposal = generate_sql(question)

    if proposal.status != "ready":
        print(
            "\nAssistant :",
            proposal.clarification_question
            or proposal.explanation,
        )
        return

    parameters = {
        item.name: item.value
        for item in proposal.parameters
    }

    print("\nCalcul proposé :")
    print(proposal.explanation)

    if proposal.assumptions:
        print("\nHypothèses et limites :")
        for assumption in proposal.assumptions:
            print(f"- {assumption}")

    try:
        result = execute_generated_sql(
            proposal.sql,
            parameters,
        )

    except SQLValidationError as error:
        print(f"\nVALIDATION REFUSÉE : {error}")
        return

    except SQLExecutionError as error:
        print(f"\nCALCUL BLOQUÉ OU INTERROMPU : {error}")
        return

    print("\nSQL exécuté :")
    print(result["sql"])

    print("\nParamètres :")
    print(
        json.dumps(
            result["parameters"],
            ensure_ascii=False,
            indent=2,
        )
    )

    print("\nRésultats :")
    print(
        json.dumps(
            {
                "columns": result["columns"],
                "rows": result["rows"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    print(f"\nLignes retournées : {result['rows_returned']}")
    print(f"Temps SQLite : {result['seconds']} secondes")

    for warning in result["warnings"]:
        print(f"\nAttention : {warning}")

    if not result["rows"]:
        print("\nAucune ligne retournée pour cette sélection.")

    elif any(
        value is None
        for row in result["rows"]
        for value in row
    ):
        print(
            "\nCertaines valeurs sont NULL. "
            "Une valeur NULL ne doit pas être interprétée "
            "automatiquement comme zéro."
        )

    print(
        "\nLes contrôles techniques ont été appliqués. "
        "La justesse métier reste à évaluer."
    )


if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        print("\nOpération interrompue.")

    except Exception as error:
        # Afficher uniquement le type pour ne pas exposer de secrets.
        print(f"\nErreur technique : {type(error).__name__}.")
import json
import sqlite3
from pathlib import Path

from interpret_question import Interpretation, interpret_question

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "Chinook_Sqlite.sqlite"


def build_query(request: Interpretation):
    if request.status != "ready":
        raise ValueError("La demande n'est pas prête pour l'exécution.")

    # Expressions définies par le développeur.
    # Aucune expression SQL fournie par le modèle n'est exécutée.
    metrics = {
        "nombre_factures": (
            "COUNT(DISTINCT i.InvoiceId)",
            "factures",
            False,
        ),
        "montant_facture": (
            "SUM(CAST(ROUND(i.Total * 100) AS INTEGER))",
            "centiemes_unite_monetaire",
            False,
        ),
        "quantite_vendue": (
            "SUM(il.Quantity)",
            "unites",
            True,
        ),
        "montant_lignes": (
            "SUM(CAST(ROUND(il.UnitPrice * 100) AS INTEGER) * il.Quantity)",
            "centiemes_unite_monetaire",
            True,
        ),
        "panier_moyen": (
            "AVG(CAST(ROUND(i.Total * 100) AS INTEGER))",
            "centiemes_unite_monetaire",
            False,
        ),
    }

    dimensions = {
        "none": None,
        "month": "strftime('%Y-%m', i.InvoiceDate)",
        "billing_country": "i.BillingCountry",
    }

    expression, unit, needs_lines = metrics[request.metric]
    dimension = dimensions[request.group_by]

    select = f"{expression} AS valeur"
    if dimension:
        select = f"{dimension} AS groupe, {select}"

    sql = f"SELECT {select}\nFROM Invoice AS i"

    if needs_lines:
        sql += "\nJOIN InvoiceLine AS il ON il.InvoiceId = i.InvoiceId"

    conditions = []
    parameters = {}

    if request.period == "range":
        conditions.extend([
            "i.InvoiceDate >= :date_start",
            "i.InvoiceDate < :date_end",
        ])
        parameters["date_start"] = request.date_start.isoformat()
        parameters["date_end"] = request.date_end_exclusive.isoformat()

    if request.billing_country is not None:
        conditions.append("i.BillingCountry = :country")
        parameters["country"] = request.billing_country

    if conditions:
        sql += "\nWHERE " + " AND ".join(conditions)

    if dimension:
        sql += f"\nGROUP BY {dimension}\nORDER BY groupe"

    return sql, parameters, unit


def execute_query(sql, parameters):
    if not DB_PATH.is_file():
        raise FileNotFoundError(DB_PATH)

    connection = sqlite3.connect(
        DB_PATH.as_uri() + "?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row

    try:
        connection.execute("PRAGMA query_only = ON")

        # Vérifier le pays proposé par le modèle avant le calcul.
        if "country" in parameters:
            found = connection.execute(
                "SELECT 1 FROM Invoice WHERE BillingCountry = ? LIMIT 1",
                (parameters["country"],),
            ).fetchone()

            if found is None:
                raise ValueError(
                    "Pays de facturation non trouvé : "
                    f"{parameters['country']}. Vérifie la valeur du filtre."
                )

        return [
            dict(row)
            for row in connection.execute(sql, parameters).fetchall()
        ]

    finally:
        connection.close()


def main():
    question = input("Ta question : ").strip()
    if not question:
        raise SystemExit("Saisis une question non vide.")

    request = interpret_question(question)

    if request.status == "clarification":
        print("\nPrécision nécessaire :")
        print(request.clarification_question)
        return

    if request.status == "unsupported":
        print("\nDemande non prise en charge :")
        print(request.explanation)
        return

    sql, parameters, unit = build_query(request)

    print("\nInterprétation proposée :")
    print(request.explanation)

    print("\nSQL exécuté :")
    print(sql)

    print("\nParamètres :")
    print(json.dumps(parameters, ensure_ascii=False, indent=2))

    results = execute_query(sql, parameters)

    print(f"\nRésultats — unité : {unit}")
    print(json.dumps(results, ensure_ascii=False, indent=2))

    if not results or all(row["valeur"] is None for row in results):
        print("Aucune valeur calculable pour cette sélection.")

    print("\nLa justesse de l'interprétation reste à vérifier.")


if __name__ == "__main__":
    main()
import hashlib
import json
import sqlite3
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "Chinook_Sqlite.sqlite"
OUTPUT_PATH = ROOT / "evaluation" / "reference_cases.json"


def to_cents(value):
    amount = Decimal(str(value)) * 100
    if amount != amount.to_integral_value():
        raise ValueError(f"Montant avec plus de deux décimales : {value}")
    return int(amount)


def main():
    if not DB_PATH.is_file():
        raise FileNotFoundError(DB_PATH)

    connection = sqlite3.connect(
        DB_PATH.as_uri() + "?mode=ro",
        uri=True,
    )

    try:
        # Données brutes pour la vérification indépendante en Python.
        invoices = connection.execute("""
            SELECT InvoiceId, InvoiceDate, Total
            FROM Invoice
        """).fetchall()

        lines = connection.execute("""
            SELECT InvoiceId, UnitPrice, Quantity
            FROM InvoiceLine
        """).fetchall()

        if not invoices:
            raise ValueError("La table Invoice est vide.")

        monthly_totals = defaultdict(int)
        invoice_totals = {}
        line_totals = defaultdict(int)

        for invoice_id, invoice_date, total in invoices:
            cents = to_cents(total)
            invoice_totals[invoice_id] = cents
            monthly_totals[invoice_date[:7]] += cents

        for invoice_id, unit_price, quantity in lines:
            line_totals[invoice_id] += to_cents(unit_price) * quantity

        # Contrôle : chaque facture correspond-elle à ses lignes ?
        mismatches = [
            invoice_id
            for invoice_id in set(invoice_totals) | set(line_totals)
            if invoice_totals.get(invoice_id) != line_totals.get(invoice_id, 0)
        ]

        if mismatches:
            raise AssertionError(
                f"Factures incohérentes avec leurs lignes : {mismatches}"
            )

        cases = [
            {
                "id": "nombre_factures",
                "question": "Combien de factures contient la base ?",
                "unit": "factures",
                "sql": "SELECT COUNT(*) FROM Invoice",
                "python_result": [[len(invoices)]],
            },
            {
                "id": "montant_total",
                "question": "Quel est le montant total facturé sur toute la période ?",
                "unit": "centiemes_unite_monetaire",
                "sql": """
                    SELECT SUM(CAST(ROUND(Total * 100) AS INTEGER))
                    FROM Invoice
                """,
                "python_result": [[sum(invoice_totals.values())]],
            },
            {
                "id": "quantite_totale",
                "question": "Combien d'unités ont été vendues sur toute la période ?",
                "unit": "unites",
                "sql": "SELECT SUM(Quantity) FROM InvoiceLine",
                "python_result": [[sum(row[2] for row in lines)]],
            },
            {
                "id": "ventes_mensuelles",
                "question": "Quel est le montant facturé par mois sur toute la période ?",
                "unit": "centiemes_unite_monetaire",
                "sql": """
                    SELECT
                        strftime('%Y-%m', InvoiceDate) AS mois,
                        SUM(CAST(ROUND(Total * 100) AS INTEGER))
                    FROM Invoice
                    GROUP BY strftime('%Y-%m', InvoiceDate)
                    ORDER BY mois
                """,
                "python_result": [
                    [month, total]
                    for month, total in sorted(monthly_totals.items())
                ],
            },
        ]

        for case in cases:
            sql_result = [
                list(row)
                for row in connection.execute(case["sql"]).fetchall()
            ]

            if sql_result != case["python_result"]:
                raise AssertionError(
                    f"Désaccord SQL/Python pour {case['id']}\n"
                    f"SQL : {sql_result}\n"
                    f"Python : {case['python_result']}"
                )

            case["expected_result"] = sql_result
            del case["python_result"]
            case["validation"] = "accord_sql_python"
            print(f"OK : {case['id']}")

        dates = [row[1] for row in invoices]

        report = {
            "database_file": DB_PATH.name,
            "database_sha256": hashlib.sha256(DB_PATH.read_bytes()).hexdigest(),
            "date_min": min(dates),
            "date_max": max(dates),
            "invoice_line_consistency": "passed",
            "cases": cases,
        }

        OUTPUT_PATH.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(f"\nPériode : {min(dates)} → {max(dates)}")
        print(f"Montant total : {sum(invoice_totals.values()) / 100:.2f}")
        print("Cohérence factures / lignes : OK")
        print(f"Références enregistrées : {OUTPUT_PATH}")

    finally:
        connection.close()


if __name__ == "__main__":
    main()
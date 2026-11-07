import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from interpret_question import Interpretation
from run_question import build_query, execute_query

DB_PATH = ROOT / "data" / "Chinook_Sqlite.sqlite"
REFERENCE_PATH = ROOT / "evaluation" / "reference_cases.json"


def main():
    reference = json.loads(
        REFERENCE_PATH.read_text(encoding="utf-8-sig")
    )

    current_hash = hashlib.sha256(DB_PATH.read_bytes()).hexdigest()

    if current_hash != reference["database_sha256"]:
        raise ValueError(
            "La base a changé depuis la création des références. "
            "Vérifie les données avant de poursuivre."
        )

    # Interprétations fixées pour tester les calculs sans appeler le modèle.
    scenarios = {
        "nombre_factures": {
            "metric": "nombre_factures",
            "group_by": "none",
        },
        "montant_total": {
            "metric": "montant_facture",
            "group_by": "none",
        },
        "quantite_totale": {
            "metric": "quantite_vendue",
            "group_by": "none",
        },
        "ventes_mensuelles": {
            "metric": "montant_facture",
            "group_by": "month",
        },
    }

    failures = 0

    for case in reference["cases"]:
        scenario = scenarios[case["id"]]

        request = Interpretation(
            status="ready",
            period="all",
            metric=scenario["metric"],
            group_by=scenario["group_by"],
            explanation="Test du calcul à partir d'une référence.",
        )

        sql, parameters, unit = build_query(request)
        rows = execute_query(sql, parameters)

        # Même format que les résultats de référence :
        # [[valeur]] ou [[mois, valeur], ...].
        if request.group_by == "none":
            actual = [[row["valeur"]] for row in rows]
        else:
            actual = [[row["groupe"], row["valeur"]] for row in rows]

        expected = case["expected_result"]

        if actual == expected and unit == case["unit"]:
            print(f"OK : {case['id']}")
        else:
            failures += 1
            print(f"ÉCHEC : {case['id']}")
            print(f"  Attendu : {expected}")
            print(f"  Obtenu  : {actual}")
            print(f"  Unité attendue : {case['unit']}")
            print(f"  Unité obtenue  : {unit}")

    total = len(reference["cases"])
    print(f"\nBilan : {total - failures}/{total} tests réussis.")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
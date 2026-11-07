import json
import sqlite3
from decimal import Decimal

from google.genai import errors

from interpret_question import interpret_question
from run_question import build_query, execute_query


LABELS = {
    "nombre_factures": "Nombre de factures",
    "montant_facture": "Montant facturé",
    "quantite_vendue": "Quantité vendue",
    "montant_lignes": "Montant des lignes facturées",
    "panier_moyen": "Montant moyen par facture",
}


def format_value(value, unit):
    if value is None:
        return "Aucune valeur calculable"

    if unit == "centiemes_unite_monetaire":
        amount = Decimal(str(value)) / Decimal("100")
        return f"{amount:.2f} unités monétaires"

    return f"{value} {unit}"


def format_results(request, rows, unit):
    output = [LABELS[request.metric]]

    if request.period == "range":
        output.append(
            f"Période : du {request.date_start} inclus "
            f"au {request.date_end_exclusive} exclu."
        )
    else:
        output.append("Période : toute la période disponible.")

    if request.billing_country:
        output.append(
            f"Pays de facturation : {request.billing_country}"
        )

    if not rows:
        output.append("Aucun résultat pour cette sélection.")
    else:
        for row in rows:
            value = format_value(row["valeur"], unit)

            if "groupe" in row:
                group = row["groupe"]
                if group is None:
                    group = "Non renseigné"
                output.append(f"- {group} : {value}")
            else:
                output.append(f"Résultat : {value}")

    if (
        request.metric == "nombre_factures"
        and rows
        and all(row["valeur"] == 0 for row in rows)
    ):
        output.append(
            "Aucune facture trouvée. Cela ne prouve pas que "
            "la base couvre complètement la période demandée."
        )

    return "\n".join(output)


def main():
    history = []

    print("Assistant SQL — Chinook")
    print("Commandes : /reset pour effacer le contexte, /quit pour quitter.")

    while True:
        question = input("\nToi : ").strip()

        if question.lower() == "/quit":
            print("Conversation terminée.")
            break

        if question.lower() == "/reset":
            history.clear()
            print("Assistant : contexte effacé.")
            continue

        if not question:
            continue

        try:
            request = interpret_question(question, history=history)

        except errors.APIError as error:
            print(
                f"Assistant : erreur API, code {error.code}. "
                "Réessaie dans un instant."
            )
            continue

        except ValueError:
            print(
                "Assistant : l'interprétation reçue est invalide. "
                "Réessaie ou reformule la question."
            )
            continue

        history.append({"role": "user", "text": question})

        if request.status == "clarification":
            answer = request.clarification_question

        elif request.status == "unsupported":
            answer = request.explanation

        else:
            try:
                sql, parameters, unit = build_query(request)
                rows = execute_query(sql, parameters)

                answer = format_results(request, rows, unit)

                print("\nSQL :")
                print(sql)
                print("Paramètres :", json.dumps(parameters, ensure_ascii=False))

            except (ValueError, sqlite3.Error):
                answer = (
                    "Le calcul n'a pas pu être effectué. "
                    "Vérifie les filtres demandés, notamment le pays."
                )

        print(f"\nAssistant : {answer}")

        # Conserver l'interprétation complète permet de comprendre
        # une question de suivi comme « Et pour mai ? ».
        memory = (
            "Interprétation de la demande précédente :\n"
            + request.model_dump_json()
            + "\nRéponse affichée :\n"
            + answer
        )

        history.append({"role": "model", "text": memory})


if __name__ == "__main__":
    main()
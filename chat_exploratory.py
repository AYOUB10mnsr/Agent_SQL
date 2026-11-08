import json
import time

from google.genai import errors

from execute_generated import (
    SQLExecutionError,
    execute_generated_sql,
)
from generate_sql import generate_sql
from validate_sql import SQLValidationError


def show_pending_help():
    print(
        "Question conservée.\n"
        "/retry : réessayer\n"
        "/cancel : abandonner la question\n"
        "/reset : effacer la conversation"
    )


def main():
    history = []
    pending_question = None

    print("Assistant SQL — parcours exploratoire")
    print("Commandes : /retry, /cancel, /reset, /quit")

    while True:
        try:
            message = input("\nToi : ").strip()

        except (EOFError, KeyboardInterrupt):
            print("\nConversation terminée.")
            break

        if not message:
            continue

        command = message.lower()

        if command == "/quit":
            print("Conversation terminée.")
            break

        if command == "/reset":
            history.clear()
            pending_question = None
            print("Assistant : conversation effacée.")
            continue

        if command == "/cancel":
            pending_question = None
            print(
                "Assistant : question abandonnée. "
                "Les échanges terminés sont conservés."
            )
            continue

        if command == "/retry":
            if pending_question is None:
                print("Aucune question à relancer.")
                continue

            print(f"Reprise : {pending_question}")

        elif message.startswith("/"):
            print("Commande inconnue.")
            continue

        elif pending_question is not None:
            print(f"Question en attente : {pending_question}")
            show_pending_help()
            continue

        else:
            pending_question = message

        started = time.perf_counter()

        try:
            proposal = generate_sql(
                pending_question,
                history=history,
            )

            if proposal.status == "clarification":
                answer = proposal.clarification_question

            elif proposal.status == "unsupported":
                answer = proposal.explanation

            else:
                parameters = {
                    item.name: item.value
                    for item in proposal.parameters
                }

                result = execute_generated_sql(
                    proposal.sql,
                    parameters,
                )

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

                sections = [
                    "Calcul : " + proposal.explanation
                ]

                if proposal.assumptions:
                    sections.append(
                        "Hypothèses et limites :\n"
                        + "\n".join(
                            f"- {item}"
                            for item in proposal.assumptions
                        )
                    )

                sections.append(
                    "Résultats :\n"
                    + json.dumps(
                        {
                            "columns": result["columns"],
                            "rows": result["rows"],
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )

                if not result["rows"]:
                    sections.append(
                        "Aucune ligne retournée. "
                        "Cela ne prouve pas que les données "
                        "couvrent la période demandée."
                    )

                if result["warnings"]:
                    sections.append(
                        "Avertissements :\n"
                        + "\n".join(
                            f"- {item}"
                            for item in result["warnings"]
                        )
                    )

                answer = "\n\n".join(sections)

        except errors.APIError as error:
            print(f"Assistant : échec API, code {error.code}.")
            show_pending_help()
            continue

        except SQLValidationError as error:
            print(f"Assistant : SQL refusé par le validateur : {error}")
            show_pending_help()
            continue

        except SQLExecutionError as error:
            print(f"Assistant : {error}")
            show_pending_help()
            continue

        except KeyboardInterrupt:
            print("\nTraitement interrompu.")
            show_pending_help()
            continue

        except Exception as error:
            print(
                "Assistant : erreur technique "
                f"({type(error).__name__})."
            )
            show_pending_help()
            continue

        # Mémoriser uniquement les échanges terminés.
        history.extend([
            {
                "role": "user",
                "text": pending_question,
            },
            {
                "role": "model",
                "text": (
                    "Proposition précédente :\n"
                    + proposal.model_dump_json()
                    + "\nRéponse affichée :\n"
                    + answer
                ),
            },
        ])

        pending_question = None

        print(f"\nAssistant : {answer}")
        print(
            "\nTemps de réponse : "
            f"{time.perf_counter() - started:.1f} secondes"
        )


if __name__ == "__main__":
    main()
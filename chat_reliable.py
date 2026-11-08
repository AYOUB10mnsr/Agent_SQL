import json
import sqlite3
import time
from datetime import date, timedelta

from google.genai import errors

from chat_sql import format_results
from interpret_question import interpret_question, read_json
from run_question import build_query, execute_query


def show_pending_help():
    print(
        "La question reste en attente.\n"
        "/retry : réessayer la même question\n"
        "/cancel : abandonner cette question\n"
        "/reset : effacer toute la conversation"
    )


def check_period(request):
    """
    Retourne :
    - blocked : période entièrement hors des dates disponibles ;
    - warning : période partiellement hors des dates disponibles ;
    - None : aucun dépassement détecté.

    Les dates extrêmes ne garantissent pas la complétude des données.
    """
    if request.period != "range":
        return None, None

    schema = read_json("knowledge/schema.json")
    coverage = schema["invoice_date_range"]

    if not coverage["min"] or not coverage["max"]:
        raise ValueError(
            "Les dates disponibles sont absentes du schéma."
        )

    first_date = date.fromisoformat(coverage["min"][:10])
    last_date = date.fromisoformat(coverage["max"][:10])
    end_exclusive = last_date + timedelta(days=1)

    available = (
        "Les dates des factures présentes vont "
        f"du {first_date:%d/%m/%Y} "
        f"au {last_date:%d/%m/%Y}."
    )

    if (
        request.date_end_exclusive <= first_date
        or request.date_start >= end_exclusive
    ):
        return (
            "blocked",
            "La période demandée est entièrement extérieure "
            "aux dates disponibles.\n"
            + available
            + "\nAucun calcul n'a été effectué. "
            "Cela ne signifie pas que les ventes étaient nulles.",
        )

    if (
        request.date_start < first_date
        or request.date_end_exclusive > end_exclusive
    ):
        return (
            "warning",
            "Attention : la période demandée dépasse "
            "les dates disponibles.\n"
            + available
            + "\nLe résultat porte uniquement sur les données présentes.",
        )

    return None, None


def main():
    history = []
    pending_question = None

    print("Assistant SQL — Chinook")
    print(
        "Commandes : /retry, /cancel, /reset, /quit\n"
        "La mémoire est conservée uniquement pendant cette session."
    )

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
            if pending_question is None:
                print("Assistant : aucune question en attente.")
            else:
                pending_question = None
                print(
                    "Assistant : question abandonnée. "
                    "Les échanges précédents sont conservés."
                )
            continue

        if command == "/retry":
            if pending_question is None:
                print("Assistant : aucune question à relancer.")
                continue

            print(f"Reprise : {pending_question}")

        elif message.startswith("/"):
            print(
                "Commande inconnue. Utilise exactement "
                "/retry, /cancel, /reset ou /quit."
            )
            continue

        elif pending_question is not None:
            print(
                "Assistant : une question précédente "
                "n'a pas abouti :\n"
                f"« {pending_question} »"
            )
            show_pending_help()
            continue

        else:
            pending_question = message

        started = time.perf_counter()

        # Interprétation de la question avec le contexte précédent.
        try:
            request = interpret_question(
                pending_question,
                history=history,
            )

        except errors.APIError as error:
            print(f"\nAssistant : échec API, code {error.code}.")
            show_pending_help()
            continue

        except FileNotFoundError:
            print(
                "\nAssistant : un fichier de contexte est introuvable. "
                "Vérifie knowledge/schema.json et "
                "knowledge/business_context.json."
            )
            show_pending_help()
            continue

        except ValueError:
            print(
                "\nAssistant : configuration ou interprétation invalide. "
                "Vérifie les fichiers du projet, ou utilise /cancel "
                "pour reformuler."
            )
            show_pending_help()
            continue

        except KeyboardInterrupt:
            print("\nAssistant : attente interrompue.")
            show_pending_help()
            continue

        except Exception as error:
            # Ne pas afficher le détail de l'exception :
            # il pourrait contenir des informations sensibles.
            print(
                "\nAssistant : erreur technique "
                f"({type(error).__name__})."
            )
            show_pending_help()
            continue

        if request.status == "clarification":
            answer = request.clarification_question

        elif request.status == "unsupported":
            answer = request.explanation

        else:
            try:
                period_status, period_message = check_period(request)

                if period_status == "blocked":
                    # Ne pas construire ni exécuter de SQL.
                    answer = period_message

                else:
                    sql, parameters, unit = build_query(request)
                    rows = execute_query(sql, parameters)

                    answer = format_results(request, rows, unit)

                    if period_status == "warning":
                        answer = period_message + "\n\n" + answer

                    print("\nSQL :")
                    print(sql)
                    print(
                        "Paramètres :",
                        json.dumps(
                            parameters,
                            ensure_ascii=False,
                        ),
                    )

            except FileNotFoundError:
                print(
                    "\nAssistant : base ou fichier de schéma introuvable. "
                    "Vérifie data/Chinook_Sqlite.sqlite "
                    "et knowledge/schema.json."
                )
                show_pending_help()
                continue

            except ValueError as error:
                if isinstance(error, json.JSONDecodeError):
                    print(
                        "\nAssistant : le fichier de schéma "
                        "contient un JSON invalide."
                    )
                else:
                    print(
                        "\nAssistant : calcul impossible. "
                        "Vérifie la période et le pays demandé."
                    )

                show_pending_help()
                continue

            except sqlite3.Error:
                print(
                    "\nAssistant : la requête SQLite "
                    "n'a pas pu être exécutée."
                )
                show_pending_help()
                continue

            except (KeyError, TypeError, OverflowError):
                print(
                    "\nAssistant : la structure ou les dates du schéma "
                    "sont invalides. Régénère knowledge/schema.json "
                    "avec export_schema.py."
                )
                show_pending_help()
                continue

        # Enregistrer une seule fois l'échange terminé.
        # Une demande hors période est également mémorisée
        # avec le message indiquant qu'aucun calcul n'a eu lieu.
        history.extend([
            {
                "role": "user",
                "text": pending_question,
            },
            {
                "role": "model",
                "text": (
                    "Interprétation précédente :\n"
                    + request.model_dump_json()
                    + "\nRéponse affichée :\n"
                    + answer
                ),
            },
        ])

        pending_question = None

        elapsed = time.perf_counter() - started

        print(f"\nAssistant : {answer}")
        print(f"\nTemps de réponse : {elapsed:.1f} secondes")


if __name__ == "__main__":
    main()
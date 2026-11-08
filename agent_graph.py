import json
import time
from typing import TypedDict
from uuid import uuid4

from google.genai import errors
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from chat_reliable import check_period
from chat_sql import format_results
from interpret_question import Interpretation, interpret_question
from run_question import build_query, execute_query


class AgentState(TypedDict, total=False):
    question: str
    history: list[dict[str, str]]
    request: dict | None
    period_status: str | None
    period_message: str | None
    sql: str | None
    parameters: dict
    unit: str | None
    rows: list[dict]
    answer: str | None
    error: str | None


def failure(error):
    """Retourner une erreur sans exposer de secrets."""
    if isinstance(error, errors.APIError):
        return {"error": f"Échec API, code {error.code}."}

    return {
        "error": (
            f"Échec technique ({type(error).__name__}). "
            "Vérifie la configuration et les fichiers du projet."
        )
    }


def interpret_node(state):
    print("\n[1] Interprétation", flush=True)

    # Effacer les données du calcul précédent.
    update = {
        "request": None,
        "period_status": None,
        "period_message": None,
        "sql": None,
        "parameters": {},
        "unit": None,
        "rows": [],
        "answer": None,
        "error": None,
    }

    try:
        request = interpret_question(
            state["question"],
            history=state.get("history", []),
        )
        update["request"] = request.model_dump(mode="json")

    except Exception as error:
        update.update(failure(error))

    return update


def period_node(state):
    print("[2] Vérification de la période", flush=True)

    try:
        request = Interpretation.model_validate(state["request"])
        status, message = check_period(request)

        return {
            "period_status": status,
            "period_message": message,
        }

    except Exception as error:
        return failure(error)


def build_node(state):
    print("[3] Construction SQL", flush=True)

    try:
        request = Interpretation.model_validate(state["request"])
        sql, parameters, unit = build_query(request)

        return {
            "sql": sql,
            "parameters": parameters,
            "unit": unit,
        }

    except Exception as error:
        return failure(error)


def execute_node(state):
    print("[4] Exécution SQLite", flush=True)

    try:
        rows = execute_query(
            state["sql"],
            state["parameters"],
        )
        return {"rows": rows}

    except Exception as error:
        return failure(error)


def respond_node(state):
    print("[5] Préparation de la réponse", flush=True)

    request = Interpretation.model_validate(state["request"])

    if request.status == "clarification":
        answer = request.clarification_question

    elif request.status == "unsupported":
        answer = request.explanation

    elif state["period_status"] == "blocked":
        answer = state["period_message"]

    else:
        answer = format_results(
            request,
            state["rows"],
            state["unit"],
        )

        if state["period_status"] == "warning":
            answer = state["period_message"] + "\n\n" + answer

    # L'historique est remplacé par sa version complétée.
    # Aucun échange échoué n'y est ajouté.
    history = state.get("history", []) + [
        {
            "role": "user",
            "text": state["question"],
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
    ]

    return {"answer": answer, "history": history}


def after_interpret(state):
    if state.get("error"):
        return END

    if state["request"]["status"] == "ready":
        return "check_period"

    return "respond"


def after_period(state):
    if state.get("error"):
        return END

    if state["period_status"] == "blocked":
        return "respond"

    return "build_sql"


def after_build(state):
    return END if state.get("error") else "execute_sql"


def after_execute(state):
    return END if state.get("error") else "respond"


def create_graph():
    builder = StateGraph(AgentState)

    builder.add_node("interpret", interpret_node)
    builder.add_node("check_period", period_node)
    builder.add_node("build_sql", build_node)
    builder.add_node("execute_sql", execute_node)
    builder.add_node("respond", respond_node)

    builder.add_edge(START, "interpret")

    builder.add_conditional_edges(
        "interpret",
        after_interpret,
        ["check_period", "respond", END],
    )
    builder.add_conditional_edges(
        "check_period",
        after_period,
        ["build_sql", "respond", END],
    )
    builder.add_conditional_edges(
        "build_sql",
        after_build,
        ["execute_sql", END],
    )
    builder.add_conditional_edges(
        "execute_sql",
        after_execute,
        ["respond", END],
    )

    builder.add_edge("respond", END)

    return builder.compile(checkpointer=InMemorySaver())


def new_conversation_config():
    return {"configurable": {"thread_id": str(uuid4())}}


def main():
    graph = create_graph()
    config = new_conversation_config()
    pending_question = None

    print("Assistant SQL — LangGraph")
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
            # Nouvelle mémoire et nouvel identifiant.
            graph = create_graph()
            config = new_conversation_config()
            pending_question = None
            print("Assistant : conversation effacée.")
            continue

        if command == "/cancel":
            pending_question = None
            print(
                "Assistant : question en attente abandonnée. "
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
            print("Utilise /retry, /cancel ou /reset.")
            continue

        else:
            pending_question = message

        started = time.perf_counter()

        try:
            result = graph.invoke(
                {"question": pending_question},
                config=config,
            )

        except KeyboardInterrupt:
            print("\nAttente interrompue. Utilise /retry ou /cancel.")
            continue

        except Exception as error:
            print(failure(error)["error"])
            print("Question conservée : utilise /retry ou /cancel.")
            continue

        elapsed = time.perf_counter() - started

        if result.get("error"):
            print(f"\nAssistant : {result['error']}")
            print("Question conservée : utilise /retry ou /cancel.")

        else:
            if result.get("sql"):
                print("\nSQL :")
                print(result["sql"])
                print(
                    "Paramètres :",
                    json.dumps(
                        result["parameters"],
                        ensure_ascii=False,
                    ),
                )

            print(f"\nAssistant : {result['answer']}")
            pending_question = None

        print(f"\nTemps de réponse : {elapsed:.1f} secondes")


if __name__ == "__main__":
    main()
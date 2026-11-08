import json
import time

import pandas as pd
import streamlit as st
from google.genai import errors

from execute_generated import SQLExecutionError, execute_generated_sql
from generate_sql import generate_sql
from interpret_question import read_json
from validate_sql import SQLValidationError


st.set_page_config(
    page_title="Agent SQL — Chinook",
    page_icon="💬",
    layout="wide",
)


def initialize_session():
    defaults = {
        "sql_messages": [],
        "sql_history": [],
        "sql_pending": None,
        "sql_error": None,
        "sql_run_requested": False,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_conversation():
    st.session_state.sql_messages = []
    st.session_state.sql_history = []
    st.session_state.sql_pending = None
    st.session_state.sql_error = None
    st.session_state.sql_run_requested = False


def render_message(message):
    with st.chat_message(message["role"]):
        if message["role"] == "user":
            st.write(message["text"])
            return

        st.write(message["text"])

        for assumption in message.get("assumptions", []):
            st.info(assumption)

        result = message.get("result")

        if result is not None:
            dataframe = pd.DataFrame(
                result["rows"],
                columns=result["columns"],
            )

            st.dataframe(
                dataframe,
                hide_index=True,
                use_container_width=True,
            )

            if dataframe.empty:
                st.info(
                    "Aucune ligne retournée. "
                    "Cela ne prouve pas que les données couvrent "
                    "la période demandée."
                )

            elif dataframe.isna().all().all():
                st.info(
                    "Aucune valeur calculable pour cette sélection. "
                    "Les valeurs absentes ne signifient pas "
                    "automatiquement zéro."
                )

            for warning in result["warnings"]:
                # L'exécuteur applique déjà un plafond d'affichage.
                if not warning.startswith("Pas de LIMIT global"):
                    st.warning(warning)

            st.caption(
                f"{result['rows_returned']} ligne(s) affichée(s) "
                f"— calcul SQLite : {result['seconds']:.3f} s. "
                "Affichage plafonné à 100 lignes."
            )

            with st.expander("Voir le calcul et la requête SQL"):
                st.write(message["explanation"])
                st.code(result["sql"], language="sql")
                st.write("Paramètres")
                st.json(result["parameters"])

        if "seconds" in message:
            st.caption(
                f"Temps de réponse : {message['seconds']:.1f} s"
            )


def process_question(question):
    started = time.perf_counter()

    with st.status(
        "Analyse de votre question…",
        expanded=True,
    ) as status:

        proposal = generate_sql(
            question,
            history=st.session_state.sql_history,
        )

        result = None

        if proposal.status == "clarification":
            answer = proposal.clarification_question

        elif proposal.status == "unsupported":
            answer = proposal.explanation

        else:
            status.update(
                label="Vérification et calcul des résultats…"
            )

            parameters = {
                item.name: item.value
                for item in proposal.parameters
            }

            result = execute_generated_sql(
                proposal.sql,
                parameters,
            )

            answer = "Voici les résultats pour votre demande."

        status.update(
            label="Traitement terminé",
            state="complete",
            expanded=False,
        )

    response = {
        "role": "assistant",
        "text": answer,
        "explanation": proposal.explanation,
        "assumptions": proposal.assumptions,
        "result": result,
        "seconds": time.perf_counter() - started,
    }

    # Le modèle reçoit les échanges terminés pour comprendre
    # les précisions et les questions de suivi.
    memory = (
        "Proposition précédente :\n"
        + proposal.model_dump_json()
        + "\nRéponse affichée :\n"
        + answer
    )

    if result is not None:
        memory += "\nRésultats calculés :\n" + json.dumps(
            {
                "columns": result["columns"],
                "rows": result["rows"],
                "truncated": result["truncated"],
                "warnings": result["warnings"],
            },
            ensure_ascii=False,
        )

    # Enregistrer uniquement après un traitement réussi.
    st.session_state.sql_history.extend([
        {"role": "user", "text": question},
        {"role": "model", "text": memory},
    ])

    st.session_state.sql_messages.append(response)
    st.session_state.sql_pending = None
    st.session_state.sql_error = None


initialize_session()

with st.sidebar:
    st.title("Agent SQL")
    st.caption("Base de démonstration : Chinook")

    try:
        coverage = read_json(
            "knowledge/schema.json"
        )["invoice_date_range"]

        st.write("Dates des factures disponibles")
        st.write(
            f"{coverage['min'][:10]} → {coverage['max'][:10]}"
        )

    except (OSError, ValueError, KeyError, TypeError):
        st.warning("Période disponible non lisible.")

    st.caption(
        "Les dates extrêmes ne garantissent pas "
        "la complétude des données."
    )

    if st.button(
        "Nouvelle conversation",
        use_container_width=True,
    ):
        reset_conversation()
        st.rerun()

    st.divider()

    st.write("Exemples de questions")
    st.caption(
        "• Montant total facturé en avril 2010\n\n"
        "• Les cinq premiers clients par montant facturé en 2010\n\n"
        "• Montant vendu par genre musical en 2011"
    )

    st.caption(
        "La conversation n'est pas sauvegardée durablement. "
        "Un rechargement de la page peut effacer la session."
    )


st.title("Interrogez vos données")
st.write(
    "Posez une question en français. "
    "L’assistant vous demandera une précision si nécessaire."
)

for message in st.session_state.sql_messages:
    render_message(message)

if st.session_state.sql_error:
    st.error(st.session_state.sql_error)

if st.session_state.sql_pending and st.session_state.sql_error:
    st.info(
        "Votre question est conservée : "
        + st.session_state.sql_pending
    )

    retry_column, cancel_column = st.columns(2)

    with retry_column:
        if st.button(
            "Réessayer",
            use_container_width=True,
        ):
            st.session_state.sql_error = None
            st.session_state.sql_run_requested = True
            st.rerun()

    with cancel_column:
        if st.button(
            "Abandonner la question",
            use_container_width=True,
        ):
            st.session_state.sql_messages.append({
                "role": "assistant",
                "text": "Cette question a été abandonnée.",
            })
            st.session_state.sql_pending = None
            st.session_state.sql_error = None
            st.session_state.sql_run_requested = False
            st.rerun()


question = st.chat_input(
    "Exemple : quel est le montant total facturé en avril 2010 ?",
    disabled=st.session_state.sql_pending is not None,
)

if question and question.strip():
    question = question.strip()

    st.session_state.sql_messages.append({
        "role": "user",
        "text": question,
    })

    st.session_state.sql_pending = question
    st.session_state.sql_error = None
    st.session_state.sql_run_requested = True
    st.rerun()


if (
    st.session_state.sql_run_requested
    and st.session_state.sql_pending is not None
):
    # Éviter de relancer automatiquement l'API à chaque
    # réaffichage de la page.
    st.session_state.sql_run_requested = False

    try:
        process_question(st.session_state.sql_pending)

    except errors.APIError as error:
        st.session_state.sql_error = (
            f"Le service IA n'a pas répondu correctement "
            f"(code {error.code}). "
            "Vous pouvez réessayer votre question."
        )

    except SQLValidationError as error:
        st.session_state.sql_error = (
            f"La requête proposée a été refusée : {error}"
        )

    except SQLExecutionError as error:
        st.session_state.sql_error = str(error)

    except FileNotFoundError:
        st.session_state.sql_error = (
            "Un fichier nécessaire est introuvable. "
            "Vérifiez la base dans data et les fichiers dans knowledge."
        )

    except Exception as error:
        st.session_state.sql_error = (
            f"Erreur technique ({type(error).__name__}). "
            "Vérifiez la configuration du projet."
        )

    st.rerun()
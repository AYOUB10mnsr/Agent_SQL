import re
import sqlite3
from datetime import date, timedelta

import sqlglot
from sqlglot import exp

from validate_sql import DB_PATH


class PeriodValidationError(ValueError):
    pass


def contains_invoice_date(expression):
    return any(
        column.name.casefold() == "invoicedate"
        for column in expression.find_all(exp.Column)
    )


def split_conditions(expression):
    """Décomposer uniquement les conditions reliées par AND."""
    if isinstance(expression, exp.Paren):
        return split_conditions(expression.this)

    if isinstance(expression, exp.And):
        return (
            split_conditions(expression.this)
            + split_conditions(expression.expression)
        )

    return [expression]


def read_date_value(expression, parameters):
    if isinstance(expression, exp.Placeholder):
        value = parameters.get(expression.this)

    elif isinstance(expression, exp.Literal) and expression.is_string:
        value = expression.this

    else:
        raise PeriodValidationError(
            "La borne temporelle doit être une date littérale "
            "ou un paramètre nommé."
        )

    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}", value
    ):
        raise PeriodValidationError(
            "Utilise des dates au format AAAA-MM-JJ."
        )

    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise PeriodValidationError("Date invalide.") from error


def check_sql_period(sql, parameters):
    tree = sqlglot.parse_one(sql, read="sqlite")

    # Refuser les sous-requêtes temporelles pour cette première version :
    # leurs intervalles ne doivent pas être mélangés.
    selects = list(tree.find_all(exp.Select))

    if len(selects) > 1 and contains_invoice_date(tree):
        raise PeriodValidationError(
            "Le contrôle des dates ne prend pas encore en charge "
            "les sous-requêtes ou CTE utilisant InvoiceDate."
        )

    # Les filtres temporels en JOIN, HAVING ou CASE nécessitent
    # une analyse différente : ne pas les accepter silencieusement.
    for clause_type in (exp.Join, exp.Having, exp.Case):
        for clause in tree.find_all(clause_type):
            if contains_invoice_date(clause):
                raise PeriodValidationError(
                    "Filtre temporel complexe non pris en charge. "
                    "Utilise InvoiceDate dans WHERE avec >= et <."
                )

    where = tree.args.get("where")

    if where is None or not contains_invoice_date(where):
        return {
            "status": "no_explicit_range",
            "message": None,
        }

    conditions = split_conditions(where.this)
    starts = []
    ends = []

    for condition in conditions:
        if not contains_invoice_date(condition):
            continue

        if not isinstance(condition, (exp.GTE, exp.LT)):
            raise PeriodValidationError(
                "Filtre temporel non pris en charge. "
                "Utilise InvoiceDate >= début AND InvoiceDate < fin."
            )

        column = condition.this

        if (
            not isinstance(column, exp.Column)
            or column.name.casefold() != "invoicedate"
        ):
            raise PeriodValidationError(
                "InvoiceDate doit être directement à gauche "
                "de la comparaison, sans fonction ni conversion."
            )

        value = read_date_value(condition.expression, parameters)

        if isinstance(condition, exp.GTE):
            starts.append(value)
        else:
            ends.append(value)

    if not starts or not ends:
        raise PeriodValidationError(
            "Précise une borne de début incluse et une borne "
            "de fin exclue pour la période."
        )

    start = max(starts)
    end = min(ends)

    if start >= end:
        raise PeriodValidationError(
            "La période SQL est vide ou ses bornes sont inversées."
        )

    if not DB_PATH.is_file():
        raise FileNotFoundError(DB_PATH)

    connection = sqlite3.connect(
        DB_PATH.as_uri() + "?mode=ro",
        uri=True,
    )

    try:
        first, last = connection.execute("""
            SELECT MIN(InvoiceDate), MAX(InvoiceDate)
            FROM Invoice
        """).fetchone()
    finally:
        connection.close()

    if first is None or last is None:
        raise PeriodValidationError(
            "La base ne contient aucune facture."
        )

    first_date = date.fromisoformat(first[:10])
    last_date = date.fromisoformat(last[:10])
    available_end = last_date + timedelta(days=1)

    coverage = (
        "Les dates des factures présentes vont "
        f"du {first_date:%d/%m/%Y} au {last_date:%d/%m/%Y}."
    )

    if end <= first_date or start >= available_end:
        return {
            "status": "outside",
            "message": (
                "Période entièrement extérieure aux dates disponibles. "
                + coverage
                + " Aucun calcul effectué. "
                "Cela ne signifie pas que les ventes étaient nulles."
            ),
        }

    if start < first_date or end > available_end:
        return {
            "status": "partial",
            "message": (
                "La période demandée dépasse les dates disponibles. "
                + coverage
                + " Le résultat porte uniquement sur les données présentes."
            ),
        }

    return {
        "status": "within",
        "message": None,
    }
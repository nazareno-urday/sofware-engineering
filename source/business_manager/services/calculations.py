import math
from typing import Any


class ValidationError(ValueError):
    pass


def normalize_rows(
    rows: list[list[Any]], width: int = 3
) -> list[list[Any]]:
    result = []
    for row in rows:
        if len(row) > width:
            raise ValidationError("Unexpected extra columns")
        normalized = []
        for cell in row:
            if cell is None:
                cell = ""
            normalized.append(cell)
        while len(normalized) < width:
            normalized.append("")
        result.append(normalized)
    while result and all(cell == "" for cell in result[-1]):
        result.pop()
    return result


def parse_amount(value: Any, location: str) -> float:
    if value == "" or value is None:
        return 0.0
    try:
        if isinstance(value, bool):
            raise TypeError
        amount = float(value)
        if not math.isfinite(amount) or amount < 0:
            raise ValueError
    except (TypeError, ValueError) as error:
        raise ValidationError(
            f"{location}: invalid non-negative amount"
        ) from error
    return round(amount, 2)


def validate_movements(
    rows: list[list[Any]], sheet: str
) -> list[list[Any]]:
    movements = []
    for number, row in enumerate(normalize_rows(rows), 2):
        if all(cell == "" for cell in row):
            continue
        name, mp, cash = row
        if not isinstance(name, str) or not name.strip():
            raise ValidationError(
                f"{sheet}!A{number}: missing text description"
            )
        if mp == "" and cash == "":
            raise ValidationError(
                f"{sheet}!B{number}: missing payment amount"
            )
        movements.append(
            [
                name,
                parse_amount(mp, f"{sheet}!B{number}"),
                parse_amount(cash, f"{sheet}!C{number}"),
            ]
        )
    return movements


def sum_payments(rows: list[list[Any]]) -> tuple[float, float]:
    mp = 0.0
    cash = 0.0
    for row in rows:
        mp += row[1]
        cash += row[2]
    return round(mp, 2), round(cash, 2)


def calculate_day(
    income: list[list[Any]], expenses: list[list[Any]]
) -> dict[str, float]:
    sales = validate_movements(income, "Ingresos")
    costs = validate_movements(expenses, "Egresos")
    income_mp, income_cash = sum_payments(sales)
    expense_mp, expense_cash = sum_payments(costs)
    gross = round(income_mp + income_cash, 2)
    expense_total = round(expense_mp + expense_cash, 2)
    return {
        "income_mp": income_mp,
        "income_cash": income_cash,
        "gross_income": gross,
        "expense_mp": expense_mp,
        "expense_cash": expense_cash,
        "total_expenses": expense_total,
        "net_mp": round(income_mp - expense_mp, 2),
        "net_cash": round(income_cash - expense_cash, 2),
        "net_total": round(gross - expense_total, 2),
        "sale_count": len(sales),
    }

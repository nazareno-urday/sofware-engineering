import pytest
from business_manager.services.calculations import (
    ValidationError,
    calculate_day,
    validate_movements,
)


def test_real_business_example():
    result = calculate_day(
        [["laureano", 1000, 2000], ["comida", 8000, 7000]],
        [["coca", 2000, 900]],
    )
    assert result == {
        "income_mp": 9000,
        "income_cash": 9000,
        "gross_income": 18000,
        "expense_mp": 2000,
        "expense_cash": 900,
        "total_expenses": 2900,
        "net_mp": 7000,
        "net_cash": 8100,
        "net_total": 15100,
        "sale_count": 2,
    }


def test_blanks_short_rows_zero_and_mixed_payment():
    rows = [
        [],
        ["MP", 10],
        ["cash", "", 20],
        [],
        ["mixed", 5, 6],
        ["zero", 0],
    ]
    result = calculate_day(rows, [])
    assert result["sale_count"] == 4
    assert result["income_mp"] == 15
    assert result["income_cash"] == 26
    assert result["gross_income"] == 41
    assert calculate_day([], [])["sale_count"] == 0


@pytest.mark.parametrize(
    "row",
    [
        ["bad", "currency"],
        ["bad", -1],
        ["bad", float("nan")],
        ["bad", float("inf")],
        ["bad", True],
        ["missing"],
        ["", 12],
        [12, 10],
        ["bad", "1,25"],
    ],
)
def test_invalid_rows_identify_sheet_and_row(row):
    with pytest.raises(ValidationError, match="Egresos!"):
        validate_movements([[], row], "Egresos")


def test_consistent_cent_rounding():
    result = calculate_day(
        [["one", 0.1], ["two", 0.2], ["three", 1.234]], []
    )
    assert result["gross_income"] == 1.53

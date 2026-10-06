from copy import deepcopy
from datetime import date

import pytest
from business_manager.services.calculations import (
    ValidationError,
)
from business_manager.services.reports import (
    generate_pdf,
    parse_period,
)
from pypdf import PdfReader


@pytest.mark.parametrize(
    "kind", ["history", "sales", "expenses"]
)
def test_printable_pdf_over_500_rows_wraps_and_repeats_headers(
    kind,
):
    rows = (
        [["05/10/2026", 30, 10, 20, 5] for _ in range(520)]
        if kind == "history"
        else [
            [
                "05/10/2026",
                "Café, azúcar y " + "producto largo " * 14,
                10,
                20,
            ]
            for _ in range(520)
        ]
    )
    before = deepcopy(rows)
    pdf = generate_pdf(kind, rows)
    assert pdf.getvalue().startswith(b"%PDF-")
    reader = PdfReader(pdf)
    assert len(reader.pages) > 1
    assert all(
        "Fecha" in page.extract_text()
        and "Página" in page.extract_text()
        for page in reader.pages
    )
    text = "\n".join(
        page.extract_text() for page in reader.pages
    )
    assert "520" in text
    assert "5.200,00" in text
    if kind != "history":
        assert "Café, azúcar" in text
        assert "15.600,00" in text
    assert float(
        reader.pages[0].mediabox.width
    ) == pytest.approx(595.28, abs=0.1)
    assert rows == before


def test_period_filters_and_empty_pdf_are_valid():
    pdf = generate_pdf(
        "sales",
        [
            ["04/10/2026", "excluded", 1],
            ["05/10/2026", "included", "", 2],
        ],
        date(2026, 10, 5),
        date(2026, 10, 5),
    )
    text = PdfReader(pdf).pages[0].extract_text()
    assert "included" in text
    assert "excluded" not in text
    assert "$ 2,00" in text
    assert len(PdfReader(generate_pdf("history", [])).pages) == 1


def test_period_validation():
    assert parse_period("05/10/2026 - 06/10/2026") == (
        date(2026, 10, 5),
        date(2026, 10, 6),
    )
    with pytest.raises(ValidationError):
        parse_period("06/10/2026 - 05/10/2026")
    with pytest.raises(ValidationError):
        parse_period("nonsense")

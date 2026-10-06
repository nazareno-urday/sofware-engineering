from datetime import date, datetime
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import (
    ParagraphStyle,
    getSampleStyleSheet,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    LongTable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    TableStyle,
)

from business_manager.config import ARGENTINA
from business_manager.services.calculations import (
    ValidationError,
    normalize_rows,
    parse_amount,
)

REPORT_TITLES = {
    "history": "Historial de jornadas",
    "sales": "Registro de ventas",
    "expenses": "Registro de egresos",
}


def money(amount: float) -> str:
    return (
        f"$ {amount:,.2f}".replace(",", "_")
        .replace(".", ",")
        .replace("_", ".")
    )


def summary_text(
    business_date: str,
    results: dict[str, float],
    provisional: bool = False,
) -> str:
    title = (
        "Resumen provisional"
        if provisional
        else "Jornada cerrada"
    )
    label = date.fromisoformat(business_date).strftime(
        "%d/%m/%Y"
    )
    return (
        f"{title} — {label}\n"
        f"Ventas: {int(results['sale_count'])}\n"
        f"Ingresos MP: {money(results['income_mp'])}\n"
        f"Ingresos efectivo: {money(results['income_cash'])}\n"
        f"Ventas brutas: {money(results['gross_income'])}\n\n"
        f"Egresos MP: {money(results['expense_mp'])}\n"
        f"Egresos efectivo: {money(results['expense_cash'])}\n"
        f"Egresos totales: {money(results['total_expenses'])}\n\n"
        f"Saldo MP: {money(results['net_mp'])}\n"
        f"Saldo efectivo: {money(results['net_cash'])}\n"
        f"Saldo total: {money(results['net_total'])}\n"
        "Los saldos corresponden a movimientos del día."
    )


def parse_date(value: str) -> date:
    for pattern in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return (
                datetime.strptime(value.strip(), pattern)
                .replace(tzinfo=ARGENTINA)
                .date()
            )
        except ValueError:
            continue
    raise ValidationError("Invalid date; expected DD/MM/YYYY")


def parse_period(value: str) -> tuple[date, date]:
    pieces = value.split(" - ")
    if len(pieces) != 2:
        raise ValidationError("Expected DD/MM/YYYY - DD/MM/YYYY")
    start = parse_date(pieces[0])
    end = parse_date(pieces[1])
    if start > end:
        raise ValidationError(
            "Start date must not follow end date"
        )
    return start, end


def generate_pdf(
    kind: str,
    rows: list[list[Any]],
    start: date | None = None,
    end: date | None = None,
) -> BytesIO:
    if (start is None) != (end is None):
        raise ValidationError("Both period dates are required")
    if start and end and start > end:
        raise ValidationError("Invalid period")
    history = kind == "history"
    title = REPORT_TITLES[kind]
    width = 5 if history else 4
    filtered = []
    for index, row in enumerate(normalize_rows(rows, width), 2):
        if all(cell == "" for cell in row):
            continue
        try:
            row_date = parse_date(str(row[0]))
        except ValidationError as error:
            raise ValidationError(
                f"{title}, row {index}: invalid date"
            ) from error
        if start and end and not start <= row_date <= end:
            continue
        if not history and (
            not isinstance(row[1], str) or not row[1].strip()
        ):
            raise ValidationError(
                f"{title}, row {index}: missing description"
            )
        first_amount = 1 if history else 2
        amounts = [
            parse_amount(value, f"{title}, row {index}")
            for value in row[first_amount:]
        ]
        report_row: list[Any] = [row_date.strftime("%d/%m/%Y")]
        if not history:
            report_row.append(row[1])
        report_row.extend(amounts)
        filtered.append(report_row)
    font_dir = Path(reportlab.__file__).parent / "fonts"
    if "BusinessVera" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(
            TTFont("BusinessVera", str(font_dir / "Vera.ttf"))
        )
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "BusinessBody",
        fontName="BusinessVera",
        fontSize=8,
        leading=11,
        splitLongWords=True,
    )
    numeric = ParagraphStyle(
        "BusinessNumeric", parent=body, alignment=TA_RIGHT
    )
    heading = ParagraphStyle(
        "BusinessHeading",
        parent=body,
        textColor=colors.white,
    )
    headers = (
        [
            "Fecha",
            "Total bruto",
            "Ingresos MP",
            "Ingresos efectivo",
            "Total egresos",
        ]
        if history
        else [
            "Fecha",
            "Producto" if kind == "sales" else "Egreso",
            "Mercado Pago",
            "Efectivo",
        ]
    )
    table_data = [
        [Paragraph(escape(item), heading) for item in headers]
    ]
    first_amount = 1 if history else 2
    totals = [0.0] * (width - first_amount)
    for row in filtered:
        cells = []
        for column, value in enumerate(row):
            if column < first_amount:
                cell = Paragraph(escape(str(value)), body)
            else:
                cell = Paragraph(escape(money(value)), numeric)
                totals[column - first_amount] += value
            cells.append(cell)
        table_data.append(cells)
    total_row = [Paragraph("Totales", body)]
    if not history:
        total_row.append(Paragraph("", body))
    for index, total in enumerate(totals):
        totals[index] = round(total, 2)
        total_row.append(
            Paragraph(escape(money(totals[index])), numeric)
        )
    table_data.append(total_row)
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=30,
        rightMargin=30,
        topMargin=35,
        bottomMargin=35,
        title=title,
        author="Business Manager",
    )
    period = (
        f"{start:%d/%m/%Y} al {end:%d/%m/%Y}"
        if start and end
        else "Todo el registro"
    )
    table = LongTable(
        table_data,
        colWidths=(
            [75, 98, 98, 98, 166]
            if history
            else [75, 260, 100, 100]
        ),
        repeatRows=1,
        splitInRow=1,
    )
    table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#23445c"),
                ),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -2),
                    [colors.white, colors.HexColor("#f0f3f5")],
                ),
                (
                    "LINEBELOW",
                    (0, -1),
                    (-1, -1),
                    0.5,
                    colors.grey,
                ),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    def page_number(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont("BusinessVera", 8)
        canvas.drawRightString(
            A4[0] - 30, 18, f"Página {doc.page}"
        )
        canvas.restoreState()

    story = [
        Paragraph(escape(title), styles["Title"]),
        Paragraph(escape(period), body),
        Spacer(1, 12),
        table,
        Spacer(1, 10),
        Paragraph(f"Filas del período: {len(filtered)}", body),
    ]
    if not history:
        story.append(
            Paragraph(
                f"Total de ambos medios: {money(round(sum(totals), 2))}",
                body,
            )
        )
    document.build(
        story, onFirstPage=page_number, onLaterPages=page_number
    )
    buffer.seek(0)
    return buffer

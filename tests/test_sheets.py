from pathlib import Path
from unittest.mock import Mock

import pytest
from business_manager.services.sheets import (
    HEADERS,
    SheetConflict,
    SheetsClient,
)


def response(values=None):
    result = Mock()
    result.json.return_value = (
        {} if values is None else {"values": values}
    )
    return result


def test_failed_daily_read_raises_instead_of_shifted_results():
    session = Mock()
    session.request.side_effect = [
        response([["sale", 5]]),
        TimeoutError("unavailable"),
    ]
    client = SheetsClient("test", Path("unused"), session)
    with pytest.raises(TimeoutError):
        client.read_daily()
    assert session.request.call_count == 2
    assert "UNFORMATTED_VALUE" in str(
        session.request.call_args_list
    )


def test_missing_values_and_trailing_cells_preserve_columns():
    session = Mock()
    session.request.side_effect = [
        response(),
        response([["cash", "", 25]]),
    ]
    client = SheetsClient("test", Path("unused"), session)
    assert client.read_daily() == {
        "Ingresos": [],
        "Egresos": [["cash", "", 25]],
    }


def test_archive_reads_are_unbounded_and_clear_is_values_only():
    session = Mock()
    session.request.return_value = response()
    client = SheetsClient("test", Path("unused"), session)
    for kind in ("history", "sales", "expenses"):
        client.read_archive(kind)
    assert all(
        "500" not in call.args[1]
        for call in session.request.call_args_list
    )
    client.clear_rows(["Ingresos!A2:C2", "Egresos!A7:C7"])
    call = session.request.call_args
    assert call.args[1].endswith("/values:batchClear")
    assert call.kwargs["json"] == {
        "ranges": ["Ingresos!A2:C2", "Egresos!A7:C7"]
    }


def test_lazy_auth_does_not_require_credentials_on_creation():
    client = SheetsClient("test", Path("does-not-exist"))
    assert client._session is None


def test_layout_does_not_overwrite_missing_expense_headers():
    client = SheetsClient("test", Path("unused"))
    client._request = Mock(
        return_value={
            "sheets": [
                {"properties": {"title": title}}
                for title in (
                    "Ingresos",
                    "Egresos",
                    "Historial",
                    "Registro ingresos",
                )
            ]
        }
    )
    client.read = Mock(
        side_effect=[
            [HEADERS[key]] if "!F1" not in key else []
            for key in HEADERS
        ]
    )
    client.write = Mock()
    with pytest.raises(SheetConflict, match="F1:I1"):
        client.check_layout()
    client.write.assert_not_called()


def test_growth_adds_rows_without_replacing_sheets():
    session = Mock()
    metadata = Mock()
    metadata.json.return_value = {
        "sheets": [
            {
                "properties": {
                    "title": "Registro ingresos",
                    "sheetId": 9,
                    "gridProperties": {"rowCount": 500},
                }
            }
        ]
    }
    session.request.side_effect = [metadata, response()]
    client = SheetsClient("test", Path("unused"), session)
    client.ensure_rows("'Registro ingresos'!A501:D502")
    assert session.request.call_args.kwargs["json"] == {
        "requests": [
            {
                "appendDimension": {
                    "sheetId": 9,
                    "dimension": "ROWS",
                    "length": 2,
                }
            }
        ]
    }

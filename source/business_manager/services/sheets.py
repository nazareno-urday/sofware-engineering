from pathlib import Path
from threading import RLock
from typing import Any
from urllib.parse import quote

from google.auth.transport.requests import AuthorizedSession
from google.oauth2.service_account import Credentials

from business_manager.services.calculations import normalize_rows

DAILY_RANGES = {
    "Ingresos": "Ingresos!A2:C500",
    "Egresos": "Egresos!A2:C500",
}
ARCHIVE_RANGES = {
    "history": "Historial!A2:E",
    "sales": "'Registro ingresos'!A2:D",
    "expenses": "'Registro ingresos'!F2:I",
}
HEADERS = {
    "Ingresos!A1:C1": ["Producto", "Mercado Pago", "Efectivo"],
    "Egresos!A1:C1": ["Egreso", "Mercado Pago", "Efectivo"],
    "Historial!A1:E1": [
        "Fecha",
        "Total",
        "Total Mercado Pago",
        "Total efectivo",
        "Total egresos",
    ],
    "'Registro ingresos'!A1:D1": [
        "Fecha",
        "Producto",
        "Mercado Pago",
        "Efectivo",
    ],
    "'Registro ingresos'!F1:I1": [
        "Fecha",
        "Egreso",
        "Mercado Pago",
        "Efectivo",
    ],
}


class SheetConflict(RuntimeError):
    pass


class SheetsClient:
    def __init__(
        self,
        sheet_id: str,
        credentials_file: Path,
        session: Any = None,
    ) -> None:
        self.sheet_id = sheet_id
        self.credentials_file = credentials_file
        self._session = session
        self.lock = RLock()
        self.base_url = (
            "https://sheets.googleapis.com/v4/spreadsheets/"
            + sheet_id
        )

    def _request(
        self, method: str, suffix: str, **kwargs: Any
    ) -> dict[str, Any]:
        with self.lock:
            if self._session is None:
                credentials = Credentials.from_service_account_file(
                    str(self.credentials_file),
                    scopes=[
                        "https://www.googleapis.com/auth/spreadsheets"
                    ],
                )
                self._session = AuthorizedSession(credentials)
            response = self._session.request(
                method,
                self.base_url + suffix,
                timeout=15,
                **kwargs,
            )
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result

    def read(self, cell_range: str) -> list[list[Any]]:
        data = self._request(
            "GET",
            "/values/" + quote(cell_range, safe=""),
            params={
                "valueRenderOption": "UNFORMATTED_VALUE",
                "dateTimeRenderOption": "FORMATTED_STRING",
            },
        )
        return list(data.get("values", []))

    def write(
        self, cell_range: str, rows: list[list[Any]]
    ) -> None:
        self._request(
            "PUT",
            "/values/" + quote(cell_range, safe=""),
            params={"valueInputOption": "RAW"},
            json={"majorDimension": "ROWS", "values": rows},
        )

    def read_daily(self) -> dict[str, list[list[Any]]]:
        with self.lock:
            daily = {}
            for name, cell_range in DAILY_RANGES.items():
                rows = self.read(cell_range)
                daily[name] = normalize_rows(rows)
            return daily

    def read_archive(self, kind: str) -> list[list[Any]]:
        with self.lock:
            return self.read(ARCHIVE_RANGES[kind])

    def check_layout(self) -> None:
        with self.lock:
            metadata = self._request(
                "GET", "", params={"fields": "sheets.properties"}
            )
            titles = {
                item["properties"]["title"]
                for item in metadata["sheets"]
            }
            if titles != {
                "Ingresos",
                "Egresos",
                "Historial",
                "Registro ingresos",
            }:
                raise SheetConflict(
                    "Expected exactly four sheets"
                )
            for cell_range, expected in HEADERS.items():
                actual = normalize_rows(
                    self.read(cell_range), len(expected)
                )
                if actual != [expected]:
                    raise SheetConflict(
                        f"Header mismatch: {cell_range}"
                    )
            if normalize_rows(
                self.read("'Registro ingresos'!E:E"), 1
            ):
                raise SheetConflict("Column E must be empty")

    def reserve_range(self, kind: str, count: int) -> str:
        existing = self.read_archive(kind)
        start = len(existing) + 2
        prefix, columns = ARCHIVE_RANGES[kind].split("!")
        first = columns[0]
        last = columns[-1]
        return (
            f"{prefix}!{first}{start}:{last}{start + count - 1}"
        )

    def ensure_rows(self, cell_range: str) -> None:
        title, coordinates = cell_range.split("!")
        title = title.strip("'")
        last_cell = coordinates.split(":")[-1]
        end = int(last_cell.lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
        metadata = self._request(
            "GET", "", params={"fields": "sheets.properties"}
        )
        properties = None
        for sheet in metadata["sheets"]:
            if sheet["properties"]["title"] == title:
                properties = sheet["properties"]
                break
        if properties is None:
            raise SheetConflict(f"Missing sheet: {title}")
        current = properties["gridProperties"]["rowCount"]
        if end > current:
            self._request(
                "POST",
                ":batchUpdate",
                json={
                    "requests": [
                        {
                            "appendDimension": {
                                "sheetId": properties["sheetId"],
                                "dimension": "ROWS",
                                "length": end - current,
                            }
                        }
                    ]
                },
            )

    def write_verified(
        self, cell_range: str, rows: list[list[Any]]
    ) -> None:
        with self.lock:
            width = len(rows[0])
            self.ensure_rows(cell_range)
            actual = normalize_rows(self.read(cell_range), width)
            expected = normalize_rows(rows, width)
            if actual == expected:
                return
            for index, row in enumerate(actual):
                for column, value in enumerate(row):
                    if value != "" and (
                        index >= len(expected)
                        or value != expected[index][column]
                    ):
                        raise SheetConflict(
                            f"Archive conflict: {cell_range}"
                        )
            self.write(cell_range, rows)
            if (
                normalize_rows(self.read(cell_range), width)
                != expected
            ):
                raise SheetConflict(
                    f"Archive verification failed: {cell_range}"
                )

    def clear_rows(self, ranges: list[str]) -> None:
        if ranges:
            self._request(
                "POST",
                "/values:batchClear",
                json={"ranges": ranges},
            )

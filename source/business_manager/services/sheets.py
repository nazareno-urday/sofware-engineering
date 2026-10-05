from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials


def get_urls() -> list[dict]:
    reader: list[dict] = []

    if not credentials.valid:
        credentials.refresh(Request())
        headers["Authorization"] = f"Bearer {credentials.token}"

    for url in urls:
        try:
            response = requests.get(
                url,
                headers=headers,
                timeout=10,
            )
            response.raise_for_status()

            data = response.json()
            reader.append(data)

        except requests.exceptions.Timeout as error:
            print(f"TIMEOUT: {error}")

        except requests.exceptions.HTTPError as error:
            print(f"Error HTTP: {error}")

            if error.response is not None:
                print(error.response.text[:200])

        except requests.exceptions.JSONDecodeError as error:
            print(f"Invalid JSON response: {error}")

        except requests.exceptions.RequestException as error:
            print(f"Connection error: {error}")

    return reader


def guardar_ingresos(ingresos: dict) -> int:
    filas = ingresos.get("values", [])

    if not filas:
        return 0

    argentina_timezone = timezone(timedelta(hours=-3))
    fecha = datetime.now(argentina_timezone).strftime("%d/%m/%Y")

    filas_con_fecha = [[fecha, *fila] for fila in filas]

    rango = quote(REGISTRO_INGRESOS_RANGE, safe="")

    url = (
        "https://sheets.googleapis.com/v4/spreadsheets/"
        f"{SHEET_ID}/values/{rango}:append"
    )

    if not credentials.valid:
        credentials.refresh(Request())
        headers["Authorization"] = f"Bearer {credentials.token}"

    response = requests.post(
        url,
        headers=headers,
        params={
            "valueInputOption": "RAW",
            "insertDataOption": "INSERT_ROWS",
        },
        json={
            "majorDimension": "ROWS",
            "values": filas_con_fecha,
        },
        timeout=10,
    )

    response.raise_for_status()

    data = response.json()
    return int(data["updates"]["updatedRows"])


# Global variables
SHEET_ID = "1D7v4Tdd8ktjq5vAMdh831MZx6EjsvFu1_VT2Bu3yaTI"

INGRESOS_RANGE = "Ingresos!A2:C500"
EGRESOS_RANGE = "Egresos!A2:C500"
HISTORIAL_RANGE = "Historial!A2:E500"
REGISTRO_INGRESOS_RANGE = "'Registro ingresos'!A1:D"

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CREDENTIALS_FILE = PROJECT_ROOT / "credentials.json"

credentials = Credentials.from_service_account_file(
    CREDENTIALS_FILE,
    scopes=["https://www.googleapis.com/auth/spreadsheets"],
)

credentials.refresh(Request())

url_ingresos = (
    "https://sheets.googleapis.com/v4/spreadsheets/"
    f"{SHEET_ID}/values/{INGRESOS_RANGE}"
)

url_egresos = (
    "https://sheets.googleapis.com/v4/spreadsheets/"
    f"{SHEET_ID}/values/{EGRESOS_RANGE}"
)

url_historial = (
    "https://sheets.googleapis.com/v4/spreadsheets/"
    f"{SHEET_ID}/values/{HISTORIAL_RANGE}"
)

urls = [url_ingresos, url_egresos, url_historial]

headers = {
    "Authorization": f"Bearer {credentials.token}",
    "Accept": "application/json",
}
import json
from pathlib import Path

import requests
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials


def get_urls(urls, headers):
    for url in urls:
        try:
            response = requests.get(
                url,
                headers=headers,
                timeout=10,
            )
            response.raise_for_status()

            data = response.json()

            print(response.status_code)
            print(
                json.dumps(
                    data.get("values", []),
                    indent=4,
                )
            )

        except requests.exceptions.Timeout as error:
            print(f"Tiempo de espera agotado: {error}")

        except requests.exceptions.HTTPError as error:
            print(f"Error HTTP: {error}")

            if error.response is not None:
                print(error.response.text[:200])

        except requests.exceptions.JSONDecodeError as error:
            print(f"Respuesta JSON inválida: {error}")

        except requests.exceptions.RequestException as error:
            print(f"Error de conexión: {error}")


# Global variables
SHEET_ID = "1D7v4Tdd8ktjq5vAMdh831MZx6EjsvFu1_VT2Bu3yaTI"
INGRESOS_RANGE = "Ingresos!A2:C500"
EGRESOS_RANGE = "Egresos!A2:C500"
HISTORIAL_RANGE = "Historial!A2:C500"
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

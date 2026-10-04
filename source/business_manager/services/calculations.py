import json
from datetime import datetime


def limpiar_monto(valor) -> float:
    """Parsea números que puedan venir como int, float, string vacío o '$ 5.000'."""
    if valor is None or valor == "":
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)

    # Si Sheets lo manda como string con formato
    val_str = (
        str(valor)
        .replace("$", "")
        .replace(".", "")
        .replace(",", ".")
        .replace(" ", "")
    )
    try:
        return float(val_str)
    except ValueError:
        return 0.0


def calcular_totales_cierre(
    ingresos, egresos, fecha: str = None
) -> dict:
    """Calcula los totales para la Tabla 3 a partir de los diccionarios de ingresos y egresos.

    - ingresos: lista de dicts (o texto JSON) con keys: 'producto', 'transferencia', 'efectivo'
    - egresos: lista de dicts (o texto JSON) con keys: 'nombre', 'monto'
    """
    # Si Sheets o el bot mandan un string en formato JSON, lo pasa a diccionarios
    if isinstance(ingresos, str):
        ingresos = json.loads(ingresos)
    if isinstance(egresos, str):
        egresos = json.loads(egresos)

    if not fecha:
        fecha = datetime.now().strftime("%d/%m/%Y")

    # 1. Sumar ingresos (transferencias y efectivo)
    total_transferencia = sum(
        limpiar_monto(item.get("transferencia", 0)) for item in ingresos
    )
    total_efectivo = sum(
        limpiar_monto(item.get("efectivo", 0)) for item in ingresos
    )
    total_ingresos = total_transferencia + total_efectivo

    # 2. Sumar egresos
    total_egresos = sum(
        limpiar_monto(item.get("monto", 0)) for item in egresos
    )

    # 3. Balance final (Total Neto en mano/cuenta)
    balance_neto = total_ingresos - total_egresos

    # 4. Diccionario final con las columnas exactas de tu Tabla 3
    resumen_tabla_3 = {
        "fecha": fecha,
        "total": balance_neto,  # O podés poner total_ingresos si el cliente quiere el bruto
        "total_de_transferencia": total_transferencia,
        "total_en_efectivo": total_efectivo,
        "total_de_egresos": total_egresos,
    }

    return resumen_tabla_3
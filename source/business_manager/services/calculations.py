"Tabla 1 Ingresos"
import json

def limpiar_monto(valor) -> float:
    """Normaliza números que vienen de Sheets como int, float, '$ 4.500' o vacíos."""
    if valor is None or valor == "":
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)

    val_str = (
        str(valor)
        .replace("$", "")
        .replace(".", "")
        .replace(",", ".")
        .strip()
    )
    try:
        return float(val_str)
    except ValueError:
        return 0.0


def procesar_tabla_ingresos(ingresos_raw) -> dict:
    """Procesa los ingresos de la feria: separa transferencias, efectivo y calcula totales.

    Acepta 'nombre del producto' o 'producto' como clave del ítem.
    Soporta lista de diccionarios o string en formato JSON.
    """
    # Si viene como string en formato JSON, lo convertimos a lista de diccionarios
    if isinstance(ingresos_raw, str):
        ingresos_raw = json.loads(ingresos_raw)

    ventas_limpias = []
    total_transferencia = 0.0
    total_efectivo = 0.0

    for item in ingresos_raw:
        # Soportamos ambos nombres de columna por si tus compas usan uno u otro en Sheets
        producto = str(
            item.get("nombre del producto") or item.get("producto") or ""
        ).strip()
        transf = limpiar_monto(item.get("transferencia", 0))
        efec = limpiar_monto(item.get("efectivo", 0))

        # Saltea filas completamente vacías al final de la hoja
        if not producto and transf == 0.0 and efec == 0.0:
            continue

        if not producto:
            producto = "Venta sin nombre"

        total_venta = transf + efec

        ventas_limpias.append({
            "producto": producto,
            "transferencia": transf,
            "efectivo": efec,
            "total_venta": total_venta,
        })

        total_transferencia += transf
        total_efectivo += efec

    total_ingresos = total_transferencia + total_efectivo

    return {
        "total_transferencia": total_transferencia,
        "total_efectivo": total_efectivo,
        "total_ingresos": total_ingresos,
        "cantidad_ventas": len(ventas_limpias),
        "desglose": ventas_limpias,
    }



"Tabla 2 Egresos"

import json
def limpiar_monto(valor) -> float:
    """Normaliza números que vienen de Sheets como int, float, '$ 3.500' o vacíos."""
    if valor is None or valor == "":
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)

    val_str = (
        str(valor)
        .replace("$", "")
        .replace(".", "")
        .replace(",", ".")
        .strip()
    )
    try:
        return float(val_str)
    except ValueError:
        return 0.0


def procesar_tabla_egresos(egresos_raw) -> dict:
    """Lee y procesa la lista de diccionarios (o string JSON) de la Tabla 2 (Egresos).

    Espera diccionarios con keys: 'nombre' y 'monto'.
    """
    # Si viene como string en formato JSON, lo convertimos a lista de diccionarios
    if isinstance(egresos_raw, str):
        egresos_raw = json.loads(egresos_raw)

    egresos_limpios = []
    total_acumulado = 0.0

    for item in egresos_raw:
        # Obtenemos la razón del gasto y el monto
        razon = str(item.get("nombre", "")).strip()
        monto = limpiar_monto(item.get("monto", 0))

        # Ignoramos filas fantasma de Sheets (sin nombre y sin monto)
        if not razon and monto == 0.0:
            continue

        # Si puso monto pero dejó el nombre vacío, le asignamos un default
        if not razon:
            razon = "Gasto sin concepto"

        egreso_parseado = {
            "razon": razon,
            "monto": monto
        }

        egresos_limpios.append(egreso_parseado)
        total_acumulado += monto

    # Diccionario final consolidado de la Tabla 2
    resumen_egresos = {
        "total_egresos": total_acumulado,
        "cantidad_registros": len(egresos_limpios),
        "desglose": egresos_limpios  # Lista de dicts limpios con cada gasto
    }

    return resumen_egresos


"Tabla 3 Totales"

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
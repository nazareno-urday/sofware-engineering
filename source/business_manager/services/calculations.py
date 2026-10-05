def sumar_importes(
    filas: list[list[str]],
) -> tuple[float, float]:

    mercado_pago = 0.0
    efectivo = 0.0

    for fila in filas:
        if len(fila) > 1 and fila[1]:
            mercado_pago += float(fila[1])

        if len(fila) > 2 and fila[2]:
            efectivo += float(fila[2])

    return mercado_pago, efectivo


def calcular_dia(
    ingresos: dict,
    egresos: dict,
) -> dict[str, float]:

    ingresos_mp, ingresos_efectivo = sumar_importes(
        ingresos.get("values", [])
    )

    egresos_mp, egresos_efectivo = sumar_importes(
        egresos.get("values", [])
    )

    total_ingresos = ingresos_mp + ingresos_efectivo
    total_egresos = egresos_mp + egresos_efectivo

    return {
        "total_ingresos": total_ingresos,
        "ingresos_mp": ingresos_mp,
        "ingresos_efectivo": ingresos_efectivo,
        "total_egresos": total_egresos,
        "egresos_mp": egresos_mp,
        "egresos_efectivo": egresos_efectivo,
        "saldo_mp": ingresos_mp - egresos_mp,
        "saldo_efectivo": ingresos_efectivo - egresos_efectivo,
        "saldo_total": total_ingresos - total_egresos,
    }

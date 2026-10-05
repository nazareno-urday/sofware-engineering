import asyncio
from datetime import date, datetime

from google.auth.exceptions import GoogleAuthError
from reportlab.platypus import LayoutError
from requests.exceptions import RequestException
from telegram import Message, ReplyKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from business_manager.config import ARGENTINA
from business_manager.jobs.close_day import deliver_pending
from business_manager.services.calculations import (
    ValidationError,
)
from business_manager.services.day_closure import ClosureError
from business_manager.services.reports import (
    generate_pdf,
    parse_date,
    parse_period,
    summary_text,
)
from business_manager.services.sheets import SheetConflict

REPORT_BUTTONS = {
    "Imprimir historial": "history",
    "Imprimir ventas": "sales",
    "Imprimir egresos": "expenses",
}
MENU_ROWS = [
    ["Comenzar el día", "Ver resumen"],
    ["Imprimir historial", "Imprimir ventas"],
    ["Imprimir egresos", "Cerrar día"],
    ["Recuperación"],
]


def menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        MENU_ROWS, resize_keyboard=True, is_persistent=True
    )


def options_keyboard(*rows: list[str]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def user_error(error: Exception) -> str:
    if isinstance(error, ValidationError):
        detail = str(error)
        translations = {
            "Future date is not allowed": "la fecha no puede ser futura",
            "missing description": "falta el nombre o concepto",
            "invalid date": "fecha inválida",
            "Unexpected extra columns": "hay columnas adicionales inesperadas",
            "Both period dates are required": "se requieren ambas fechas",
            "Invalid period": "período inválido",
            "invalid non-negative amount": "importe inválido: usá un número mayor o igual a cero",
            "missing text description": "falta el nombre o concepto",
            "missing payment amount": "falta al menos un importe",
            "Invalid date; expected DD/MM/YYYY": "fecha inválida: usá DD/MM/AAAA",
            "Expected DD/MM/YYYY - DD/MM/YYYY": "usá DD/MM/AAAA - DD/MM/AAAA",
            "Start date must not follow end date": "la fecha inicial debe ser anterior o igual a la final",
        }
        for original, translated in translations.items():
            detail = detail.replace(original, translated)
        return (
            f"Revisá los datos: {detail}. No se limpiaron hojas."
        )
    if isinstance(error, SheetConflict):
        return (
            "Hay un conflicto en encabezados o registros permanentes. "
            "Revisá las cuatro pestañas y los rangos del journal. "
            "No se limpiaron movimientos sin verificar su archivo."
        )
    if isinstance(error, ClosureError):
        messages = {
            "This business date is already closed": "Esta jornada ya está cerrada. No se agregaron filas.",
            "The active day belongs to another authorized user": "La jornada pertenece a otro usuario autorizado. "
            "El destinatario no se modificó.",
            "No active day; nothing was changed": "No hay jornada activa; no se modificó nada.",
            "No active day": "No hay jornada activa.",
            "No ambiguous cleanup to confirm": "No hay una limpieza interrumpida para confirmar.",
        }
        return messages.get(
            str(error),
            (
                "No pude terminar el cierre. No cargues datos nuevos. "
                "Revisá los movimientos y seguí los pasos de "
                "recuperación del README antes de reintentar."
            ),
        )
    return (
        "No pude completar la operación. Revisá la conexión "
        "y los permisos. Si estabas cerrando el día, "
        "seguí los pasos de recuperación del README."
    )


async def send_report(
    message: Message,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    today: date,
) -> None:
    if context.user_data is None:
        return
    flow = context.user_data["flow"]
    if text == "Elegir fechas":
        flow["awaiting_dates"] = True
        await message.reply_text(
            "Enviá DD/MM/AAAA - DD/MM/AAAA",
            reply_markup=options_keyboard(["Volver"]),
        )
        return
    start = end = None
    if text == "Hoy":
        start = end = today
    elif text != "Todo":
        if not flow.get("awaiting_dates") or not text:
            context.user_data.clear()
            await message.reply_text(
                "Elegí una opción del menú.",
                reply_markup=menu_keyboard(),
            )
            return
        start, end = parse_period(text)
    kind = flow["kind"]
    sheets = context.application.bot_data["sheets"]
    rows = await asyncio.to_thread(sheets.read_archive, kind)
    document = await asyncio.to_thread(
        generate_pdf, kind, rows, start, end
    )
    await message.reply_document(
        document=document,
        filename=f"{kind}.pdf",
        caption="Reporte listo para abrir e imprimir.",
        reply_markup=menu_keyboard(),
    )
    context.user_data.clear()


async def handle_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if (
        message is None
        or user is None
        or chat is None
        or context.user_data is None
    ):
        return
    config = context.application.bot_data["config"]
    text = message.text or ""
    if text in {"/id", "/id@" + context.bot.username}:
        await message.reply_text(f"Tu ID de Telegram: {user.id}")
        return
    if (
        chat.type != "private"
        or user.id not in config.allowed_user_ids
    ):
        await message.reply_text(
            "Acceso restringido. En una conversación privada, "
            "enviá /id y pedí al administrador que autorice tu ID."
        )
        return
    closure = context.application.bot_data["closure"]
    today = datetime.now(ARGENTINA).date()
    flow = context.user_data.get("flow")
    try:
        if text in {"Volver", "/start", "Menú"}:
            context.user_data.clear()
        elif text == "Comenzar el día":
            context.user_data.clear()
            day = await asyncio.to_thread(
                closure.start, today, chat.id, user.id
            )
            await message.reply_text(
                f"Jornada registrada: {day['date']}.\n"
                f"{config.sheet_url}\n"
                "Cargá movimientos en Ingresos y Egresos, filas "
                "2 a 500. Si la jornada es anterior a hoy, revisá "
                "y cerrala antes de cargar datos nuevos.",
                reply_markup=menu_keyboard(),
            )
            return
        elif text == "Ver resumen":
            context.user_data.clear()
            results = await asyncio.to_thread(closure.preview)
            day = await asyncio.to_thread(closure.active_day)
            business_date = today.isoformat()
            if day:
                business_date = day["date"]
            report = summary_text(
                business_date, results, provisional=True
            )
            if day is None:
                report += (
                    "\nSin jornada registrada. Usá Comenzar el día "
                    "o Recuperación para asignar estos movimientos."
                )
            await message.reply_text(
                report, reply_markup=menu_keyboard()
            )
            return
        elif text in REPORT_BUTTONS:
            context.user_data["flow"] = {
                "action": "report",
                "kind": REPORT_BUTTONS[text],
            }
            await message.reply_text(
                "Elegí el período. Hoy puede estar vacío si "
                "la jornada todavía no se cerró.",
                reply_markup=options_keyboard(
                    ["Todo", "Hoy"], ["Elegir fechas", "Volver"]
                ),
            )
            return
        elif text == "Cerrar día":
            context.user_data.clear()
            day = await asyncio.to_thread(closure.active_day)
            if day is None:
                await message.reply_text(
                    "No hay jornada activa. Si ya cerraste, no se "
                    "volverán a agregar registros. Si hay movimientos "
                    "sin jornada, usá Recuperación.",
                    reply_markup=menu_keyboard(),
                )
                return
            context.user_data["flow"] = {"action": "close"}
            await message.reply_text(
                f"Vas a cerrar la jornada {day['date']}. "
                "Dejá de editar Sheets hasta recibir el resultado. "
                "Si el proceso estuvo apagado, comprobá que no "
                "haya movimientos de distintas fechas mezclados. "
                "El cierre usará la fecha registrada.",
                reply_markup=options_keyboard(
                    ["Confirmar cierre", "Volver"]
                ),
            )
            return
        elif text == "Recuperación":
            context.user_data["flow"] = {"action": "recovery"}
            await message.reply_text(
                "Para datos sin jornada, registrá su fecha real. "
                "Para una limpieza interrumpida, primero revisá "
                ".state/journal.json y el procedimiento del README; "
                "se exige que las filas archivadas estén vacías.",
                reply_markup=options_keyboard(
                    ["Registrar jornada pendiente"],
                    ["Confirmar limpieza revisada", "Volver"],
                ),
            )
            return
        elif (
            flow
            and flow["action"] == "close"
            and text == "Confirmar cierre"
        ):
            context.user_data.clear()
            await asyncio.to_thread(
                closure.close, chat.id, user.id
            )
            await deliver_pending(context.application)
            await message.reply_text(
                "Cierre guardado. Las hojas quedan disponibles "
                "para la próxima jornada. Si el aviso no llegó, "
                "se reintentará sin volver a archivar.",
                reply_markup=menu_keyboard(),
            )
            return
        elif flow and flow["action"] == "recovery":
            if text == "Registrar jornada pendiente":
                context.user_data["flow"] = {
                    "action": "recover_date"
                }
                await message.reply_text(
                    "Enviá la fecha de esos movimientos: DD/MM/AAAA. "
                    "Separá manualmente las jornadas mezcladas primero.",
                    reply_markup=options_keyboard(["Volver"]),
                )
                return
            if text == "Confirmar limpieza revisada":
                await asyncio.to_thread(
                    closure.confirm_reviewed_cleanup,
                    chat.id,
                    user.id,
                )
                context.user_data.clear()
                await deliver_pending(context.application)
                await message.reply_text(
                    "Limpieza revisada y cierre confirmado.",
                    reply_markup=menu_keyboard(),
                )
                return
        elif flow and flow["action"] == "recover_date" and text:
            recovered_date = parse_date(text)
            if recovered_date > today:
                raise ValidationError(
                    "Future date is not allowed"
                )
            day = await asyncio.to_thread(
                closure.start, recovered_date, chat.id, user.id
            )
            context.user_data.clear()
            await message.reply_text(
                f"Jornada registrada: {day['date']}. "
                "Revisá el resumen y usá Cerrar día.",
                reply_markup=menu_keyboard(),
            )
            return
        elif flow and flow["action"] == "report":
            await send_report(message, context, text, today)
            return
        context.user_data.clear()
        await message.reply_text(
            "Elegí una opción para administrar el negocio.",
            reply_markup=menu_keyboard(),
        )
    except (
        ValueError,
        OSError,
        ClosureError,
        SheetConflict,
        RequestException,
        GoogleAuthError,
        TelegramError,
        LayoutError,
    ) as error:
        await message.reply_text(
            user_error(error), reply_markup=menu_keyboard()
        )
        if not isinstance(error, ValidationError):
            context.user_data.clear()

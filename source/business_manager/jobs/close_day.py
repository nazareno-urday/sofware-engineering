import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from google.auth.exceptions import GoogleAuthError
from requests.exceptions import RequestException
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from business_manager.config import ARGENTINA
from business_manager.services.day_closure import ClosureError
from business_manager.services.reports import summary_text
from business_manager.services.sheets import SheetConflict

logger = logging.getLogger(__name__)


async def deliver_pending(application: Any) -> None:
    async with application.bot_data["notification_lock"]:
        closure = application.bot_data["closure"]
        pending = await asyncio.to_thread(
            closure.pending_notifications
        )
        for day in pending:
            try:
                await application.bot.send_message(
                    chat_id=day["chat_id"],
                    text=summary_text(
                        day["date"], day["results"]
                    ),
                )
            except TelegramError as error:
                logger.warning(
                    "Notification remains pending: %s",
                    type(error).__name__,
                )
                continue
            await asyncio.to_thread(
                closure.mark_notified, day["date"]
            )


async def scheduled_close(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    application = context.application
    closure = application.bot_data["closure"]
    day = await asyncio.to_thread(closure.active_day)
    if day:
        today = datetime.now(ARGENTINA).date()
        config = application.bot_data["config"]
        expected = today
        if (
            config.closing_time.hour == 0
            and config.closing_time.minute == 0
        ):
            expected = today - timedelta(days=1)
        if day["date"] == expected.isoformat():
            try:
                await asyncio.to_thread(closure.close)
            except (
                ClosureError,
                SheetConflict,
                ValueError,
                OSError,
                RequestException,
                GoogleAuthError,
            ) as error:
                logger.warning(
                    "Closure requires recovery: %s",
                    type(error).__name__,
                )
                await send_recovery_notice(
                    application, day, error
                )
        elif day["date"] < today.isoformat():
            await send_recovery_notice(application, day)
    await deliver_pending(application)


async def send_recovery_notice(
    application: Any,
    day: dict[str, Any],
    error: Exception | None = None,
) -> None:
    from business_manager.bot.handlers import (
        menu_keyboard,
        user_error,
    )

    text = (
        f"La jornada {day['date']} sigue pendiente. "
        "No cargues movimientos nuevos. Revisá las hojas "
        "y usá Cerrar día para continuar. Si el cierre "
        "se interrumpió al limpiar, seguí los pasos "
        "de recuperación del README."
    )
    if error:
        text += "\n" + user_error(error)
    try:
        await application.bot.send_message(
            chat_id=day["chat_id"],
            text=text,
            reply_markup=menu_keyboard(),
        )
    except TelegramError as notification_error:
        logger.warning(
            "Recovery notice failed: %s",
            type(notification_error).__name__,
        )
        return
    application.bot_data["recovery_notice"] = (
        day["date"],
        day["phase"],
    )


async def startup_recovery(application: Any) -> None:
    closure = application.bot_data["closure"]
    day = await asyncio.to_thread(closure.active_day)
    if day and (
        day["date"] < datetime.now(ARGENTINA).date().isoformat()
        or day["phase"] != "active"
    ):
        await send_recovery_notice(application, day)
    await deliver_pending(application)


async def retry_notifications(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    application = context.application
    closure = application.bot_data["closure"]
    day = await asyncio.to_thread(closure.active_day)
    if day:
        today = datetime.now(ARGENTINA).date().isoformat()
        overdue = day["date"] < today
        interrupted = day["phase"] != "active"
        notice = (day["date"], day["phase"])
        already_sent = (
            application.bot_data.get("recovery_notice") == notice
        )
        if (overdue or interrupted) and not already_sent:
            await send_recovery_notice(application, day)
    await deliver_pending(application)

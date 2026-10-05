import asyncio
import logging

from filelock import FileLock, Timeout
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    filters,
)

from business_manager.bot.handlers import handle_message
from business_manager.config import Config, load_config
from business_manager.jobs.close_day import (
    retry_notifications,
    scheduled_close,
    startup_recovery,
)
from business_manager.services.day_closure import DayClosure
from business_manager.services.sheets import SheetsClient


async def handle_error(
    update: object, context: ContextTypes.DEFAULT_TYPE
) -> None:
    logging.getLogger(__name__).error(
        "Unhandled operation failure: %s",
        type(context.error).__name__,
    )
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "La operación se interrumpió. Revisá la configuración "
                "y el estado antes de reintentar."
            )
        except TelegramError as error:
            logging.getLogger(__name__).warning(
                "Error notice failed: %s", type(error).__name__
            )


def build_application(
    config: Config, closure: DayClosure, sheets: SheetsClient
) -> Application:
    application = (
        Application.builder()
        .token(config.token)
        .post_init(startup_recovery)
        .build()
    )
    application.bot_data.update(
        config=config,
        closure=closure,
        sheets=sheets,
        notification_lock=asyncio.Lock(),
    )
    application.add_handler(
        MessageHandler(filters.ALL, handle_message)
    )
    application.add_error_handler(handle_error)
    if application.job_queue is None:
        raise RuntimeError(
            "Install python-telegram-bot[job-queue]"
        )
    application.job_queue.run_daily(
        scheduled_close,
        config.closing_time,
        name="close-day",
        job_kwargs={"misfire_grace_time": 1},
    )
    application.job_queue.run_repeating(
        retry_notifications,
        interval=60,
        first=60,
        name="retry-notifications",
    )
    return application


def main() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.CRITICAL)
    logging.getLogger("telegram").setLevel(logging.CRITICAL)
    config = load_config()
    config.state_dir.mkdir(parents=True, exist_ok=True)
    try:
        with FileLock(
            str(config.state_dir / "process.lock"), timeout=0
        ):
            sheets = SheetsClient(
                config.sheet_id, config.credentials_file
            )
            closure = DayClosure(
                sheets, config.state_dir, config.sheet_id
            )
            application = build_application(
                config, closure, sheets
            )
            application.run_polling()
    except Timeout as error:
        raise RuntimeError(
            "Another service process is using this state directory"
        ) from error


if __name__ == "__main__":
    main()

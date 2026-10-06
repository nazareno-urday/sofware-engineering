import asyncio
from datetime import datetime, time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from business_manager.bot.handlers import (
    MENU_ROWS,
    handle_message,
)
from business_manager.config import ARGENTINA, Config
from business_manager.jobs import close_day
from business_manager.main import build_application
from test_day_closure import started


@pytest.fixture
def conversation():
    config = SimpleNamespace(
        allowed_user_ids=frozenset({200}),
        sheet_url="https://example.com/sheet",
        closing_time=time(0, tzinfo=ARGENTINA),
    )
    closure = Mock()
    closure.active_day.return_value = {
        "date": "2026-10-05",
        "chat_id": 100,
        "user_id": 200,
        "phase": "active",
    }
    closure.start.return_value = closure.active_day.return_value
    closure.preview.return_value = {
        "income_mp": 9000,
        "income_cash": 9000,
        "gross_income": 18000,
        "expense_mp": 2000,
        "expense_cash": 900,
        "total_expenses": 2900,
        "net_mp": 7000,
        "net_cash": 8100,
        "net_total": 15100,
        "sale_count": 2,
    }
    closure.pending_notifications.return_value = []
    sheets = Mock()
    sheets.read_archive.return_value = [
        ["05/10/2026", "Café", "", 20]
    ]
    application = SimpleNamespace(
        bot_data={
            "config": config,
            "closure": closure,
            "sheets": sheets,
            "notification_lock": asyncio.Lock(),
        },
        bot=SimpleNamespace(send_message=AsyncMock()),
    )
    context = SimpleNamespace(
        application=application,
        user_data={},
        bot=SimpleNamespace(username="testbot"),
    )
    message = SimpleNamespace(
        text=None,
        reply_text=AsyncMock(),
        reply_document=AsyncMock(),
    )
    update = SimpleNamespace(
        effective_message=message,
        effective_chat=SimpleNamespace(id=100, type="private"),
        effective_user=SimpleNamespace(id=200),
    )
    return update, context, closure, sheets


def send(conversation, text):
    update, context, _, _ = conversation
    update.effective_message.text = text
    asyncio.run(handle_message(update, context))
    return update.effective_message


@pytest.mark.parametrize(
    "text", ["hola", "unknown sale 100", None, "/help"]
)
def test_unknown_and_nontext_show_menu_without_business_actions(
    conversation, text
):
    message = send(conversation, text)
    _, _, closure, sheets = conversation
    keyboard = message.reply_text.call_args.kwargs[
        "reply_markup"
    ]
    assert [
        [button.text for button in row]
        for row in keyboard.keyboard
    ] == MENU_ROWS
    assert closure.mock_calls == []
    assert sheets.mock_calls == []
    assert message.reply_text.call_count == 1


def test_authorization_and_private_chat_are_required(
    conversation,
):
    update, _, closure, sheets = conversation
    update.effective_user.id = 999
    send(conversation, "Cerrar día")
    update.effective_user.id = 200
    update.effective_chat.type = "group"
    send(conversation, "Ver resumen")
    assert closure.mock_calls == sheets.mock_calls == []
    update.effective_message.text = "/id"
    send(conversation, "/id")
    assert (
        "200"
        in update.effective_message.reply_text.call_args.args[0]
    )


def test_start_and_preview_route_without_archiving(conversation):
    send(conversation, "Comenzar el día")
    send(conversation, "Ver resumen")
    _, _, closure, sheets = conversation
    assert closure.start.call_args.args[1:] == (100, 200)
    closure.preview.assert_called_once()
    closure.close.assert_not_called()
    sheets.write.assert_not_called()


@pytest.mark.parametrize(
    "button,kind",
    [
        ("Imprimir historial", "history"),
        ("Imprimir ventas", "sales"),
        ("Imprimir egresos", "expenses"),
    ],
)
def test_report_buttons_only_read_and_send_pdf(
    conversation, button, kind
):
    _, _, closure, sheets = conversation
    if kind == "history":
        sheets.read_archive.return_value = [
            ["05/10/2026", 20, 0, 20, 0]
        ]
    send(conversation, button)
    send(conversation, "Elegir fechas")
    message = send(conversation, "05/10/2026 - 05/10/2026")
    sheets.read_archive.assert_called_once_with(kind)
    document = message.reply_document.call_args.kwargs[
        "document"
    ]
    assert document.getvalue().startswith(b"%PDF-")
    closure.close.assert_not_called()
    closure.start.assert_not_called()
    sheets.write.assert_not_called()


def test_invalid_period_does_not_close_and_can_be_corrected(
    conversation,
):
    send(conversation, "Imprimir ventas")
    send(conversation, "Elegir fechas")
    send(conversation, "06/10/2026 - 05/10/2026")
    _, context, closure, sheets = conversation
    assert context.user_data["flow"]["awaiting_dates"]
    closure.close.assert_not_called()
    sheets.read_archive.assert_not_called()
    message = send(conversation, "05/10/2026 - 05/10/2026")
    message.reply_document.assert_called_once()


def test_close_needs_button_and_uses_shared_orchestrator(
    conversation,
):
    send(conversation, "Cerrar día")
    _, _, closure, _ = conversation
    closure.close.assert_not_called()
    send(conversation, "Confirmar cierre")
    closure.close.assert_called_once_with(100, 200)


def test_back_and_nontext_cancel_date_flow(conversation):
    send(conversation, "Imprimir ventas")
    send(conversation, "Elegir fechas")
    send(conversation, None)
    _, context, closure, sheets = conversation
    assert context.user_data == {}
    send(conversation, "05/10/2026 - 05/10/2026")
    sheets.read_archive.assert_not_called()
    closure.close.assert_not_called()
    send(conversation, "Recuperación")
    send(conversation, "Volver")
    assert context.user_data == {}


def test_build_only_registers_handlers_and_argentine_scheduler(
    tmp_path,
):
    config = Config(
        "123456:placeholder",
        "test",
        Path("unused"),
        tmp_path,
        frozenset({200}),
        time(0, tzinfo=ARGENTINA),
    )
    sheets, closure = Mock(), Mock()
    app = build_application(config, closure, sheets)
    assert len(app.handlers[0]) == 1
    assert app.post_init is close_day.startup_recovery
    jobs = app.job_queue.get_jobs_by_name("close-day")
    assert len(jobs) == 1
    assert str(jobs[0].job.trigger.timezone) == str(ARGENTINA)
    assert sheets.mock_calls == closure.mock_calls == []


def freeze_time(monkeypatch, day):
    class FrozenDatetime:
        @staticmethod
        def now(zone):
            assert zone == ARGENTINA
            return datetime(2026, 10, day, tzinfo=ARGENTINA)

    monkeypatch.setattr(close_day, "datetime", FrozenDatetime)


def app_for(closure):
    return SimpleNamespace(
        bot_data={
            "closure": closure,
            "notification_lock": asyncio.Lock(),
            "config": SimpleNamespace(
                closing_time=time(0, tzinfo=ARGENTINA)
            ),
        },
        bot=SimpleNamespace(send_message=AsyncMock()),
    )


def test_midnight_of_sixth_archives_fifth(monkeypatch, tmp_path):
    closure, sheets = started(tmp_path)
    freeze_time(monkeypatch, 6)
    app = app_for(closure)
    asyncio.run(
        close_day.scheduled_close(
            SimpleNamespace(application=app)
        )
    )
    assert sheets.archives["history"][0][0] == "05/10/2026"
    assert (
        app.bot.send_message.call_args.kwargs["chat_id"] == 100
    )
    assert closure.pending_notifications() == []


@pytest.mark.parametrize(
    "day,expect_notice", [(5, False), (6, True)]
)
def test_startup_does_not_close_current_or_overdue_day(
    monkeypatch, tmp_path, day, expect_notice
):
    closure, sheets = started(tmp_path)
    freeze_time(monkeypatch, day)
    app = app_for(closure)
    asyncio.run(close_day.startup_recovery(app))
    assert sheets.writes == sheets.clears == []
    assert app.bot.send_message.called == expect_notice
    assert closure.active_day()["date"] == "2026-10-05"


def test_overdue_scheduler_requests_review_without_guessing(
    monkeypatch, tmp_path
):
    closure, sheets = started(tmp_path)
    freeze_time(monkeypatch, 7)
    app = app_for(closure)
    asyncio.run(
        close_day.scheduled_close(
            SimpleNamespace(application=app)
        )
    )
    assert sheets.writes == sheets.clears == []
    assert (
        app.bot.send_message.call_args.kwargs["chat_id"] == 100
    )


def test_no_active_day_scheduler_preserves_orphan_rows(
    monkeypatch, tmp_path
):
    closure, sheets = started(tmp_path)
    closure.close()
    closure.mark_notified("2026-10-05")
    sheets.daily["Ingresos"] = [["orphan", 7]]
    writes = len(sheets.writes)
    freeze_time(monkeypatch, 7)
    app = app_for(closure)
    asyncio.run(
        close_day.scheduled_close(
            SimpleNamespace(application=app)
        )
    )
    assert len(sheets.writes) == writes
    assert len(sheets.clears) == 1
    assert sheets.daily["Ingresos"] == [["orphan", 7]]


def test_wake_after_missed_midnight_warns_once_without_closing(
    monkeypatch, tmp_path
):
    closure, sheets = started(tmp_path)
    freeze_time(monkeypatch, 6)
    app = app_for(closure)
    context = SimpleNamespace(application=app)
    asyncio.run(close_day.retry_notifications(context))
    asyncio.run(close_day.retry_notifications(context))
    assert app.bot.send_message.call_count == 1
    assert sheets.writes == sheets.clears == []

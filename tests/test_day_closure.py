import asyncio
import re
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from business_manager.jobs.close_day import deliver_pending
from business_manager.services.calculations import (
    ValidationError,
    normalize_rows,
)
from business_manager.services.day_closure import (
    ClosureError,
    DayClosure,
)
from business_manager.services.sheets import (
    ARCHIVE_RANGES,
    SheetConflict,
    SheetsClient,
)
from telegram.error import TelegramError


class FakeSheets(SheetsClient):
    def __init__(self):
        super().__init__("test", Path("unused.json"))
        self.daily = {
            "Ingresos": [
                ["laureano", 1000, 2000],
                ["comida", 8000, 7000],
            ],
            "Egresos": [["coca", 2000, 900]],
        }
        self.archives = {
            "history": [],
            "sales": [],
            "expenses": [],
        }
        self.writes = []
        self.clears = []
        self.fail_kind = None
        self.lost_write = False
        self.lost_clear = False
        self.after_write = None

    def check_layout(self):
        pass

    def ensure_rows(self, cell_range):
        pass

    def read_daily(self):
        return {
            key: normalize_rows(deepcopy(rows))
            for key, rows in self.daily.items()
        }

    def read_archive(self, kind):
        return deepcopy(self.archives[kind])

    def locate(self, cell_range):
        for kind, archive_range in ARCHIVE_RANGES.items():
            prefix = archive_range.split("!")[0]
            first = archive_range.split("!")[1][0]
            if cell_range.startswith(prefix + "!" + first):
                numbers = re.findall(r"\d+", cell_range)
                return (
                    kind,
                    int(numbers[0]) - 2,
                    int(numbers[1]) - 1,
                )
        raise AssertionError(cell_range)

    def read(self, cell_range):
        if cell_range.startswith(("Ingresos!", "Egresos!")):
            sheet = cell_range.split("!")[0]
            number = int(re.findall(r"\d+", cell_range)[0]) - 2
            return deepcopy(
                self.daily[sheet][number : number + 1]
            )
        kind, start, end = self.locate(cell_range)
        return deepcopy(self.archives[kind][start:end])

    def write(self, cell_range, rows):
        kind, start, end = self.locate(cell_range)
        if self.fail_kind == kind:
            raise OSError("Simulated archive outage")
        archive = self.archives[kind]
        while len(archive) < end:
            archive.append([])
        archive[start:end] = deepcopy(rows)
        self.writes.append(cell_range)
        if self.after_write:
            self.after_write(self)
        if self.lost_write:
            self.lost_write = False
            raise TimeoutError("Simulated lost write response")

    def clear_rows(self, ranges):
        self.clears.append(deepcopy(ranges))
        for cell_range in ranges:
            sheet = cell_range.split("!")[0]
            number = int(re.findall(r"\d+", cell_range)[0]) - 2
            self.daily[sheet][number] = []
        if self.lost_clear:
            self.lost_clear = False
            raise TimeoutError("Simulated lost clear response")


def started(tmp_path, sheets=None):
    sheets = sheets or FakeSheets()
    closure = DayClosure(sheets, tmp_path, "test")
    closure.start(date(2026, 10, 5), 100, 200)
    return closure, sheets


def test_start_persists_owner_and_is_idempotent(tmp_path):
    closure, sheets = started(tmp_path)
    day = closure.start(date(2026, 10, 6), 100, 200)
    assert day["date"] == "2026-10-05"
    with pytest.raises(ClosureError, match="another"):
        closure.start(date(2026, 10, 5), 101, 201)
    restarted = DayClosure(sheets, tmp_path, "test")
    assert restarted.active_day()["chat_id"] == 100
    assert sheets.writes == sheets.clears == []


def test_close_archives_both_blocks_with_business_date(tmp_path):
    closure, sheets = started(tmp_path)
    day = closure.close(100, 200)
    assert day["phase"] == "closed"
    assert sheets.archives["sales"] == [
        ["05/10/2026", "laureano", 1000, 2000],
        ["05/10/2026", "comida", 8000, 7000],
    ]
    assert sheets.archives["expenses"] == [
        ["05/10/2026", "coca", 2000, 900]
    ]
    assert sheets.archives["history"] == [
        ["05/10/2026", 18000, 9000, 9000, 2900]
    ]
    assert sheets.read_daily() == {"Ingresos": [], "Egresos": []}
    assert sheets.clears == [
        ["Ingresos!A2:C2", "Ingresos!A3:C3", "Egresos!A2:C2"]
    ]
    assert closure.pending_notifications()[0]["chat_id"] == 100
    with pytest.raises(ClosureError, match="No active"):
        closure.close()
    with pytest.raises(ClosureError, match="already closed"):
        closure.start(date(2026, 10, 5), 100, 200)
    closure.start(date(2026, 10, 6), 100, 200)
    assert len(sheets.archives["history"]) == 1


def test_blocks_have_independent_next_rows_and_preserve_history(
    tmp_path,
):
    sheets = FakeSheets()
    sheets.archives["sales"] = [["old", "sale", 1, 2]] * 501
    sheets.archives["expenses"] = [["old", "cost", 3, 4]]
    sheets.archives["history"] = [["04/10/2026", 1, 1, 0, 0]]
    closure, sheets = started(tmp_path, sheets)
    day = closure.close()
    assert day["destinations"]["sales"].endswith("A503:D504")
    assert day["destinations"]["expenses"].endswith("F3:I3")
    assert len(sheets.archives["sales"]) == 503
    assert sheets.archives["history"][0][0] == "04/10/2026"
    assert len(sheets.archives["history"]) == 2


def test_invalid_input_prevents_all_writes_and_clear(tmp_path):
    closure, sheets = started(tmp_path)
    sheets.daily["Egresos"] = [["coca", "invalid", 900]]
    with pytest.raises(ValidationError, match="Egresos!B2"):
        closure.close()
    assert sheets.writes == sheets.clears == []
    assert closure.active_day()["phase"] == "active"


@pytest.mark.parametrize("lost_response", [False, True])
def test_partial_archive_restart_never_duplicates(
    tmp_path, lost_response
):
    closure, sheets = started(tmp_path)
    if lost_response:
        sheets.lost_write = True
    else:
        sheets.fail_kind = "expenses"
    with pytest.raises((OSError, TimeoutError)):
        closure.close()
    assert sheets.clears == []
    assert len(sheets.archives["sales"]) == 2
    sheets.fail_kind = None
    restarted = DayClosure(sheets, tmp_path, "test")
    restarted.close()
    assert len(sheets.archives["sales"]) == 2
    assert len(sheets.archives["expenses"]) == 1
    assert len(sheets.archives["history"]) == 1
    assert len(sheets.writes) == 3
    assert len(sheets.clears) == 1


def test_snapshot_edit_stops_cleanup_and_keeps_new_sale(
    tmp_path,
):
    closure, sheets = started(tmp_path)

    def edit(sheets):
        sheets.daily["Ingresos"].append(["new", "", 50])
        sheets.after_write = None

    sheets.after_write = edit
    with pytest.raises(ClosureError, match="changed"):
        closure.close()
    assert sheets.clears == []
    assert sheets.daily["Ingresos"][-1] == ["new", "", 50]
    assert closure.active_day()["phase"] == "archived"


def test_lost_clear_requires_review_and_never_repeats_clear(
    tmp_path,
):
    closure, sheets = started(tmp_path)
    sheets.lost_clear = True
    with pytest.raises(TimeoutError):
        closure.close()
    restarted = DayClosure(sheets, tmp_path, "test")
    with pytest.raises(ClosureError, match="Ambiguous"):
        restarted.close()
    restarted.confirm_reviewed_cleanup(100, 200)
    assert len(sheets.clears) == 1
    assert len(sheets.archives["history"]) == 1


def test_review_rejects_new_data_in_archived_rows(tmp_path):
    closure, sheets = started(tmp_path)
    sheets.lost_clear = True
    with pytest.raises(TimeoutError):
        closure.close()
    sheets.daily["Ingresos"][0] = ["new", 5]
    with pytest.raises(ClosureError, match="not confirmed"):
        closure.confirm_reviewed_cleanup(100, 200)
    assert sheets.daily["Ingresos"][0] == ["new", 5]
    assert len(sheets.clears) == 1


def test_concurrent_closures_only_archive_once(tmp_path):
    closure, sheets = started(tmp_path)

    def close():
        try:
            return closure.close()["phase"]
        except ClosureError:
            return "already closed"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: close(), range(2)))
    assert sorted(results) == ["already closed", "closed"]
    assert len(sheets.archives["history"]) == 1
    assert len(sheets.clears) == 1


def test_notification_retry_does_not_archive_again(tmp_path):
    closure, sheets = started(tmp_path)
    closure.close()
    app = SimpleNamespace(
        bot=SimpleNamespace(
            send_message=AsyncMock(
                side_effect=[TelegramError("offline"), None]
            )
        ),
        bot_data={
            "closure": closure,
            "notification_lock": asyncio.Lock(),
        },
    )
    asyncio.run(deliver_pending(app))
    assert len(closure.pending_notifications()) == 1
    asyncio.run(deliver_pending(app))
    assert closure.pending_notifications() == []
    assert len(sheets.writes) == 3
    assert len(sheets.clears) == 1


def test_permanent_conflict_stops_clear(tmp_path):
    closure, sheets = started(tmp_path)
    sheets.fail_kind = "expenses"
    with pytest.raises(OSError):
        closure.close()
    sheets.fail_kind = None
    sheets.archives["sales"][0][1] = "human edit"
    with pytest.raises(SheetConflict, match="conflict"):
        closure.close()
    assert sheets.clears == []


def test_existing_history_date_blocks_duplicate_day(tmp_path):
    closure, sheets = started(tmp_path)
    sheets.archives["history"] = [["05/10/2026", 1, 1, 0, 0]]
    with pytest.raises(SheetConflict, match="already"):
        closure.close()
    assert sheets.clears == sheets.writes == []


def test_empty_day_and_preview_have_expected_effects(tmp_path):
    closure, sheets = started(tmp_path)
    before = deepcopy(sheets.daily)
    assert closure.preview()["net_total"] == 15100
    assert sheets.daily == before
    assert sheets.writes == sheets.clears == []
    sheets.daily = {"Ingresos": [], "Egresos": []}
    closure.close()
    assert sheets.archives["sales"] == []
    assert sheets.archives["expenses"] == []
    assert sheets.archives["history"] == [
        ["05/10/2026", 0, 0, 0, 0]
    ]


def test_journal_corruption_and_wrong_sheet_fail_closed(
    tmp_path,
):
    closure, sheets = started(tmp_path)
    with pytest.raises(ClosureError, match="mismatch"):
        DayClosure(sheets, tmp_path, "other")
    closure.path.write_text("broken", encoding="utf-8")
    with pytest.raises(ValueError):
        DayClosure(sheets, tmp_path, "test")
    assert sheets.clears == sheets.writes == []


def test_other_owner_cannot_close_or_confirm_cleanup(tmp_path):
    closure, sheets = started(tmp_path)
    with pytest.raises(ClosureError, match="another"):
        closure.close(101, 201)
    assert sheets.writes == sheets.clears == []
    sheets.lost_clear = True
    with pytest.raises(TimeoutError):
        closure.close()
    with pytest.raises(ClosureError, match="another"):
        closure.confirm_reviewed_cleanup(101, 201)
    assert closure.active_day()["phase"] == "clearing"
    assert len(sheets.clears) == 1

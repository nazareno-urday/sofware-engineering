import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from datetime import date
from pathlib import Path
from threading import RLock
from typing import Any

from business_manager.services.calculations import (
    calculate_day,
    validate_movements,
)
from business_manager.services.sheets import SheetConflict


class ClosureError(RuntimeError):
    pass


class DayClosure:
    def __init__(
        self, sheets: Any, state_dir: Path, sheet_id: str
    ) -> None:
        self.sheets = sheets
        self.state_dir = state_dir
        self.sheet_id = sheet_id
        self.path = state_dir / "journal.json"
        self.lock = RLock()
        self.state: dict[str, Any] = {}
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with self._operation():
            pass

    @contextmanager
    def _operation(self) -> Iterator[None]:
        with self.lock, self.sheets.lock:
            if self.path.exists():
                self.state = json.loads(
                    self.path.read_text(encoding="utf-8")
                )
                if (
                    self.state.get("version") != 1
                    or self.state.get("sheet_id")
                    != self.sheet_id
                ):
                    raise ClosureError(
                        "Journal configuration mismatch"
                    )
            else:
                self.state = {
                    "version": 1,
                    "sheet_id": self.sheet_id,
                    "active": None,
                    "days": {},
                }
            yield

    def _save(self) -> None:
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(
                self.state,
                stream,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
            )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)

    def active_day(self) -> dict[str, Any] | None:
        with self._operation():
            key = self.state["active"]
            if not key:
                return None
            day: dict[str, Any] = self.state["days"][key]
            return deepcopy(day)

    def start(
        self, business_date: date, chat_id: int, user_id: int
    ) -> dict[str, Any]:
        with self._operation():
            key = self.state["active"]
            if key:
                day = self.state["days"][key]
                self._check_owner(day, chat_id, user_id)
                return deepcopy(day)
            key = business_date.isoformat()
            if key in self.state["days"]:
                raise ClosureError(
                    "This business date is already closed"
                )
            self.sheets.check_layout()
            day = {
                "date": key,
                "chat_id": chat_id,
                "user_id": user_id,
                "phase": "active",
                "notification_pending": False,
            }
            self.state["days"][key] = day
            self.state["active"] = key
            self._save()
            return deepcopy(day)

    def _check_owner(
        self, day: dict[str, Any], chat_id: int, user_id: int
    ) -> None:
        if (
            day["chat_id"] != chat_id
            or day["user_id"] != user_id
        ):
            raise ClosureError(
                "The active day belongs to another authorized user"
            )

    def preview(self) -> dict[str, float]:
        with self._operation():
            snapshot = self.sheets.read_daily()
            return calculate_day(
                snapshot["Ingresos"], snapshot["Egresos"]
            )

    def close(
        self,
        chat_id: int | None = None,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        with self._operation():
            key = self.state["active"]
            if not key:
                raise ClosureError(
                    "No active day; nothing was changed"
                )
            day = self.state["days"][key]
            if chat_id is not None and user_id is not None:
                self._check_owner(day, chat_id, user_id)
            if day["phase"] == "clearing":
                raise ClosureError(
                    "Ambiguous clear: review journal and daily rows, "
                    "then confirm reviewed cleanup"
                )
            self.sheets.check_layout()
            if day["phase"] == "active":
                self._prepare_day(day)
            self._verify_archive(day)
            day["phase"] = "archived"
            self._save()
            if self.sheets.read_daily() != day["snapshot"]:
                raise ClosureError(
                    "Daily rows changed after snapshot; no cleanup. "
                    "Restore snapshot before retrying"
                )
            day["phase"] = "clearing"
            self._save()
            self.sheets.clear_rows(day["clear_ranges"])
            self._verify_empty(day)
            return self._finish(day)

    def _prepare_day(self, day: dict[str, Any]) -> None:
        snapshot = self.sheets.read_daily()
        results = calculate_day(
            snapshot["Ingresos"], snapshot["Egresos"]
        )
        business_date = day["date"]
        label = date.fromisoformat(business_date).strftime(
            "%d/%m/%Y"
        )
        for row in self.sheets.read_archive("history"):
            if row and str(row[0]) in {label, business_date}:
                raise SheetConflict(
                    "History already contains this business date"
                )
        payloads = {}
        for kind, sheet in (
            ("sales", "Ingresos"),
            ("expenses", "Egresos"),
        ):
            movements = validate_movements(
                snapshot[sheet], sheet
            )
            dated_rows = []
            for row in movements:
                dated_rows.append([label] + row)
            payloads[kind] = dated_rows
        payloads["history"] = [
            [
                label,
                results["gross_income"],
                results["income_mp"],
                results["income_cash"],
                results["total_expenses"],
            ]
        ]
        destinations = {}
        for kind, rows in payloads.items():
            if rows:
                destinations[kind] = self.sheets.reserve_range(
                    kind, len(rows)
                )
        clear_ranges = []
        for sheet, rows in snapshot.items():
            for number, row in enumerate(rows, 2):
                if any(cell != "" for cell in row):
                    clear_ranges.append(
                        f"{sheet}!A{number}:C{number}"
                    )
        day.update(
            snapshot=snapshot,
            results=results,
            payloads=payloads,
            destinations=destinations,
            clear_ranges=clear_ranges,
            phase="prepared",
        )
        self._save()

    def _verify_archive(self, day: dict[str, Any]) -> None:
        for kind, destination in day["destinations"].items():
            self.sheets.write_verified(
                destination, day["payloads"][kind]
            )

    def _verify_empty(self, day: dict[str, Any]) -> None:
        current = self.sheets.read_daily()
        for sheet, rows in day["snapshot"].items():
            for index, row in enumerate(rows):
                if not any(cell != "" for cell in row):
                    continue
                existing = []
                if index < len(current[sheet]):
                    existing = current[sheet][index]
                if any(cell != "" for cell in existing):
                    raise ClosureError(
                        f"Cleanup not confirmed: {sheet}!A{index + 2}:C{index + 2}"
                    )

    def _finish(self, day: dict[str, Any]) -> dict[str, Any]:
        day["phase"] = "closed"
        day["notification_pending"] = True
        self.state["active"] = None
        self._save()
        return deepcopy(day)

    def confirm_reviewed_cleanup(
        self, chat_id: int, user_id: int
    ) -> dict[str, Any]:
        with self._operation():
            key = self.state["active"]
            if not key:
                raise ClosureError("No active day")
            day = self.state["days"][key]
            self._check_owner(day, chat_id, user_id)
            if day["phase"] != "clearing":
                raise ClosureError(
                    "No ambiguous cleanup to confirm"
                )
            self.sheets.check_layout()
            self._verify_archive(day)
            self._verify_empty(day)
            return self._finish(day)

    def pending_notifications(self) -> list[dict[str, Any]]:
        with self._operation():
            pending = []
            for day in self.state["days"].values():
                if day["notification_pending"]:
                    pending.append(deepcopy(day))
            return pending

    def mark_notified(self, business_date: str) -> None:
        with self._operation():
            self.state["days"][business_date][
                "notification_pending"
            ] = False
            self._save()

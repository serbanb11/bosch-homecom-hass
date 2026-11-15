"""Tests for importing the energy recordings into long-term statistics.

The fixture holds a K30's real answers (Buderus heat pump, no hot-water tank)
fetched on 9 November 2026 around 00:30 in Europe/Rome: hourly buckets back to
30 October, daily ones from 2 September and monthly ones from 2025.
"""

from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.recorder import Recorder
from homeassistant.components.recorder.statistics import get_last_statistics
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homecom_alt import ApiError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.bosch_homecom import async_remove_entry
from custom_components.bosch_homecom.const import CONF_DEVICES, CONF_REFRESH, DOMAIN
from custom_components.bosch_homecom.coordinator import BoschComModuleCoordinatorK40
from custom_components.bosch_homecom.statistics import (
    ENERGY_RECORDINGS,
    async_import_energy,
    bucket_values,
    build_rows,
    recording_path,
)

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "k30_energy_recordings.json").read_text()
)
DEVICE = "101756851"
TOTAL = f"bosch_homecom:{DEVICE}_heat_produced_total"
CH = f"bosch_homecom:{DEVICE}_heat_produced_ch"
DHW = f"bosch_homecom:{DEVICE}_heat_produced_dhw"
DAY = date(2026, 11, 8)


@pytest.fixture
def mock_recorder_before_hass(async_test_recorder) -> None:
    """Prepare the recorder database before hass, which ``recorder_mock`` needs.

    The autouse ``enable_custom_integrations`` would set hass up first.
    """


@pytest.fixture
async def rome(hass: HomeAssistant) -> None:
    """Run in the fixture's time zone, so buckets land on the right days."""
    await hass.config.async_set_time_zone("Europe/Rome")


def _local(*args: int) -> datetime:
    return datetime(*args, tzinfo=dt_util.get_default_time_zone())


def _day_result(day: date, recordings: dict | None = None) -> dict:
    """Return the coordinator's bulk answer for ``day``."""
    source = recordings if recordings is not None else FIXTURE
    paths = [recording_path(s, day.isoformat()) for s in ENERGY_RECORDINGS]
    return {p: source[p] for p in paths if p in source}


def _bhc(requested: list[list[str]]) -> MagicMock:
    async def bulk(device_id: str, paths: list[str]) -> dict:
        requested.append(list(paths))
        return {p: FIXTURE[p] for p in paths if p in FIXTURE}

    bhc = MagicMock()
    bhc.async_request_bulk = AsyncMock(side_effect=bulk)
    return bhc


def _counters(paths: list[str]) -> set[str]:
    """Return the emon counters, e.g. ``total``, that ``paths`` ask for."""
    return {path.split("/emon/")[1].split("/")[0] for path in paths}


def _coordinator(
    hass: HomeAssistant, bhc: MagicMock, entry: MockConfigEntry | None = None
) -> BoschComModuleCoordinatorK40:
    if entry is None:
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_DEVICES: {f"{DEVICE}_k30": True},
                CONF_REFRESH: "r",
                "token": "t",
            },
        )
        entry.add_to_hass(hass)
    return BoschComModuleCoordinatorK40(
        hass,
        bhc,
        {"deviceId": DEVICE, "deviceType": "k30"},
        {"value": "15.00.01"},
        entry,
        auth_provider=False,
    )


def _hourly(*values: float) -> dict:
    """Return an hourly recording whose first buckets hold ``values``."""
    buckets = [{"c": 1, "y": v} for v in values]
    buckets += [{"c": 0, "y": 1.0}] * (24 - len(values))
    return {"recording": buckets, "sampleRate": "P1H", "unitOfMeasure": "kWh"}


async def _last(recorder: Recorder, hass: HomeAssistant, statistic_id: str):
    stats = await recorder.async_add_executor_job(
        get_last_statistics, hass, 1, statistic_id, True, {"sum"}
    )
    return stats.get(statistic_id, [None])[0]


def test_bucket_values_skip_unpopulated_buckets():
    """A ``c: 0`` bucket is no reading, whatever its placeholder ``y``."""
    payload = {"recording": [{"c": 1, "y": 2.0}, {"c": 0, "y": 1.0}, {"c": 1}]}
    assert bucket_values(payload) == [2.0, None, None]
    assert bucket_values(None) == []


async def test_build_rows_merges_resolutions_without_overlap(hass, rome):
    """Each period comes once, from the finest resolution that covers it."""
    suffix = "emon/total/outputProduced"
    hourly, daily, monthly = {}, {}, {}
    for path, payload in FIXTURE.items():
        if f"/{suffix}?" not in path:
            continue
        interval = path.rsplit("=", 1)[1]
        values = bucket_values(payload)
        if len(interval) == 10:
            hourly[date.fromisoformat(interval)] = values
        elif len(interval) == 7:
            daily[date.fromisoformat(f"{interval}-01")] = values
        else:
            monthly[int(interval)] = values

    rows = build_rows(hourly, daily, monthly, _local(2026, 11, 9, 0, 30))
    starts = [start for start, _ in rows]

    assert len(starts) == len(set(starts)) == 20 + 58 + 240
    assert sum(value for _, value in rows) == 29103 + 224 + 695
    # Monthly rows end with August, daily ones begin on 2 September (1 September
    # has no bucket) and hourly ones on 30 October, where hourly data starts.
    assert starts[0] == dt_util.as_utc(_local(2025, 1, 1))
    assert starts[19] == dt_util.as_utc(_local(2026, 8, 1))
    assert starts[20] == dt_util.as_utc(_local(2026, 9, 2))
    assert starts[77] == dt_util.as_utc(_local(2026, 10, 29))
    assert starts[78] == dt_util.as_utc(_local(2026, 10, 30))
    assert starts[-1] == dt_util.as_utc(_local(2026, 11, 8, 23))


async def test_build_rows_skip_periods_still_running(hass, rome):
    """The current hour, day and month are left for a later import."""
    rows = build_rows(
        {date(2026, 11, 9): [1.0, 2.0, 3.0]},
        {date(2026, 11, 1): [5.0] * 9},
        {2026: [None] * 10 + [7.0]},
        _local(2026, 11, 9, 2, 30),
    )
    # 9 November is covered by hours, so daily rows stop on the 8th; the 02:00
    # hour and November as a month are still running.
    assert [value for _, value in rows] == [5.0] * 8 + [1.0, 2.0]
    assert rows[-1][0] == dt_util.as_utc(_local(2026, 11, 9, 1))


@pytest.mark.parametrize(
    ("day", "count", "hours"),
    [
        # One bucket per hour that passed, as _store_recordings expects.
        (date(2027, 3, 28), 23, 23),
        (date(2026, 10, 25), 25, 25),
        # One bucket per clock hour: the skipped 02:00 joins 03:00, the
        # repeated 02:00 covers both of its passes.
        (date(2027, 3, 28), 24, 23),
        (date(2026, 10, 25), 24, 24),
    ],
)
async def test_build_rows_on_dst_days(hass, rome, day, count, hours):
    """A day of 23 or 25 hours keeps every bucket's energy, in that day."""
    rows = build_rows({day: [1.0] * count}, {}, {}, _local(2027, 4, 1))
    starts = [start for start, _ in rows]

    assert len(starts) == len(set(starts)) == hours
    assert sum(value for _, value in rows) == count
    assert starts[0] == dt_util.as_utc(_local(day.year, day.month, day.day))
    assert starts[-1] == dt_util.as_utc(_local(day.year, day.month, day.day, 23))


async def test_build_rows_wait_for_both_passes_of_the_repeated_hour(hass, rome):
    """With 24 buckets on the 25-hour day, 02:00 is added once it is over twice."""
    day = date(2026, 10, 25)
    # 02:30 on the second pass, when the 02:00 bucket can still grow.
    second_pass = datetime(2026, 10, 25, 1, 30, tzinfo=dt_util.UTC)
    rows = build_rows({day: [1.0] * 24}, {}, {}, second_pass)

    assert [start for start, _ in rows] == [
        dt_util.as_utc(_local(2026, 10, 25, 0)),
        dt_util.as_utc(_local(2026, 10, 25, 1)),
    ]


async def test_import_backfills_then_appends_without_extra_requests(
    recorder_mock: Recorder, hass: HomeAssistant, rome, freezer
):
    """The first import loads the history, later ones only add new hours."""
    freezer.move_to(_local(2026, 11, 9, 0, 30))
    requested: list[list[str]] = []
    bhc = _bhc(requested)
    zero_only: set[str] = set()

    changed = await async_import_energy(
        hass, bhc, DEVICE, _day_result(DAY), DAY, zero_only
    )
    await async_wait_recording_done(hass)

    assert len(requested) == 1
    last = await _last(recorder_mock, hass, TOTAL)
    assert last["sum"] == 30022
    assert last["start"] == _local(2026, 11, 8, 23).timestamp()
    assert await _last(recorder_mock, hass, CH) is not None
    # The tank-less unit fills the hot-water recording with zeros only.
    assert await _last(recorder_mock, hass, DHW) is None
    assert changed
    assert zero_only == {DHW}

    # After midnight the coordinator reads the previous day again: nothing new.
    changed = await async_import_energy(
        hass, bhc, DEVICE, _day_result(DAY), DAY, zero_only
    )
    await async_wait_recording_done(hass)
    assert not changed
    assert (await _last(recorder_mock, hass, TOTAL))["sum"] == 30022

    # Two hours later the first two hours of the day have arrived. The hot-water
    # counter still has no rows, but it is not backfilled a second time.
    freezer.move_to(_local(2026, 11, 9, 2, 30))
    today = date(2026, 11, 9)
    path = recording_path("emon/total/outputProduced", today.isoformat())
    result = {path: _hourly(3.0, 2.0)}
    await async_import_energy(hass, bhc, DEVICE, result, today, zero_only)
    await async_wait_recording_done(hass)

    assert len(requested) == 1
    last = await _last(recorder_mock, hass, TOTAL)
    assert last["sum"] == 30027
    assert last["start"] == _local(2026, 11, 9, 1).timestamp()


async def test_import_asks_history_only_for_counters_without_statistics(
    recorder_mock: Recorder, hass: HomeAssistant, rome, freezer
):
    """A counter that already has its statistic adds no history request."""
    freezer.move_to(_local(2026, 11, 9, 0, 30))
    requested: list[list[str]] = []
    bhc = _bhc(requested)
    zero_only: set[str] = set()
    total = recording_path("emon/total/outputProduced", DAY.isoformat())

    await async_import_energy(
        hass, bhc, DEVICE, {total: FIXTURE[total]}, DAY, zero_only
    )
    await async_wait_recording_done(hass)
    assert _counters(requested[-1]) == {"total"}

    # The heating and hot-water counters come later: only theirs is asked for.
    await async_import_energy(hass, bhc, DEVICE, _day_result(DAY), DAY, zero_only)
    await async_wait_recording_done(hass)
    assert len(requested) == 2
    assert _counters(requested[-1]) == {"ch", "dhw"}
    assert await _last(recorder_mock, hass, CH) is not None


async def test_import_fills_the_gap_after_downtime(
    recorder_mock: Recorder, hass: HomeAssistant, rome, freezer
):
    """Days missed while Home Assistant was down are read back hour by hour."""
    freezer.move_to(_local(2026, 11, 9, 0, 30))
    requested: list[list[str]] = []
    bhc = _bhc(requested)
    zero_only: set[str] = set()
    await async_import_energy(hass, bhc, DEVICE, _day_result(DAY), DAY, zero_only)
    await async_wait_recording_done(hass)

    # Down from 9 November until the 12th at 03:30, when the 12th's first three
    # hours are in. The 9th to the 11th are fetched again; the fake cloud has
    # nothing for them, so only the 12th's hours are added.
    freezer.move_to(_local(2026, 11, 12, 3, 30))
    day = date(2026, 11, 12)
    result = {
        recording_path(s, day.isoformat()): _hourly(1.0, 1.0, 2.0)
        for s in ("emon/total/outputProduced", "emon/ch/outputProduced")
    }
    await async_import_energy(hass, bhc, DEVICE, result, day, zero_only)
    await async_wait_recording_done(hass)

    asked = {p.rsplit("=", 1)[1] for p in requested[-1]}
    assert asked == {"2026-11-09", "2026-11-10", "2026-11-11"}
    last = await _last(recorder_mock, hass, TOTAL)
    assert last["sum"] == 30022 + 4
    assert last["start"] == _local(2026, 11, 12, 2).timestamp()


async def test_zero_only_counters_are_remembered_across_restarts(
    recorder_mock: Recorder, hass: HomeAssistant, rome, freezer, hass_storage
):
    """After a restart the hot-water counter does not request the history again."""
    freezer.move_to(_local(2026, 11, 9, 0, 30))
    requested: list[list[str]] = []
    coordinator = _coordinator(hass, _bhc(requested))
    entry = coordinator.entry
    key = f"{DOMAIN}.{entry.entry_id}.{DEVICE}.energy_statistics"

    await coordinator._import_statistics(_day_result(DAY), DAY)
    await async_wait_recording_done(hass)
    assert len(requested) == 1
    assert hass_storage[key]["data"] == [DHW]

    restarted = _coordinator(hass, _bhc(requested), entry)
    await restarted._import_statistics(_day_result(DAY), DAY)
    assert len(requested) == 1
    assert restarted._statistics_zero_only == {DHW}

    # Removing the integration deletes the stored counters.
    await async_remove_entry(hass, entry)
    assert key not in hass_storage


@pytest.mark.parametrize("error", [ApiError("boom"), RuntimeError("bug")])
async def test_import_errors_stay_in_the_background_task(
    recorder_mock: Recorder, hass: HomeAssistant, caplog, error
):
    """The import runs beside the update; its errors never reach it."""
    bhc = MagicMock()
    bhc.async_request_bulk = AsyncMock(side_effect=error)
    coordinator = _coordinator(hass, bhc)

    coordinator._start_statistics_import(_day_result(DAY), DAY)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert coordinator._statistics_task.done()
    assert coordinator._statistics_zero_only == set()
    # A cloud error waits quietly for the next hour, a bug is logged.
    assert ("Traceback" in caplog.text) == isinstance(error, RuntimeError)

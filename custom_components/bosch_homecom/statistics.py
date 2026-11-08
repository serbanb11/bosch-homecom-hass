"""Import the energy recordings into Home Assistant's long-term statistics.

The cloud keeps a K30/K40's ``/recordings/heatSources/emon/*`` energy counters
as hourly buckets for about ten days, daily buckets for about two months and
monthly buckets since installation. Each counter the device serves becomes the
external statistic ``bosch_homecom:<device id>_<key>``, selectable in the
energy dashboard. The first import backfills it with the finest resolution
each period still has; later imports append what the coordinator's hourly
recordings fetch brings, so they cost no extra requests.

A daily or monthly value is stored as one row at the start of its day or
month, so the energy dashboard shows it on that hour.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import EnergyConverter

from .const import DOMAIN, RECORDING_PATHS

# ponytail: only the emon kWh counters. The icom total/energyMonitoring branch
# stores per-minute sums whose daily and monthly buckets nobody has checked yet.
ENERGY_RECORDINGS: dict[str, str] = {
    suffix: meta["key"]
    for suffix, meta in RECORDING_PATHS.items()
    if suffix.startswith("emon/") and meta["agg"] == "sum"
}

# How far back the first import asks, a little past the retention seen on a K30
# (hourly ~10 days, daily ~2 months). Empty periods simply add no rows.
BACKFILL_DAYS = 14
BACKFILL_MONTHS = 6
BACKFILL_YEARS = 5

HOUR = timedelta(hours=1)


def recording_path(suffix: str, interval: str) -> str:
    """Return the bulk path of one recording for one interval."""
    return f"/recordings/heatSources/{suffix}?interval={interval}"


def bucket_values(payload: Any) -> list[float | None]:
    """Return one kWh value per bucket, None for a bucket without samples.

    An unpopulated bucket carries ``c: 0`` and a placeholder ``y`` of 1.
    """
    recording = payload.get("recording") if isinstance(payload, dict) else None
    if not isinstance(recording, list):
        return []
    values: list[float | None] = []
    for bucket in recording:
        c = bucket.get("c") if isinstance(bucket, dict) else None
        y = bucket.get("y") if isinstance(bucket, dict) else None
        populated = isinstance(c, (int, float)) and c > 0
        values.append(float(y) if populated and isinstance(y, (int, float)) else None)
    return values


def _start(day: date) -> datetime:
    """Return the UTC start of a local day, on the hour statistics are kept in.

    ponytail: in a zone with a half-hour offset the row moves by 30 minutes.
    """
    return dt_util.as_utc(dt_util.start_of_local_day(day)).replace(
        minute=0, second=0, microsecond=0
    )


def _next_month(first: date) -> date:
    return (first + timedelta(days=32)).replace(day=1)


def build_rows(
    hourly: dict[date, list[float | None]],
    daily: dict[date, list[float | None]],
    monthly: dict[int, list[float | None]],
    now: datetime,
) -> list[tuple[datetime, float]]:
    """Merge the three resolutions of one counter into hourly rows.

    ``hourly`` is keyed by day, ``daily`` by the first day of a month and
    ``monthly`` by year. A bucket is used once its period is over, and a
    coarser bucket only when it ends before the finer rows start, so no
    energy is counted twice.
    """
    rows: list[tuple[datetime, float]] = []
    for day, values in hourly.items():
        start, end = _start(day), _start(day + timedelta(days=1))
        for index, value in enumerate(values):
            hour = start + index * HOUR
            if value is not None and hour + HOUR <= min(end, now):
                rows.append((hour, value))

    finer = min((start for start, _ in rows), default=now)
    for first, values in daily.items():
        for index, value in enumerate(values):
            day = first + timedelta(days=index)
            if day.month != first.month:
                break
            if value is not None and _start(day + timedelta(days=1)) <= finer:
                rows.append((_start(day), value))

    finer = min((start for start, _ in rows), default=now)
    for year, values in monthly.items():
        for index, value in enumerate(values[:12]):
            first = date(year, index + 1, 1)
            if value is not None and _start(_next_month(first)) <= finer:
                rows.append((_start(first), value))
    return sorted(rows)


def with_sums(
    rows: list[tuple[datetime, float]], after: datetime | None, total: float
) -> list[StatisticData]:
    """Return the rows newer than ``after``, summed on from ``total``."""
    statistics: list[StatisticData] = []
    for start, value in rows:
        if after is not None and start <= after:
            continue
        total += value
        statistics.append(StatisticData(start=start, sum=total))
    return statistics


def _intervals(day: date, resume: date | None) -> list[str]:
    """Return the intervals to fetch besides ``day`` itself.

    Without a ``resume`` day (a counter has no rows yet) every resolution is
    asked for. Otherwise only the days from ``resume`` to before ``day`` are
    missing, which is none in normal operation.
    """
    if resume is not None:
        gap = (day - resume).days
        return [
            (resume + timedelta(days=n)).isoformat()
            for n in range(max(0, gap - BACKFILL_DAYS), gap)
        ]
    days = [(day - timedelta(days=n)).isoformat() for n in range(1, BACKFILL_DAYS)]
    months, first = [], day.replace(day=1)
    for _ in range(BACKFILL_MONTHS):
        months.append(first.strftime("%Y-%m"))
        first = (first - timedelta(days=1)).replace(day=1)
    years = [str(day.year - n) for n in range(BACKFILL_YEARS)]
    return days + months + years


async def _last_row(
    hass: HomeAssistant, statistic_id: str
) -> tuple[datetime, float] | None:
    """Return the start and sum of a statistic's last row, or None."""
    stats = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, statistic_id, True, {"sum"}
    )
    if not stats.get(statistic_id):
        return None
    row = stats[statistic_id][0]
    return dt_util.utc_from_timestamp(row["start"]), row.get("sum") or 0.0


async def async_import_energy(
    hass: HomeAssistant,
    bhc: Any,
    device_id: str,
    result: dict,
    day: date,
    backfilled: set[str],
) -> None:
    """Add the energy rows that ``result``, the bulk answer for ``day``, brings.

    Counters without statistics yet are backfilled first, once per
    ``backfilled`` set (the caller keeps it for the run): a counter the device
    answers but never fills with energy, such as hot water on a unit without a
    tank, would otherwise ask for the whole history every hour. A gap left by Home
    Assistant being down is filled from the hourly buckets still kept.
    """
    served = [
        suffix
        for suffix in ENERGY_RECORDINGS
        if isinstance(result.get(recording_path(suffix, day.isoformat())), dict)
    ]
    if not served:
        return
    ids = {s: f"{DOMAIN}:{device_id}_{ENERGY_RECORDINGS[s]}" for s in served}
    last = {s: await _last_row(hass, ids[s]) for s in served}

    pending = {ids[s] for s in served if last[s] is None} - backfilled
    starts = [row[0] for row in last.values() if row is not None]
    intervals: list[str] = []
    if pending:
        intervals = _intervals(day, None)
    elif starts:
        intervals = _intervals(day, dt_util.as_local(min(starts) + HOUR).date())
    fetched = dict(result)
    if intervals:
        paths = [recording_path(s, iv) for iv in intervals for s in served]
        fetched.update(await bhc.async_request_bulk(device_id, paths) or {})
    backfilled |= pending

    now = dt_util.utcnow()
    for suffix in served:
        hourly: dict[date, list[float | None]] = {}
        daily: dict[date, list[float | None]] = {}
        monthly: dict[int, list[float | None]] = {}
        for interval in [day.isoformat(), *intervals]:
            values = bucket_values(fetched.get(recording_path(suffix, interval)))
            if len(interval) == 10:
                hourly[date.fromisoformat(interval)] = values
            elif len(interval) == 7:
                daily[date.fromisoformat(f"{interval}-01")] = values
            else:
                monthly[int(interval)] = values
        after, total = last[suffix] or (None, 0.0)
        statistics = with_sums(build_rows(hourly, daily, monthly, now), after, total)
        # A new statistic starts with its first energy: a counter the unit
        # fills with zeros only (hot water without a tank) creates none.
        if not statistics or (after is None and not statistics[-1]["sum"]):
            continue
        key = ENERGY_RECORDINGS[suffix]
        metadata = StatisticMetaData(
            mean_type=StatisticMeanType.NONE,
            has_sum=True,
            name=f"Bosch HomeCom {device_id} {key.replace('_', ' ')}",
            source=DOMAIN,
            statistic_id=ids[suffix],
            unit_class=EnergyConverter.UNIT_CLASS,
            unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        )
        async_add_external_statistics(hass, metadata, statistics)

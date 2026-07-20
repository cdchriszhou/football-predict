"""Datetime helpers — Beijing business day for 体彩 / dashboard, UTC for legacy fields."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

CHINA_TZ = ZoneInfo("Asia/Shanghai")


def utc_now() -> datetime:
    return datetime.utcnow()


def china_now() -> datetime:
    """Current time in China (体彩销售日 / 开奖时区)."""
    return datetime.now(CHINA_TZ)


def china_today() -> date:
    """Today's date in Asia/Shanghai — aligns with sporttery businessDate."""
    return china_now().date()


def beijing_day_bounds_naive() -> tuple[datetime, datetime]:
    """Start/end of today in Beijing as naive datetimes (matches DB match_time storage)."""
    today = china_today()
    start = datetime(today.year, today.month, today.day, 0, 0, 0)
    return start, start + timedelta(days=1)


def format_beijing_iso(dt: datetime | None) -> str | None:
    """Serialize naive Beijing wall-clock match_time with +08:00 for correct UI parsing."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        local = dt.astimezone(CHINA_TZ).replace(tzinfo=None)
    else:
        local = dt
    aware = local.replace(tzinfo=CHINA_TZ)
    return aware.isoformat()


def format_utc_iso(dt: datetime | None) -> str | None:
    """Serialize naive UTC datetime with Z suffix for correct frontend parsing."""
    if dt is None:
        return None
    return dt.isoformat() + "Z"

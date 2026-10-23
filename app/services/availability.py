from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def window_label(charger) -> str | None:
    if charger.available_from is None or charger.available_to is None:
        return None
    return f"{charger.available_from:%H:%M}–{charger.available_to:%H:%M} ({charger.timezone})"


def fits_window(charger, start: datetime, end: datetime) -> bool:
    """True if the booking (naive UTC start/end) lies fully inside one daily availability window."""
    if charger.available_from is None or charger.available_to is None:
        return True
    tz = ZoneInfo(charger.timezone)
    s = start.replace(tzinfo=timezone.utc)
    e = end.replace(tzinfo=timezone.utc)
    local_day = s.astimezone(tz).date()
    f, t = charger.available_from, charger.available_to
    for offset in (0, -1):  # also try the window that began the previous evening
        day = local_day + timedelta(days=offset)
        w_start = datetime.combine(day, f, tzinfo=tz).astimezone(timezone.utc)
        w_end_day = day if t > f else day + timedelta(days=1)
        w_end = datetime.combine(w_end_day, t, tzinfo=tz).astimezone(timezone.utc)
        if w_start <= s and e <= w_end:
            return True
    return False

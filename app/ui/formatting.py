from datetime import datetime, timezone


def utc(value):
    if value is None: return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def datetime_text(value):
    value = utc(value)
    return "—" if value is None else value.strftime("%d %b, %H:%M UTC")


def datetime_full(value):
    value = utc(value)
    return "—" if value is None else value.isoformat()


def price(value):
    return "—" if value is None else f"${float(value):,.2f}"


def percent(value, digits=2):
    return "—" if value is None else f"{float(value):.{digits}f}%"


def duration(seconds):
    if seconds is None: return "—"
    seconds = int(seconds)
    if seconds < 60: return f"{seconds}s"
    if seconds < 3600: return f"{seconds//60}m {seconds%60}s"
    return f"{seconds//3600}h {(seconds%3600)//60}m"


def age_seconds(value):
    value = utc(value)
    return None if value is None else int((datetime.now(timezone.utc)-value).total_seconds())

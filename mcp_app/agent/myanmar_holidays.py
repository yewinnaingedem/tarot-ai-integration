# mcp_app/agent/myanmar_holidays.py
from datetime import date, datetime

# ── Myanmar Public Holidays 2025-2026 ─────────────────────────
MYANMAR_HOLIDAYS = {
    # 2025
    date(2025, 1, 4):  {"name": "Independence Day", "name_mm": "လွတ်လပ်ရေးနေ့", "type": "public"},
    date(2025, 2, 12): {"name": "Union Day", "name_mm": "ပြည်ထောင်စုနေ့", "type": "public"},
    date(2025, 3, 2):  {"name": "Peasants Day", "name_mm": "တောင်သူလယ်သမားနေ့", "type": "public"},
    date(2025, 3, 27): {"name": "Armed Forces Day", "name_mm": "တပ်မတော်နေ့", "type": "public"},
    date(2025, 4, 13): {"name": "Thingyan Water Festival", "name_mm": "သင်္ကြန်ရေပွဲ", "type": "thingyan"},
    date(2025, 4, 14): {"name": "Thingyan Water Festival", "name_mm": "သင်္ကြန်ရေပွဲ", "type": "thingyan"},
    date(2025, 4, 15): {"name": "Thingyan Water Festival", "name_mm": "သင်္ကြန်ရေပွဲ", "type": "thingyan"},
    date(2025, 4, 16): {"name": "Myanmar New Year", "name_mm": "မြန်မာနှစ်သစ်ကူး", "type": "public"},
    date(2025, 4, 17): {"name": "Myanmar New Year Holiday", "name_mm": "နှစ်သစ်ကူးရုံးပိတ်", "type": "public"},
    date(2025, 5, 1):  {"name": "Workers Day", "name_mm": "အလုပ်သမားနေ့", "type": "public"},
    date(2025, 5, 12): {"name": "Kason Full Moon Day", "name_mm": "ကဆုန်လပြည့်နေ့", "type": "public"},
    date(2025, 7, 19): {"name": "Martyrs Day", "name_mm": "အာဇာနည်နေ့", "type": "public"},
    date(2025, 10, 6): {"name": "Thadingyut Festival", "name_mm": "သဝေသနေ့ / သီတင်းကျွတ်", "type": "festival"},
    date(2025, 10, 7): {"name": "Thadingyut Holiday", "name_mm": "သီတင်းကျွတ်ရုံးပိတ်", "type": "festival"},
    date(2025, 10, 8): {"name": "Thadingyut Holiday", "name_mm": "သီတင်းကျွတ်ရုံးပိတ်", "type": "festival"},
    date(2025, 11, 4): {"name": "Tazaungdaing Festival", "name_mm": "တန်ဆောင်တိုင်နေ့", "type": "festival"},
    date(2025, 11, 5): {"name": "Tazaungdaing Holiday", "name_mm": "တန်ဆောင်တိုင်ရုံးပိတ်", "type": "festival"},
    date(2025, 12, 25): {"name": "Christmas Day", "name_mm": "ခရစ်စမတ်နေ့", "type": "public"},

    # 2026
    date(2026, 1, 4):  {"name": "Independence Day", "name_mm": "လွတ်လပ်ရေးနေ့", "type": "public"},
    date(2026, 2, 12): {"name": "Union Day", "name_mm": "ပြည်ထောင်စုနေ့", "type": "public"},
    date(2026, 3, 2):  {"name": "Peasants Day", "name_mm": "တောင်သူလယ်သမားနေ့", "type": "public"},
    date(2026, 3, 27): {"name": "Armed Forces Day", "name_mm": "တပ်မတော်နေ့", "type": "public"},
    date(2026, 4, 11): {"name": "Thingyan Eve", "name_mm": "သင်္ကြန်အကြိုနေ့", "type": "thingyan"},
    date(2026, 4, 12): {"name": "Thingyan Water Festival", "name_mm": "သင်္ကြန်ရေပွဲ", "type": "thingyan"},
    date(2026, 4, 13): {"name": "Thingyan Water Festival", "name_mm": "သင်္ကြန်ရေပွဲ", "type": "thingyan"},
    date(2026, 4, 14): {"name": "Thingyan Water Festival", "name_mm": "သင်္ကြန်ရေပွဲ", "type": "thingyan"},
    date(2026, 4, 15): {"name": "Thingyan Water Festival", "name_mm": "သင်္ကြန်ရေပွဲ", "type": "thingyan"},
    date(2026, 4, 16): {"name": "Myanmar New Year", "name_mm": "မြန်မာနှစ်သစ်ကူး", "type": "public"},
    date(2026, 4, 17): {"name": "Myanmar New Year Holiday", "name_mm": "နှစ်သစ်ကူးရုံးပိတ်", "type": "public"},
    date(2026, 4, 19): {"name": "Myanmar New Year Office Holiday", "name_mm": "နှစ်သစ်ကူးရုံးပိတ်ရက်", "type": "public"},
    date(2026, 4, 30): {"name": "Kason Full Moon Day", "name_mm": "ကဆုန်လပြည့်နေ့", "type": "public"},
    date(2026, 5, 1):  {"name": "Workers Day", "name_mm": "အလုပ်သမားနေ့", "type": "public"},
    date(2026, 7, 19): {"name": "Martyrs Day", "name_mm": "အာဇာနည်နေ့", "type": "public"},
    date(2026, 12, 25): {"name": "Christmas Day", "name_mm": "ခရစ်စမတ်နေ့", "type": "public"},
}

# ── Holiday periods (multi-day events) ───────────────────────
HOLIDAY_PERIODS = {
    "thingyan_2025": {
        "name":       "Thingyan Water Festival 2025",
        "name_mm":    "သင်္ကြန်ရေပွဲ ၂၀၂၅",
        "start":      date(2025, 4, 13),
        "end":        date(2025, 4, 17),
        "pre_start":  date(2025, 4, 10),  # pre-holiday boost starts
    },
    "thingyan_2026": {
        "name":       "Thingyan Water Festival 2026",
        "name_mm":    "သင်္ကြန်ရေပွဲ ၂၀၂၆",
        "start":      date(2026, 4, 11),
        "end":        date(2026, 4, 19),
        "pre_start":  date(2026, 4, 7),
    },
    "thadingyut_2025": {
        "name":       "Thadingyut Festival 2025",
        "name_mm":    "သီတင်းကျွတ်ပွဲ ၂၀၂၅",
        "start":      date(2025, 10, 6),
        "end":        date(2025, 10, 8),
        "pre_start":  date(2025, 10, 3),
    },
    "tazaungdaing_2025": {
        "name":       "Tazaungdaing Festival 2025",
        "name_mm":    "တန်ဆောင်တိုင်ပွဲ ၂၀၂၅",
        "start":      date(2025, 11, 4),
        "end":        date(2025, 11, 5),
        "pre_start":  date(2025, 11, 1),
    },
}


def get_upcoming_holidays(days_ahead: int = 60) -> list:
    """Get holidays coming up in the next N days"""
    today    = date.today()
    upcoming = []

    for holiday_date, info in sorted(MYANMAR_HOLIDAYS.items()):
        delta = (holiday_date - today).days
        if 0 <= delta <= days_ahead:
            upcoming.append({
                "date":     holiday_date.strftime("%Y-%m-%d"),
                "days_away": delta,
                "name":     info["name"],
                "name_mm":  info["name_mm"],
                "type":     info["type"],
            })

    return upcoming


def get_holiday_context_for_date(target_date: date) -> dict | None:
    """Check if a date is a holiday or near a holiday"""
    # Check exact match
    if target_date in MYANMAR_HOLIDAYS:
        return MYANMAR_HOLIDAYS[target_date]

    # Check if within 7 days before a holiday
    for holiday_date, info in MYANMAR_HOLIDAYS.items():
        delta = (holiday_date - target_date).days
        if 0 < delta <= 7:
            return {
                **info,
                "days_until": delta,
                "context":    f"Pre-holiday period — {info['name']} in {delta} days",
            }

    return None


def get_holiday_period_for_date(target_date: date) -> dict | None:
    """Check if date falls within a known holiday period"""
    for key, period in HOLIDAY_PERIODS.items():
        if period["pre_start"] <= target_date <= period["end"]:
            return {
                "period_name": period["name"],
                "name_mm":     period["name_mm"],
                "start":       period["start"].strftime("%Y-%m-%d"),
                "end":         period["end"].strftime("%Y-%m-%d"),
                "is_pre_holiday": target_date < period["start"],
            }
    return None
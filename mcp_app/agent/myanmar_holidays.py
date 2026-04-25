# mcp_app/agent/myanmar_holidays.py
from datetime import date, datetime

# ── Myanmar Public Holidays & Commercial Events 2025-2026 ─────
MYANMAR_HOLIDAYS = {
    # ── 2025 ──────────────────────────────────────────────────
    date(2025, 1, 1):  {"name": "New Year's Day",           "name_mm": "နှစ်သစ်ကူးနေ့ (ဂရီဂိုရီ)",    "type": "festival"},
    date(2025, 1, 4):  {"name": "Independence Day",          "name_mm": "လွတ်လပ်ရေးနေ့",              "type": "public"},
    date(2025, 1, 29): {"name": "Chinese New Year",          "name_mm": "တရုတ်နှစ်သစ်ကူး",            "type": "festival"},
    date(2025, 2, 12): {"name": "Union Day",                 "name_mm": "ပြည်ထောင်စုနေ့",              "type": "public"},
    date(2025, 2, 14): {"name": "Valentine's Day",           "name_mm": "ချစ်သူများနေ့",               "type": "festival"},
    date(2025, 3, 2):  {"name": "Peasants Day",              "name_mm": "တောင်သူလယ်သမားနေ့",          "type": "public"},
    date(2025, 3, 27): {"name": "Armed Forces Day",          "name_mm": "တပ်မတော်နေ့",                "type": "public"},
    date(2025, 4, 13): {"name": "Thingyan Water Festival",   "name_mm": "သင်္ကြန်ရေပွဲ",              "type": "thingyan"},
    date(2025, 4, 14): {"name": "Thingyan Water Festival",   "name_mm": "သင်္ကြန်ရေပွဲ",              "type": "thingyan"},
    date(2025, 4, 15): {"name": "Thingyan Water Festival",   "name_mm": "သင်္ကြန်ရေပွဲ",              "type": "thingyan"},
    date(2025, 4, 16): {"name": "Myanmar New Year",          "name_mm": "မြန်မာနှစ်သစ်ကူး",           "type": "thingyan"},
    date(2025, 4, 17): {"name": "Myanmar New Year Holiday",  "name_mm": "နှစ်သစ်ကူးရုံးပိတ်",         "type": "thingyan"},
    date(2025, 5, 1):  {"name": "Workers Day",               "name_mm": "အလုပ်သမားနေ့",               "type": "public"},
    date(2025, 5, 12): {"name": "Kason Full Moon Day",       "name_mm": "ကဆုန်လပြည့်နေ့",             "type": "fullmoon"},
    date(2025, 6, 11): {"name": "Waso Full Moon Day",        "name_mm": "ဝါဆိုလပြည့်နေ့",             "type": "fullmoon"},
    date(2025, 7, 19): {"name": "Martyrs Day",               "name_mm": "အာဇာနည်နေ့",                 "type": "public"},
    date(2025, 9, 7):  {"name": "Thawthalin Full Moon Day",  "name_mm": "သီတင်းကျွတ်မတိုင်မီ လပြည့်", "type": "fullmoon"},
    date(2025, 10, 2): {"name": "Eid al-Adha (approx)",      "name_mm": "အိဒ်အယ်လ်အဒ်ဟာ",            "type": "festival"},
    date(2025, 10, 6): {"name": "Thadingyut Festival",       "name_mm": "သဝေသနေ့ / သီတင်းကျွတ်",     "type": "festival"},
    date(2025, 10, 7): {"name": "Thadingyut Holiday",        "name_mm": "သီတင်းကျွတ်ရုံးပိတ်",        "type": "festival"},
    date(2025, 10, 8): {"name": "Thadingyut Holiday",        "name_mm": "သီတင်းကျွတ်ရုံးပိတ်",        "type": "festival"},
    date(2025, 10, 20):{"name": "Deepawali",                 "name_mm": "ဒီပါဝလီပွဲ",                 "type": "festival"},
    date(2025, 11, 4): {"name": "Tazaungdaing Festival",     "name_mm": "တန်ဆောင်တိုင်နေ့",           "type": "festival"},
    date(2025, 11, 5): {"name": "Tazaungdaing Holiday",      "name_mm": "တန်ဆောင်တိုင်ရုံးပိတ်",      "type": "festival"},
    date(2025, 11, 11):{"name": "National Day",              "name_mm": "အမျိုးသားနေ့",               "type": "public"},
    date(2025, 12, 25):{"name": "Christmas Day",             "name_mm": "ခရစ်စမတ်နေ့",               "type": "festival"},
    date(2025, 12, 31):{"name": "New Year's Eve",            "name_mm": "နှစ်သစ်ကူးညနေ",             "type": "festival"},

    # ── 2026 ──────────────────────────────────────────────────
    date(2026, 1, 1):  {"name": "New Year's Day",            "name_mm": "နှစ်သစ်ကူးနေ့ (ဂရီဂိုရီ)",   "type": "festival"},
    date(2026, 1, 4):  {"name": "Independence Day",          "name_mm": "လွတ်လပ်ရေးနေ့",              "type": "public"},
    date(2026, 1, 17): {"name": "Chinese New Year",          "name_mm": "တရုတ်နှစ်သစ်ကူး",            "type": "festival"},
    date(2026, 2, 12): {"name": "Union Day",                 "name_mm": "ပြည်ထောင်စုနေ့",              "type": "public"},
    date(2026, 2, 14): {"name": "Valentine's Day",           "name_mm": "ချစ်သူများနေ့",               "type": "festival"},
    date(2026, 3, 2):  {"name": "Peasants Day",              "name_mm": "တောင်သူလယ်သမားနေ့",          "type": "public"},
    date(2026, 3, 27): {"name": "Armed Forces Day",          "name_mm": "တပ်မတော်နေ့",                "type": "public"},
    date(2026, 4, 11): {"name": "Thingyan Eve",              "name_mm": "သင်္ကြန်အကြိုနေ့",           "type": "thingyan"},
    date(2026, 4, 12): {"name": "Thingyan Water Festival",   "name_mm": "သင်္ကြန်ရေပွဲ",              "type": "thingyan"},
    date(2026, 4, 13): {"name": "Thingyan Water Festival",   "name_mm": "သင်္ကြန်ရေပွဲ",              "type": "thingyan"},
    date(2026, 4, 14): {"name": "Thingyan Water Festival",   "name_mm": "သင်္ကြန်ရေပွဲ",              "type": "thingyan"},
    date(2026, 4, 15): {"name": "Thingyan Water Festival",   "name_mm": "သင်္ကြန်ရေပွဲ",              "type": "thingyan"},
    date(2026, 4, 16): {"name": "Myanmar New Year",          "name_mm": "မြန်မာနှစ်သစ်ကူး",           "type": "thingyan"},
    date(2026, 4, 17): {"name": "Myanmar New Year Holiday",  "name_mm": "နှစ်သစ်ကူးရုံးပိတ်",         "type": "thingyan"},
    date(2026, 4, 19): {"name": "Myanmar New Year Holiday",  "name_mm": "နှစ်သစ်ကူးရုံးပိတ်ရက်",      "type": "thingyan"},
    date(2026, 4, 30): {"name": "Kason Full Moon Day",       "name_mm": "ကဆုန်လပြည့်နေ့",             "type": "fullmoon"},
    date(2026, 5, 1):  {"name": "Workers Day",               "name_mm": "အလုပ်သမားနေ့",               "type": "public"},
    date(2026, 5, 29): {"name": "Waso Full Moon Day",        "name_mm": "ဝါဆိုလပြည့်နေ့",             "type": "fullmoon"},
    date(2026, 7, 19): {"name": "Martyrs Day",               "name_mm": "အာဇာနည်နေ့",                 "type": "public"},
    date(2026, 9, 21): {"name": "Eid al-Adha (approx)",      "name_mm": "အိဒ်အယ်လ်အဒ်ဟာ",            "type": "festival"},
    date(2026, 10, 1): {"name": "Thadingyut Festival",       "name_mm": "သဝေသနေ့ / သီတင်းကျွတ်",     "type": "festival"},
    date(2026, 10, 2): {"name": "Thadingyut Holiday",        "name_mm": "သီတင်းကျွတ်ရုံးပိတ်",        "type": "festival"},
    date(2026, 10, 3): {"name": "Thadingyut Holiday",        "name_mm": "သီတင်းကျွတ်ရုံးပိတ်",        "type": "festival"},
    date(2026, 10, 9): {"name": "Deepawali",                 "name_mm": "ဒီပါဝလီပွဲ",                 "type": "festival"},
    date(2026, 10, 30):{"name": "Tazaungdaing Festival",     "name_mm": "တန်ဆောင်တိုင်နေ့",           "type": "festival"},
    date(2026, 10, 31):{"name": "Tazaungdaing Holiday",      "name_mm": "တန်ဆောင်တိုင်ရုံးပိတ်",      "type": "festival"},
    date(2026, 11, 11):{"name": "National Day",              "name_mm": "အမျိုးသားနေ့",               "type": "public"},
    date(2026, 12, 25):{"name": "Christmas Day",             "name_mm": "ခရစ်စမတ်နေ့",               "type": "festival"},
    date(2026, 12, 31):{"name": "New Year's Eve",            "name_mm": "နှစ်သစ်ကူးညနေ",             "type": "festival"},
}

# ── Holiday periods (multi-day events for order analysis) ─────
HOLIDAY_PERIODS = {
    "new_year_2025": {
        "name":      "New Year 2025",
        "name_mm":   "နှစ်သစ်ကူး ၂၀၂၅",
        "start":     date(2025, 1, 1),
        "end":       date(2025, 1, 1),
        "pre_start": date(2024, 12, 28),
    },
    "chinese_new_year_2025": {
        "name":      "Chinese New Year 2025",
        "name_mm":   "တရုတ်နှစ်သစ်ကူး ၂၀၂၅",
        "start":     date(2025, 1, 29),
        "end":       date(2025, 1, 29),
        "pre_start": date(2025, 1, 26),
    },
    "valentine_2025": {
        "name":      "Valentine's Day 2025",
        "name_mm":   "ချစ်သူများနေ့ ၂၀၂၅",
        "start":     date(2025, 2, 14),
        "end":       date(2025, 2, 14),
        "pre_start": date(2025, 2, 10),
    },
    "thingyan_2025": {
        "name":      "Thingyan Water Festival 2025",
        "name_mm":   "သင်္ကြန်ရေပွဲ ၂၀၂၅",
        "start":     date(2025, 4, 13),
        "end":       date(2025, 4, 17),
        "pre_start": date(2025, 4, 10),
    },
    "thadingyut_2025": {
        "name":      "Thadingyut Festival 2025",
        "name_mm":   "သီတင်းကျွတ်ပွဲ ၂၀၂၅",
        "start":     date(2025, 10, 6),
        "end":       date(2025, 10, 8),
        "pre_start": date(2025, 10, 3),
    },
    "tazaungdaing_2025": {
        "name":      "Tazaungdaing Festival 2025",
        "name_mm":   "တန်ဆောင်တိုင်ပွဲ ၂၀၂၅",
        "start":     date(2025, 11, 4),
        "end":       date(2025, 11, 5),
        "pre_start": date(2025, 11, 1),
    },
    "christmas_2025": {
        "name":      "Christmas 2025",
        "name_mm":   "ခရစ်စမတ်ပွဲ ၂၀၂၅",
        "start":     date(2025, 12, 25),
        "end":       date(2025, 12, 31),
        "pre_start": date(2025, 12, 20),
    },
    "new_year_2026": {
        "name":      "New Year 2026",
        "name_mm":   "နှစ်သစ်ကူး ၂၀၂၆",
        "start":     date(2026, 1, 1),
        "end":       date(2026, 1, 1),
        "pre_start": date(2025, 12, 28),
    },
    "chinese_new_year_2026": {
        "name":      "Chinese New Year 2026",
        "name_mm":   "တရုတ်နှစ်သစ်ကူး ၂၀၂၆",
        "start":     date(2026, 1, 17),
        "end":       date(2026, 1, 17),
        "pre_start": date(2026, 1, 14),
    },
    "valentine_2026": {
        "name":      "Valentine's Day 2026",
        "name_mm":   "ချစ်သူများနေ့ ၂၀၂၆",
        "start":     date(2026, 2, 14),
        "end":       date(2026, 2, 14),
        "pre_start": date(2026, 2, 10),
    },
    "thingyan_2026": {
        "name":      "Thingyan Water Festival 2026",
        "name_mm":   "သင်္ကြန်ရေပွဲ ၂၀၂၆",
        "start":     date(2026, 4, 11),
        "end":       date(2026, 4, 19),
        "pre_start": date(2026, 4, 7),
    },
    "thadingyut_2026": {
        "name":      "Thadingyut Festival 2026",
        "name_mm":   "သီတင်းကျွတ်ပွဲ ၂၀၂၆",
        "start":     date(2026, 10, 1),
        "end":       date(2026, 10, 3),
        "pre_start": date(2026, 9, 28),
    },
    "tazaungdaing_2026": {
        "name":      "Tazaungdaing Festival 2026",
        "name_mm":   "တန်ဆောင်တိုင်ပွဲ ၂၀၂၆",
        "start":     date(2026, 10, 30),
        "end":       date(2026, 10, 31),
        "pre_start": date(2026, 10, 27),
    },
    "christmas_2026": {
        "name":      "Christmas 2026",
        "name_mm":   "ခရစ်စမတ်ပွဲ ၂၀၂၆",
        "start":     date(2026, 12, 25),
        "end":       date(2026, 12, 31),
        "pre_start": date(2026, 12, 20),
    },
}


def get_upcoming_holidays(days_ahead: int = 60) -> list:
    today    = date.today()
    upcoming = []
    for holiday_date, info in sorted(MYANMAR_HOLIDAYS.items()):
        delta = (holiday_date - today).days
        if 0 <= delta <= days_ahead:
            upcoming.append({
                "date":      holiday_date.strftime("%Y-%m-%d"),
                "days_away": delta,
                "name":      info["name"],
                "name_mm":   info["name_mm"],
                "type":      info["type"],
            })
    return upcoming


def get_holiday_context_for_date(target_date: date) -> dict | None:
    if target_date in MYANMAR_HOLIDAYS:
        return MYANMAR_HOLIDAYS[target_date]
    for holiday_date, info in MYANMAR_HOLIDAYS.items():
        delta = (holiday_date - target_date).days
        if 0 < delta <= 7:
            return {**info, "days_until": delta, "context": f"Pre-holiday — {info['name']} in {delta} days"}
    return None


def get_holiday_period_for_date(target_date: date) -> dict | None:
    for key, period in HOLIDAY_PERIODS.items():
        if period["pre_start"] <= target_date <= period["end"]:
            return {
                "period_name":    period["name"],
                "name_mm":        period["name_mm"],
                "start":          period["start"].strftime("%Y-%m-%d"),
                "end":            period["end"].strftime("%Y-%m-%d"),
                "is_pre_holiday": target_date < period["start"],
            }
    return None

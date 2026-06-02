import os
import asyncio
import logging
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

# ═══════════════════════════════════════════════════════
# КОНФИГ
# ═══════════════════════════════════════════════════════
BOT_TOKEN = os.getenv("BOT_TOKEN", "8393309194:AAHN-2LSXibBfMRmQ2k5XsphyY9dOGrQ5XU")
SHEET_ID  = os.getenv("SHEET_ID", "1nGcC77Uqy_Y642FuWGgZh_Ebwzzo9KszKlP-HjO0njs")
SHEET_NAME = "📋 Офферы"
REQUESTS_SHEET_ID   = os.getenv("REQUESTS_SHEET_ID", "1YISJ2t_vXy2FK-FGsKtPzS5vea10TDFREVhF1ykXEnI")
REQUESTS_SHEET_NAME = "📥 Запросы"
CHECK_INTERVAL = 300  # секунд (5 минут)

CHANNEL_ID = -1003960058902

# ID веток (thread_id)
TOPICS = {
    "hot":        4,
    "latam":      7,
    "asia":       6,
    "sng":        9,
    "africa":     10,
    "exclusive":  11,
    "eu":         5,
    "new_tests":  14,
    "analytics":  15,
    "mena":       17,
    "nordics":    18,
    "updates":    19,
    "thepacemedia": 3,
}

# Маппинг регион → топик
REGION_TO_TOPIC = {
    "t1 eu":   "eu",
    "t1eu":    "eu",
    "азия":    "asia",
    "латам":   "latam",
    "latam":   "latam",
    "снг":     "sng",
    "сng":     "sng",
    "африка":  "africa",
    "africa":  "africa",
    "mena":    "mena",
    "nordics": "nordics",
}

# Маппинг ГЕО код → флаг
GEO_FLAGS = {
    "GB": "🇬🇧", "DE": "🇩🇪", "FR": "🇫🇷", "IT": "🇮🇹", "ES": "🇪🇸",
    "NL": "🇳🇱", "AT": "🇦🇹", "CH": "🇨🇭", "BE": "🇧🇪", "SE": "🇸🇪",
    "NO": "🇳🇴", "FI": "🇫🇮", "DK": "🇩🇰", "IE": "🇮🇪", "PT": "🇵🇹",
    "PL": "🇵🇱", "CZ": "🇨🇿", "HU": "🇭🇺", "RO": "🇷🇴", "SK": "🇸🇰",
    "BG": "🇧🇬", "HR": "🇭🇷", "LT": "🇱🇹", "LV": "🇱🇻", "EE": "🇪🇪",
    "SG": "🇸🇬", "MY": "🇲🇾", "TH": "🇹🇭", "VN": "🇻🇳", "PH": "🇵🇭",
    "ID": "🇮🇩", "IN": "🇮🇳", "JP": "🇯🇵", "KR": "🇰🇷", "BD": "🇧🇩",
    "TR": "🇹🇷", "KH": "🇰🇭", "MM": "🇲🇲", "PK": "🇵🇰",
    "BR": "🇧🇷", "MX": "🇲🇽", "AR": "🇦🇷", "CL": "🇨🇱", "CO": "🇨🇴",
    "PE": "🇵🇪", "EC": "🇪🇨", "UY": "🇺🇾", "PY": "🇵🇾", "BO": "🇧🇴",
    "UA": "🇺🇦", "KZ": "🇰🇿", "UZ": "🇺🇿", "AZ": "🇦🇿", "GE": "🇬🇪",
    "MD": "🇲🇩", "AM": "🇦🇲", "KG": "🇰🇬", "TJ": "🇹🇯", "BY": "🇧🇾",
    "NG": "🇳🇬", "ZA": "🇿🇦", "KE": "🇰🇪", "GH": "🇬🇭", "TZ": "🇹🇿",
    "ET": "🇪🇹", "ZW": "🇿🇼", "SL": "🇸🇱",
    "SA": "🇸🇦", "AE": "🇦🇪", "EG": "🇪🇬", "IQ": "🇮🇶", "MA": "🇲🇦",
    "US": "🇺🇸", "CA": "🇨🇦", "AU": "🇦🇺", "NZ": "🇳🇿",
}

# Колонки (0-based index)
COL = {
    "inp":        0,   # A - конфиденциально
    "partner":    1,   # B - конфиденциально
    "offer":      2,   # C
    "geo":        3,   # D
    "region":     4,   # E
    "source":     5,   # F
    "status":     6,   # G
    "rate":       7,   # H
    "min_dep":    8,   # I
    "kpi":        9,   # J
    "wager":      10,  # K
    "baseline":   11,  # L
    "bonus":      12,  # M
    "postback":   13,  # N - пропускаем
    "c2r":        14,  # O
    "r2d":        15,  # P
    "slots":      16,  # Q
    "am":         17,  # R - конфиденциально
    "updated":    18,  # S
    "publish":    19,  # T
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════
# GOOGLE SHEETS
# ═══════════════════════════════════════════════════════
def get_sheet():
    import json
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if creds_json:
        creds_info = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    else:
        creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)

def get_requests_sheet():
    import json
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if creds_json:
        creds_info = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    else:
        creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(REQUESTS_SHEET_ID).worksheet(REQUESTS_SHEET_NAME)

def add_request(partner_id, username, source, geo, details, offer, rate, status):
    """Добавить запрос в таблицу запросов"""
    from datetime import datetime
    sheet = get_requests_sheet()
    today = datetime.now().strftime("%d.%m.%y")
    row = [partner_id, username, source, geo, "", details, offer, rate, status, "—", today, ""]
    # Найти первую пустую строку начиная с 7й
    all_values = sheet.get_all_values()
    next_row = len(all_values) + 1
    if next_row < 7:
        next_row = 7
    sheet.insert_row(row, next_row)

def get_all_rows():
    sheet = get_sheet()
    rows = sheet.get_all_values()
    return rows[6:]  # данные с 7й строки (индекс 6)

def update_publish_status(row_index, new_status):
    """row_index — 0-based индекс в массиве данных (без шапки)"""
    sheet = get_sheet()
    sheet_row = row_index + 7  # +7 потому что данные с 7й строки
    col_t = COL["publish"] + 1  # gspread 1-based
    sheet.update_cell(sheet_row, col_t, new_status)

# ═══════════════════════════════════════════════════════
# ФОРМАТИРОВАНИЕ ПОСТОВ
# ═══════════════════════════════════════════════════════
def format_geo(geo_str):
    """'GB, DE, FR' → '🇬🇧 🇩🇪 🇫🇷'"""
    if not geo_str or geo_str.strip() == "—":
        return ""
    geos = [g.strip().upper() for g in geo_str.replace(";", ",").split(",")]
    return " ".join(GEO_FLAGS.get(g, "") + " " for g in geos).strip()

def format_geo_hashtags(geo_str):
    """'GB, DE, FR' → '🇬🇧 #GB 🇩🇪 #DE 🇫🇷 #FR'"""
    if not geo_str or geo_str.strip() == "—":
        return ""
    geos = [g.strip().upper() for g in geo_str.replace(";", ",").split(",")]
    return " ".join(f"{GEO_FLAGS.get(g, '')} #{g}" for g in geos)

def val(row, key, default="—"):
    """Безопасно получить значение из строки"""
    idx = COL.get(key)
    if idx is None or idx >= len(row):
        return default
    v = str(row[idx]).strip()
    return v if v else default

def make_post(row, status):
    offer   = val(row, "offer")
    geo_raw = val(row, "geo")
    region  = val(row, "region")
    source  = val(row, "source")
    rate    = val(row, "rate")
    min_dep = val(row, "min_dep")
    wager   = val(row, "wager")
    kpi     = val(row, "kpi")
    baseline= val(row, "baseline")
    bonus   = val(row, "bonus")
    c2r     = val(row, "c2r")
    r2d     = val(row, "r2d")
    slots   = val(row, "slots")

    geo_flags    = format_geo(geo_raw)
    geo_hashtags = format_geo_hashtags(geo_raw)
    region_tag   = "#" + region.replace(" ", "").replace("/", "")

    # C2R / R2D
    c2r_str = f"{c2r}%" if c2r != "—" else "—%"
    r2d_str = f"{r2d}%" if r2d != "—" else "—%"

    status_clean = status.lower()

    if "hot" in status_clean:
        header = f"🎰 HOT OFFER | {offer}"
        extra = ""
        tags = f"{geo_hashtags} {region_tag} #hot #gambling"

    elif "эксклюзив" in status_clean:
        header = f"💎 ЭКСКЛЮЗИВ | {offer}"
        extra = "\n🔒 Только для партнёров сетки"
        tags = f"{geo_hashtags} {region_tag} #эксклюзив #gambling"

    elif "test" in status_clean or "тест" in status_clean:
        header = f"🔬 НОВЫЙ ТЕСТ | {offer}"
        extra = "\n📈 Конверт: уточняется\n⏳ Результаты через 3–5 дней"
        tags = f"{geo_hashtags} {region_tag} #тест #gambling"

    elif "paused" in status_clean or "пауза" in status_clean:
        return (
            f"⏸ ПАУЗА | {offer}\n\n"
            f"🗺 ГЕО: {geo_flags} | {region}\n\n"
            f"Оффер временно приостановлен\n"
            f"📩 Детали — у вашего менеджера\n"
            f"{geo_hashtags} {region_tag} #updates #пауза\n\n"
            f"THE PACE MEDIA 💙"
        )

    elif "стоп" in status_clean or "stop" in status_clean:
        return (
            f"🚫 СТОП | {offer}\n\n"
            f"🗺 ГЕО: {geo_flags} | {region}\n\n"
            f"Оффер снят с работы\n"
            f"📩 Детали — у вашего менеджера\n"
            f"{geo_hashtags} {region_tag} #updates #стоп\n\n"
            f"THE PACE MEDIA 💙"
        )

    else:  # Active
        header = f"✅ ОФФЕР | {offer}"
        extra = ""
        tags = f"{geo_hashtags} {region_tag} #gambling"

    # Слоты — только если есть
    slots_line = f"\n🎮 Топ слоты: {slots}" if slots != "—" else ""

    # C2R/R2D — только если не Test
    if "test" in status_clean or "тест" in status_clean:
        conv_line = extra
    else:
        conv_line = f"{extra}\n📈 C2R: {c2r_str} | R2D: {r2d_str}"

    post = (
        f"{header}\n\n"
        f"🗺 ГЕО: {geo_flags} | {region}\n"
        f"📡 Сорс: {source}\n"
        f"💵 Ставка: {rate}\n"
        f"💳 Мин деп: {min_dep} | Wager: x{wager}\n"
        f"🎯 KPI: {kpi} | Baseline: {baseline}\n"
        f"🎁 Бонус: {bonus}"
        f"{slots_line}"
        f"{conv_line}\n\n"
        f"📩 Для апрува / запроса капы — обратитесь к вашему менеджеру\n"
        f"{tags}\n\n"
        f"THE PACE MEDIA 💙"
    )
    return post

def make_analytics_post(rows):
    """Еженедельная аналитика"""
    active = [r for r in rows if "active" in val(r, "status").lower() or "hot" in val(r, "status").lower()]
    tests  = [r for r in rows if "test" in val(r, "status").lower()]
    new_this_week = []
    today = datetime.now()
    for r in rows:
        upd = val(r, "updated")
        try:
            d = datetime.strptime(upd, "%d.%m.%y")
            if (today - d).days <= 7:
                new_this_week.append(r)
        except:
            pass

    # Топ-3 по R2D
    def r2d_val(r):
        try: return float(val(r, "r2d").replace("%",""))
        except: return 0.0

    top3 = sorted(active, key=r2d_val, reverse=True)[:3]
    top_lines = ""
    for i, r in enumerate(top3, 1):
        geo_raw = val(r, "geo")
        geos = [g.strip().upper() for g in geo_raw.replace(";",",").split(",")]
        geo_str = " ".join(f"{GEO_FLAGS.get(g,'')} #{g}" for g in geos[:2])
        top_lines += f"{i}. {val(r,'offer')} — {geo_str} — C2R {val(r,'c2r')}% → R2D {val(r,'r2d')}%\n"

    date_str = today.strftime("%d.%m.%y")
    post = (
        f"📊 АНАЛИТИКА НЕДЕЛИ | {date_str}\n\n"
        f"🏆 Топ-3 по конверту:\n{top_lines}\n"
        f"🔥 Новых офферов за неделю: {len(new_this_week)}\n"
        f"✅ Активных: {len(active)}\n"
        f"🔬 В тесте: {len(tests)}\n\n"
        f"📩 Вопросы — к вашему менеджеру\n"
        f"#аналитика #weekly #gambling\n\n"
        f"THE PACE MEDIA 💙"
    )
    return post

# ═══════════════════════════════════════════════════════
# ОПРЕДЕЛИТЬ ТОПИК ДЛЯ ПУБЛИКАЦИИ
# ═══════════════════════════════════════════════════════
def get_topic(row, status):
    status_clean = status.lower()

    if "hot" in status_clean:
        return TOPICS["hot"]
    if "эксклюзив" in status_clean:
        return TOPICS["exclusive"]
    if "test" in status_clean or "тест" in status_clean:
        return TOPICS["new_tests"]
    if "paused" in status_clean or "пауза" in status_clean or "стоп" in status_clean or "stop" in status_clean:
        return TOPICS["updates"]

    # Active — по региону
    region = val(row, "region").lower().strip()
    return TOPICS.get(REGION_TO_TOPIC.get(region, ""), TOPICS["updates"])

# ═══════════════════════════════════════════════════════
# КОМАНДЫ БОТА (Часть 2)
# ═══════════════════════════════════════════════════════
async def handle_commands(bot, update_data):
    """Обработка команд партнёров в чатах"""
    if "message" not in update_data:
        return

    msg = update_data["message"]
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "").strip()

    if not text.startswith("/"):
        return

    parts = text.split(maxsplit=1)
    cmd = parts[0].lower().replace("@thepacemedia_offers_bot", "")
    arg = parts[1].strip() if len(parts) > 1 else ""

    rows = get_all_rows()
    active_rows = [r for r in rows if val(r, "publish") in ("📤 Posted",) and val(r, "status") not in ("⏸ Paused", "❌ Стоп", "🚫 Skip")]

    response = None

    # /top — топ-5 по R2D
    if cmd == "/top":
        def r2d_val(r):
            try: return float(val(r, "r2d").replace("%",""))
            except: return 0.0
        top5 = sorted(active_rows, key=r2d_val, reverse=True)[:5]
        if not top5:
            response = "Нет данных по конверту. Скоро обновим 👀"
        else:
            lines = []
            for i, r in enumerate(top5, 1):
                geo_raw = val(r, "geo")
                geos = [g.strip().upper() for g in geo_raw.replace(";",",").split(",")]
                flags = " ".join(GEO_FLAGS.get(g,"") for g in geos[:3])
                lines.append(f"{i}. {val(r,'offer')} — {flags} — C2R {val(r,'c2r')}% → R2D {val(r,'r2d')}%")
            response = "🏆 Топ-5 по конверту:\n\n" + "\n".join(lines) + "\n\n📩 Детали — у вашего менеджера\n\nTHE PACE MEDIA 💙"

    # /geo DE — топ по ГЕО
    elif cmd == "/geo" and arg:
        geo_filter = arg.upper()
        filtered = [r for r in active_rows if geo_filter in val(r, "geo").upper()]
        if not filtered:
            response = f"Нет активных офферов по ГЕО: {geo_filter}"
        else:
            flag = GEO_FLAGS.get(geo_filter, "")
            lines = []
            for r in filtered[:5]:
                lines.append(f"• {val(r,'offer')} — {val(r,'rate')} — {val(r,'source')}")
            response = f"📍 Офферы по {flag} #{geo_filter}:\n\n" + "\n".join(lines) + "\n\n📩 Детали — у вашего менеджера\n\nTHE PACE MEDIA 💙"

    # /region T1EU — топ по региону
    elif cmd == "/region" and arg:
        region_filter = arg.lower().replace("_", " ")
        filtered = [r for r in active_rows if region_filter in val(r, "region").lower()]
        if not filtered:
            response = f"Нет активных офферов по региону: {arg}"
        else:
            lines = []
            for r in filtered[:5]:
                geo_raw = val(r, "geo")
                geos = [g.strip().upper() for g in geo_raw.replace(";",",").split(",")]
                flags = " ".join(GEO_FLAGS.get(g,"") for g in geos[:3])
                lines.append(f"• {val(r,'offer')} — {flags} — {val(r,'rate')}")
            response = f"🗺 Офферы по региону {arg}:\n\n" + "\n".join(lines) + "\n\n📩 Детали — у вашего менеджера\n\nTHE PACE MEDIA 💙"

    # /cr LeoVegas — конверт по продукту
    elif cmd == "/cr" and arg:
        found = [r for r in active_rows if arg.lower() in val(r, "offer").lower()]
        if not found:
            response = f"Оффер не найден: {arg}"
        else:
            r = found[0]
            response = (
                f"📈 Конверт | {val(r,'offer')}\n\n"
                f"C2R: {val(r,'c2r')}%\n"
                f"R2D: {val(r,'r2d')}%\n"
                f"KPI: {val(r,'kpi')} | Baseline: {val(r,'baseline')}\n\n"
                f"📩 Детали — у вашего менеджера\n\nTHE PACE MEDIA 💙"
            )

    # /slots LeoVegas — топ слоты
    elif cmd == "/slots" and arg:
        found = [r for r in active_rows if arg.lower() in val(r, "offer").lower()]
        if not found:
            response = f"Оффер не найден: {arg}"
        else:
            r = found[0]
            response = (
                f"🎮 Топ слоты | {val(r,'offer')}\n\n"
                f"{val(r,'slots')}\n\n"
                f"📩 Детали — у вашего менеджера\n\nTHE PACE MEDIA 💙"
            )

    # /bonus LeoVegas — бонусы
    elif cmd == "/bonus" and arg:
        found = [r for r in active_rows if arg.lower() in val(r, "offer").lower()]
        if not found:
            response = f"Оффер не найден: {arg}"
        else:
            r = found[0]
            response = (
                f"🎁 Бонусы | {val(r,'offer')}\n\n"
                f"{val(r,'bonus')}\n\n"
                f"📩 Детали — у вашего менеджера\n\nTHE PACE MEDIA 💙"
            )

    # /source UAC T1EU — топ по сорсу и региону
    elif cmd == "/source" and arg:
        parts2 = arg.split(maxsplit=1)
        source_filter = parts2[0].upper()
        region_filter = parts2[1].lower() if len(parts2) > 1 else ""
        filtered = [r for r in active_rows if source_filter in val(r, "source").upper()]
        if region_filter:
            filtered = [r for r in filtered if region_filter in val(r, "region").lower()]
        if not filtered:
            response = f"Нет офферов по сорсу: {source_filter}"
        else:
            lines = []
            for r in filtered[:5]:
                geo_raw = val(r, "geo")
                geos = [g.strip().upper() for g in geo_raw.replace(";",",").split(",")]
                flags = " ".join(GEO_FLAGS.get(g,"") for g in geos[:2])
                lines.append(f"• {val(r,'offer')} — {flags} — {val(r,'rate')}")
            response = f"📡 Топ по {source_filter}:\n\n" + "\n".join(lines) + "\n\n📩 Детали — у вашего менеджера\n\nTHE PACE MEDIA 💙"

    # /kpi LeoVegas — KPI + Wager + Baseline
    elif cmd == "/kpi" and arg:
        found = [r for r in active_rows if arg.lower() in val(r, "offer").lower()]
        if not found:
            response = f"Оффер не найден: {arg}"
        else:
            r = found[0]
            response = (
                f"🎯 Условия | {val(r,'offer')}\n\n"
                f"KPI: {val(r,'kpi')}\n"
                f"Baseline: {val(r,'baseline')}\n"
                f"Wager: x{val(r,'wager')}\n"
                f"Мин деп: {val(r,'min_dep')}\n\n"
                f"📩 Детали — у вашего менеджера\n\nTHE PACE MEDIA 💙"
            )

    # /hot — все Hot офферы
    elif cmd == "/hot":
        filtered = [r for r in active_rows if "hot" in val(r, "status").lower()]
        if not filtered:
            response = "Нет Hot офферов прямо сейчас"
        else:
            lines = []
            for r in filtered[:5]:
                geo_raw = val(r, "geo")
                geos = [g.strip().upper() for g in geo_raw.replace(";",",").split(",")]
                flags = " ".join(GEO_FLAGS.get(g,"") for g in geos[:2])
                lines.append(f"🔥 {val(r,'offer')} — {flags} — {val(r,'rate')}")
            response = "🔥 Hot офферы сейчас:\n\n" + "\n".join(lines) + "\n\n📩 Детали — у вашего менеджера\n\nTHE PACE MEDIA 💙"

    # /excl — эксклюзивы
    elif cmd == "/excl":
        filtered = [r for r in active_rows if "эксклюзив" in val(r, "status").lower()]
        if not filtered:
            response = "Нет эксклюзивных офферов прямо сейчас"
        else:
            lines = []
            for r in filtered[:5]:
                geo_raw = val(r, "geo")
                geos = [g.strip().upper() for g in geo_raw.replace(";",",").split(",")]
                flags = " ".join(GEO_FLAGS.get(g,"") for g in geos[:2])
                lines.append(f"💎 {val(r,'offer')} — {flags} — {val(r,'rate')}")
            response = "💎 Эксклюзивные офферы:\n\n" + "\n".join(lines) + "\n\n🔒 Только для партнёров\n📩 Детали — у вашего менеджера\n\nTHE PACE MEDIA 💙"

    # /new — новые за 7 дней
    elif cmd == "/new":
        today = datetime.now()
        new_rows = []
        for r in active_rows:
            upd = val(r, "updated")
            try:
                d = datetime.strptime(upd, "%d.%m.%y")
                if (today - d).days <= 7:
                    new_rows.append(r)
            except:
                pass
        if not new_rows:
            response = "Нет новых офферов за последние 7 дней"
        else:
            lines = []
            for r in new_rows[:5]:
                geo_raw = val(r, "geo")
                geos = [g.strip().upper() for g in geo_raw.replace(";",",").split(",")]
                flags = " ".join(GEO_FLAGS.get(g,"") for g in geos[:2])
                lines.append(f"• {val(r,'offer')} — {flags} — {val(r,'rate')}")
            response = f"🆕 Новые офферы (7 дней):\n\n" + "\n".join(lines) + "\n\n📩 Детали — у вашего менеджера\n\nTHE PACE MEDIA 💙"

    # /find — быстрый поиск офферов
    elif cmd == "/find" and arg:
        parts_arg = arg.split(maxsplit=2)
        geo_or_region = parts_arg[0].upper() if parts_arg else ""
        source_filter = parts_arg[1].upper() if len(parts_arg) > 1 else ""
        condition = parts_arg[2].lower() if len(parts_arg) > 2 else ""

        filtered = []
        for r in active_rows:
            geo_match = geo_or_region in val(r, "geo").upper()
            region_match = geo_or_region.lower() in val(r, "region").lower()
            if geo_match or region_match:
                filtered.append(r)

        if source_filter:
            filtered = [r for r in filtered if source_filter in val(r, "source").upper() or val(r, "source") == "ALL"]

        if "без bl" in condition or "без baseline" in condition:
            filtered = [r for r in filtered if val(r, "baseline") in ("—", "", "0")]

        if not filtered:
            response = "❌ Офферов по запросу '" + arg + "' не найдено в базе\n\nTHE PACE MEDIA 💙"
        else:
            lines_list = []
            for r in filtered[:5]:
                geo_raw = val(r, "geo")
                geos = [g.strip().upper() for g in geo_raw.replace(";",",").split(",")]
                flags = " ".join(GEO_FLAGS.get(g,"") + " #" + g for g in geos[:3])
                lines_list.append("• " + val(r,"offer") + " | " + flags + " | " + val(r,"rate") + " | " + val(r,"source"))

            partner_list = []
            for r in filtered[:3]:
                geo_raw = val(r, "geo")
                geos = [g.strip().upper() for g in geo_raw.replace(";",",").split(",")]
                flags = " ".join(GEO_FLAGS.get(g,"") + " #" + g for g in geos[:3])
                partner_list.append("🌍 " + val(r,"offer") + " | " + flags + " | " + val(r,"rate") + " | " + val(r,"source"))

            response = (
                "📍 Найдено по '" + arg + "': " + str(len(filtered)) + " оффер(ов)\n\n"
                + "\n".join(lines_list)
                + "\n\n📋 Готовый ответ партнёру 👇\n——————\n"
                + "\n".join(partner_list)
                + "\n📩 Детали — у вашего менеджера\nTHE PACE MEDIA 💙"
            )

    # /req — зафиксировать запрос + найти оффер
    elif cmd == "/req" and arg:
        req_parts = [p.strip() for p in arg.split("|")]
        partner_id = req_parts[0] if len(req_parts) > 0 else "—"
        username   = req_parts[1] if len(req_parts) > 1 else "—"
        source     = req_parts[2].upper() if len(req_parts) > 2 else "—"
        geo        = req_parts[3].upper() if len(req_parts) > 3 else "—"
        details    = req_parts[4] if len(req_parts) > 4 else "—"

        filtered = []
        for r in active_rows:
            geo_match = geo in val(r, "geo").upper()
            region_match = geo.lower() in val(r, "region").lower()
            if geo_match or region_match:
                filtered.append(r)
        if source and source != "—":
            filtered = [r for r in filtered if source in val(r, "source").upper() or val(r, "source") == "ALL"]
        if "без bl" in details.lower():
            filtered = [r for r in filtered if val(r, "baseline") in ("—", "", "0")]

        if filtered:
            status_req = "✅ Закрыт"
            offer_name = val(filtered[0], "offer")
            offer_rate = val(filtered[0], "rate")

            partner_list = []
            for r in filtered[:3]:
                geo_raw = val(r, "geo")
                geos = [g.strip().upper() for g in geo_raw.replace(";",",").split(",")]
                flags = " ".join(GEO_FLAGS.get(g,"") + " #" + g for g in geos[:3])
                partner_list.append("🌍 " + val(r,"offer") + " | " + flags + " | " + val(r,"rate") + " | " + val(r,"source"))

            response = (
                "✅ Запрос " + partner_id + " зафиксирован | " + username + "\n\n"
                + "Найдено " + str(len(filtered)) + " оффер(ов) по " + geo + "/" + source + ":\n\n"
                + "\n".join("• " + val(r,"offer") + " | " + val(r,"rate") for r in filtered[:5])
                + "\n\n📋 Готовый ответ партнёру 👇\n——————\n"
                + "\n".join(partner_list)
                + "\n📩 Детали — у вашего менеджера\nTHE PACE MEDIA 💙"
            )
        else:
            status_req = "🔍 В поиске"
            offer_name = "—"
            offer_rate = "—"
            response = (
                "❌ Офферов по " + geo + "/" + source + " нет в базе\n\n"
                + "📋 Запрос " + partner_id + " зафиксирован → в поиск\n"
                + "👤 " + username + " | " + source + " | " + geo + " | " + details + "\n\n"
                + "THE PACE MEDIA 💙"
            )

        try:
            add_request(partner_id, username, source, geo, details, offer_name, offer_rate, status_req)
            log.info("Запрос зафиксирован: " + partner_id + " " + username + " " + geo)
        except Exception as e:
            log.error("Ошибка записи запроса: " + str(e))

    # /help
    elif cmd == "/help":
        response = (
            "📋 Команды THE PACE MEDIA бота:\n\n"
            "/top — топ-5 по конверту\n"
            "/hot — все Hot офферы\n"
            "/excl — эксклюзивные офферы\n"
            "/new — новые за 7 дней\n"
            "/geo [код] — офферы по ГЕО\n"
            "   пример: /geo DE\n"
            "/region [регион] — офферы по региону\n"
            "   пример: /region T1EU\n"
            "/cr [оффер] — конверт по продукту\n"
            "   пример: /cr CasinOK\n"
            "/slots [оффер] — топ слоты\n"
            "   пример: /slots CasinOK\n"
            "/bonus [оффер] — бонусы\n"
            "   пример: /bonus CasinOK\n"
            "/source [сорс] [регион] — по сорсу\n"
            "   пример: /source UAC T1EU\n"
            "/kpi [оффер] — условия оффера\n"
            "   пример: /kpi CasinOK\n\n"
            "🔍 Для менеджеров:\n"
            "/find [гео/регион] [сорс] — быстрый поиск\n"
            "   пример: /find ZM FB\n"
            "/req [#id] | [@user] | [сорс] | [гео] | [детали]\n"
            "   пример: /req #0101 | @username | FB | ZM | без BL\n\n"
            "THE PACE MEDIA 💙"
        )

    if response:
        try:
            await bot.send_message(chat_id=chat_id, text=response)
        except TelegramError as e:
            log.error(f"Ошибка отправки команды: {e}")

# ═══════════════════════════════════════════════════════
# ОСНОВНОЙ ЦИКЛ
# ═══════════════════════════════════════════════════════
async def check_and_publish(bot):
    log.info("Проверяю таблицу...")
    try:
        rows = get_all_rows()
    except Exception as e:
        log.error(f"Ошибка чтения таблицы: {e}")
        return

    for i, row in enumerate(rows):
        if len(row) < 20:
            continue

        publish = val(row, "publish").strip()
        status  = val(row, "status").strip()
        offer   = val(row, "offer").strip()

        if not offer or offer == "—":
            continue

        # Публикуем если Publish = ✅ Publish
        if publish == "✅ Publish":
            try:
                post = make_post(row, status)
                topic = get_topic(row, status)

                offer_name = val(row, "offer")
                # Только полный пост в нужную ветку — шапка от Telegram автоматически
                await bot.send_message(
                    chat_id=CHANNEL_ID,
                    message_thread_id=topic,
                    text=post,
                )
                update_publish_status(i, "📤 Posted")
                log.info(f"Опубликован: {offer_name} → топик {topic}")
                await asyncio.sleep(2)  # пауза между постами

            except TelegramError as e:
                log.error(f"Ошибка публикации {offer}: {e}")

        # Если статус сменился на Paused/Стоп и было Posted
        elif publish == "📤 Posted" and any(s in status.lower() for s in ["paused", "пауза", "стоп", "stop", "❌"]):
            try:
                post = make_post(row, status)
                await bot.send_message(
                    chat_id=CHANNEL_ID,
                    message_thread_id=TOPICS["updates"],
                    text=post,
                )
                update_publish_status(i, "🚫 Skip")
                log.info(f"Стоп/Пауза отправлен: {offer}")
                await asyncio.sleep(2)

            except TelegramError as e:
                log.error(f"Ошибка отправки стопа {offer}: {e}")

async def weekly_analytics(bot):
    """Отправляет аналитику каждый понедельник в 10:00"""
    while True:
        now = datetime.now()
        # Следующий понедельник 10:00
        days_until_monday = (7 - now.weekday()) % 7 or 7
        next_monday = now.replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=days_until_monday)
        wait_seconds = (next_monday - now).total_seconds()
        log.info(f"Аналитика через {wait_seconds/3600:.1f} часов")
        await asyncio.sleep(wait_seconds)

        try:
            rows = get_all_rows()
            post = make_analytics_post(rows)
            await bot.send_message(
                chat_id=CHANNEL_ID,
                message_thread_id=TOPICS["analytics"],
                text=post,
            )
            log.info("Еженедельная аналитика отправлена")
        except Exception as e:
            log.error(f"Ошибка аналитики: {e}")

async def poll_commands(bot, offset=0):
    """Polling для команд партнёров"""
    while True:
        try:
            updates = await bot.get_updates(offset=offset, timeout=30)
            for update in updates:
                offset = update.update_id + 1
                await handle_commands(bot, update.to_dict())
        except TelegramError as e:
            log.error(f"Polling error: {e}")
            await asyncio.sleep(5)

async def main():
    bot = Bot(token=BOT_TOKEN)
    me = await bot.get_me()
    log.info(f"Бот запущен: @{me.username}")

    # Запускаем все задачи параллельно
    await asyncio.gather(
        # Проверка таблицы каждые 5 минут
        asyncio.create_task(run_interval(bot)),
        # Еженедельная аналитика
        asyncio.create_task(weekly_analytics(bot)),
        # Обработка команд
        asyncio.create_task(poll_commands(bot)),
    )

async def run_interval(bot):
    while True:
        await check_and_publish(bot)
        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())

"""Telegram-бот: поиск вакансий и Ausbildung через API Arbeitsagentur."""
from __future__ import annotations

import asyncio
import difflib
import html
import logging

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import arbeitsagentur as aa
import translate
from config import Config
from storage import Storage, Subscription

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("jobs-bot")

_MAX_RESULTS = 5
_PAGE_SIZE = 5
_MAX_MSG_CHARS = 3500

# Подсказки-профессии для кнопок: (подпись, ключевое слово для API).
CATEGORIES: list[tuple[str, str]] = [
    ("💻 IT", "Informatik"),
    ("🛒 Verkauf", "Verkäufer"),
    ("📦 Lager", "Lager"),
    ("🩺 Pflege", "Pflege"),
    ("🍳 Gastro", "Koch"),
    ("🔧 Handwerk", "Elektroniker"),
    ("🏢 Büro", "Kaufmann"),
    ("🧒 Erzieher", "Erzieher"),
]

# Порядок кнопок типа занятости.
AZ_ORDER: list[str] = ["vz", "tz", "ho", "mj", "snw"]

# Подписи постоянной нижней клавиатуры (перехватываются в on_text).
BTN_SEARCH = "🔍 Поиск вакансий"
BTN_AUSB = "🎓 Ausbildung"
BTN_SUBS = "🔔 Мои подписки"
BTN_HELP = "❓ Команды"

# Команды для меню бота (кнопка «/» рядом с полем ввода).
BOT_COMMANDS: list[tuple[str, str]] = [
    ("start", "Меню и помощь"),
    ("search", "Поиск вакансий: /search слова"),
    ("ausbildung", "Поиск Ausbildung: /ausbildung слова"),
    ("watch", "Подписка на новые: /watch job|ausbildung слова"),
    ("list", "Мои подписки"),
    ("unwatch", "Удалить подписку: /unwatch номер"),
]


def _reply_kb() -> ReplyKeyboardMarkup:
    """Постоянная клавиатура снизу с быстрым доступом."""
    return ReplyKeyboardMarkup(
        [[BTN_SEARCH, BTN_AUSB], [BTN_SUBS, BTN_HELP]],
        resize_keyboard=True,
        is_persistent=True,
    )

# Словарь профессий: алиас (рус/нем, в нижнем регистре) -> немецкий запрос для API.
# Используется для перевода с русского и исправления опечаток.
SYNONYMS: dict[str, str] = {
    # IT
    "it": "Informatik", "айти": "Informatik", "программист": "Informatik",
    "informatik": "Informatik", "информатик": "Informatik",
    "fachinformatiker": "Fachinformatiker", "разработчик": "Informatik",
    # Продажи
    "продавец": "Verkäufer", "verkäufer": "Verkäufer", "verkaufer": "Verkäufer",
    "кассир": "Verkäufer", "verkauf": "Verkäufer",
    # Склад/логистика
    "склад": "Lager", "lager": "Lager", "грузчик": "Lager",
    "логистика": "Lager", "кладовщик": "Lager",
    # Уход/медицина
    "уход": "Pflege", "pflege": "Pflege", "медсестра": "Pflege",
    "санитар": "Pflege", "сиделка": "Pflege",
    # Гастрономия
    "повар": "Koch", "koch": "Koch", "кух": "Koch", "кухня": "Koch",
    "официант": "Kellner", "kellner": "Kellner",
    "пекарь": "Bäcker", "bäcker": "Bäcker", "baecker": "Bäcker",
    # Ремесло/техника
    "электрик": "Elektroniker", "электроник": "Elektroniker",
    "elektroniker": "Elektroniker", "elektriker": "Elektroniker",
    "сварщик": "Schweißer", "schweißer": "Schweißer", "schweisser": "Schweißer",
    "механик": "Mechaniker", "mechaniker": "Mechaniker",
    "слесарь": "Mechaniker", "автомеханик": "Kfz-Mechatroniker",
    # Офис
    "офис": "Kaufmann", "бухгалтер": "Kaufmann", "kaufmann": "Kaufmann",
    "кауфман": "Kaufmann", "kauffrau": "Kauffrau", "менеджер": "Kaufmann",
    # Воспитание
    "воспитатель": "Erzieher", "erzieher": "Erzieher", "педагог": "Erzieher",
    # Транспорт
    "водитель": "Berufskraftfahrer", "шофер": "Berufskraftfahrer",
    "kraftfahrer": "Berufskraftfahrer", "дальнобойщик": "Berufskraftfahrer",
    # Красота
    "парикмахер": "Friseur", "friseur": "Friseur",
    "косметолог": "Kosmetiker",
    # Офисные/экономические
    "экономист": "Betriebswirt", "юрист": "Jurist", "адвокат": "Rechtsanwalt",
    "маркетолог": "Marketing", "бухгалтерия": "Buchhaltung",
    "секретарь": "Sekretär", "ассистент": "Assistent",
    # Инженерия/техника
    "инженер": "Ingenieur", "конструктор": "Konstrukteur",
    "сантехник": "Anlagenmechaniker", "строитель": "Bau",
    "маляр": "Maler", "плотник": "Tischler", "столяр": "Tischler",
    # Медицина
    "врач": "Arzt", "доктор": "Arzt", "медбрат": "Pflege",
    "стоматолог": "Zahnarzt", "фармацевт": "Apotheker", "аптекарь": "Apotheker",
    # Образование/языки
    "учитель": "Lehrer", "преподаватель": "Lehrer",
    "переводчик": "Übersetzer", "дизайнер": "Designer",
    # Сервис/прочее
    "охранник": "Sicherheit", "уборщик": "Reinigung", "уборщица": "Reinigung",
    "садовник": "Gärtner", "курьер": "Kurier", "почтальон": "Zusteller",
    "архитектор": "Architekt", "менеджер": "Manager",
}


def _resolve_query(text: str) -> tuple[str, str | None]:
    """Приводит ввод к немецкому запросу.

    Возвращает (запрос_для_API, пояснение_или_None). Пояснение задаётся,
    если мы перевели слово или исправили опечатку.
    """
    raw = text.strip()
    low = raw.lower()
    if low in SYNONYMS:
        german = SYNONYMS[low]
        note = None if german.lower() == low else f"Понял как: «{german}»"
        return german, note
    match = difflib.get_close_matches(low, list(SYNONYMS), n=1, cutoff=0.72)
    if match:
        german = SYNONYMS[match[0]]
        return german, f"Похоже, имелось в виду «{german}». Ищу его."
    return raw, None


async def _resolve_query_full(text: str) -> tuple[str, str | None]:
    """Словарь как быстрый путь, иначе авто-перевод RU->DE для кириллицы."""
    german, note = _resolve_query(text)
    if note is not None:
        return german, note
    # Слова нет в словаре. Если это кириллица — пробуем перевести на немецкий.
    if translate.has_cyrillic(german):
        translated = await translate.translate_ru_de(german)
        if translated:
            return translated, f"Перевёл на немецкий: «{translated}»"
    return german, None

HELP_TEXT = (
    "<b>Бот поиска вакансий и Ausbildung</b>\n"
    "Источник: Bundesagentur für Arbeit.\n\n"
    "Проще всего — нажми кнопку ниже и выбирай мышкой.\n\n"
    "<b>Команды (для тех, кто любит печатать):</b>\n"
    "/search <i>слова</i> — разовый поиск вакансий\n"
    "/ausbildung <i>слова</i> — разовый поиск Ausbildung\n"
    "/watch job|ausbildung <i>слова</i> — подписка (проверка раз в час)\n"
    "/list — мои подписки\n"
    "/unwatch <i>номер</i> — удалить подписку (номер из /list)\n\n"
    "<b>Фильтр по занятости</b> — допиши через <code>|</code>:\n"
    "<code>vz</code> Vollzeit, <code>tz</code> Teilzeit, "
    "<code>ho</code> Homeoffice, <code>mj</code> Minijob, "
    "<code>snw</code> смена/ночь/выходные\n"
    "Пример: <code>/search Fachinformatiker | vz tz</code>"
)


def _parse_query_and_times(text: str) -> tuple[str | None, str | None, list[str]]:
    """Делит строку на ключевые слова и фильтр занятости (после '|')."""
    left, sep, right = text.partition("|")
    query = left.strip() or None
    if not sep:
        return query, None, []
    codes, invalid = aa.normalize_arbeitszeit(right.split())
    return query, codes, invalid


def _times_label(arbeitszeit: str | None) -> str:
    if not arbeitszeit:
        return ""
    names = [aa.ARBEITSZEIT_LABELS.get(code, code) for code in arbeitszeit.split(";")]
    return ", ".join(names)


def _is_allowed(config: Config, update: Update) -> bool:
    chat = update.effective_chat
    return chat is not None and chat.id in config.allowed_chat_ids


def _offer_label(offer_type: int) -> str:
    return "Ausbildung" if offer_type == int(aa.OfferType.AUSBILDUNG) else "вакансии"


def _state(context: ContextTypes.DEFAULT_TYPE) -> dict:
    """Текущий выбор пользователя для кнопочного меню (в памяти процесса)."""
    return context.user_data.setdefault(
        "search",
        {"offer_type": int(aa.OfferType.JOB), "arbeitszeit": [], "query": None},
    )


def _state_times(state: dict) -> str | None:
    codes = state.get("arbeitszeit") or []
    return ";".join(codes) if codes else None


def _kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("💼 Вакансии", callback_data="type:1"),
                InlineKeyboardButton("🎓 Ausbildung", callback_data="type:4"),
            ],
            [InlineKeyboardButton("🔔 Мои подписки", callback_data="act:list")],
        ]
    )


def _kb_search(state: dict) -> InlineKeyboardMarkup:
    selected_query = state.get("query")
    az = set(state.get("arbeitszeit") or [])

    rows: list[list[InlineKeyboardButton]] = []
    cat_row: list[InlineKeyboardButton] = []
    for idx, (label, keyword) in enumerate(CATEGORIES):
        mark = "✅ " if selected_query == keyword else ""
        cat_row.append(
            InlineKeyboardButton(mark + label, callback_data=f"cat:{idx}")
        )
        if len(cat_row) == 2:
            rows.append(cat_row)
            cat_row = []
    if cat_row:
        rows.append(cat_row)

    az_row: list[InlineKeyboardButton] = []
    for code in AZ_ORDER:
        mark = "✅ " if code in az else "▫️ "
        az_row.append(
            InlineKeyboardButton(
                mark + aa.ARBEITSZEIT_LABELS[code], callback_data=f"az:{code}"
            )
        )
        if len(az_row) == 3:
            rows.append(az_row)
            az_row = []
    if az_row:
        rows.append(az_row)

    rows.append(
        [
            InlineKeyboardButton("🔍 Искать все", callback_data="act:search"),
            InlineKeyboardButton("🆕 Только свежие", callback_data="act:fresh"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                "🔔 Следить за новыми (раз в час)", callback_data="act:watch"
            )
        ]
    )
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="nav:main")])
    return InlineKeyboardMarkup(rows)


def _kb_results(shown: int, total: int) -> InlineKeyboardMarkup:
    """Компактная панель под результатами: ещё / следить / новый поиск."""
    rows: list[list[InlineKeyboardButton]] = []
    if shown < total:
        remaining = total - shown
        more = min(_PAGE_SIZE, remaining)
        rows.append(
            [
                InlineKeyboardButton(
                    f"➡️ Показать ещё {more} (осталось {remaining})",
                    callback_data="more",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                "🔔 Следить за новыми (раз в час)", callback_data="act:watch"
            )
        ]
    )
    rows.append([InlineKeyboardButton("🔍 Новый поиск", callback_data="nav:main")])
    return InlineKeyboardMarkup(rows)


def _search_title(state: dict) -> str:
    parts = [f"Тип: <b>{_offer_label(state['offer_type'])}</b>"]
    if state.get("query"):
        parts.append(f"Профессия: <b>{html.escape(state['query'])}</b>")
    times = _state_times(state)
    if times:
        parts.append(f"Занятость: <b>{html.escape(_times_label(times))}</b>")
    parts.append(
        "\nВыбери профессию или напиши запрос текстом, затем:\n"
        "• «🔍 Искать все» — все подходящие вакансии;\n"
        "• «🆕 Только свежие» — лишь опубликованные за последние дни."
    )
    return "\n".join(parts)


def _format_listing(listing: aa.JobListing) -> str:
    return (
        f"<b>{html.escape(listing.title)}</b>\n"
        f"🏢 {html.escape(listing.employer)}\n"
        f"📍 {html.escape(listing.city)}  ·  🗓 {html.escape(listing.published)}\n"
        f"🔗 {html.escape(listing.url)}"
    )


def _chunk_messages(blocks: list[str]) -> list[str]:
    messages: list[str] = []
    current = ""
    for block in blocks:
        candidate = block if not current else f"{current}\n\n{block}"
        if len(candidate) > _MAX_MSG_CHARS and current:
            messages.append(current)
            current = block
        else:
            current = candidate
    if current:
        messages.append(current)
    return messages


async def _send_listings(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    listings: list[aa.JobListing],
) -> None:
    blocks = [_format_listing(item) for item in listings]
    for message in _chunk_messages(blocks):
        await context.bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )


def _config(context: ContextTypes.DEFAULT_TYPE) -> Config:
    return context.application.bot_data["config"]


def _storage(context: ContextTypes.DEFAULT_TYPE) -> Storage:
    return context.application.bot_data["storage"]


async def _run_search(
    context: ContextTypes.DEFAULT_TYPE,
    what: str | None,
    offer_type: aa.OfferType,
    arbeitszeit: str | None = None,
    *,
    since_days: int | None = None,
) -> list[aa.JobListing]:
    config = _config(context)
    if since_days is None:
        since_days = (
            config.ausbildung_since_days
            if offer_type == aa.OfferType.AUSBILDUNG
            else config.published_since_days
        )
    return await aa.search(
        what=what,
        where=config.default_city,
        offer_type=offer_type,
        radius_km=config.default_radius_km,
        published_since_days=since_days,
        arbeitszeit=arbeitszeit or config.default_arbeitszeit or None,
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(_config(context), update):
        return
    await update.message.reply_html(HELP_TEXT, reply_markup=_reply_kb())
    await update.message.reply_text("Что ищем?", reply_markup=_kb_main())


async def _send_results_page(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int
) -> None:
    """Отправляет следующую страницу (5 шт.) из сохранённых результатов поиска."""
    results = context.user_data.get("results")
    if not results or not results.get("listings"):
        await context.bot.send_message(chat_id, "Сначала выполни поиск.")
        return
    listings: list[aa.JobListing] = results["listings"]
    total = len(listings)
    offset: int = results.get("offset", 0)
    page = listings[offset:offset + _PAGE_SIZE]
    if not page:
        return
    await _send_listings(context, chat_id, page)
    shown = offset + len(page)
    results["offset"] = shown
    if shown < total:
        text = f"Показано {shown} из {total}."
    else:
        text = f"Это всё ({total})."
    await context.bot.send_message(
        chat_id, text, reply_markup=_kb_results(shown, total)
    )


async def _search_and_send(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    what: str | None,
    offer_type: aa.OfferType,
    times: str | None,
    *,
    fresh: bool = False,
) -> None:
    """Выполняет поиск, сохраняет результаты и показывает первую страницу.

    fresh=True использует узкое окно подписки (только свежие объявления).
    """
    config = _config(context)
    since_days = config.subscription_since_days if fresh else None
    suffix = f" ({_times_label(times)})" if times else ""
    if fresh:
        await context.bot.send_message(
            chat_id,
            f"Ищу свежие {_offer_label(int(offer_type))} за последние "
            f"{config.subscription_since_days} дн. в {config.default_city}{suffix}…",
        )
    else:
        await context.bot.send_message(
            chat_id,
            f"Ищу {_offer_label(int(offer_type))} в {config.default_city}{suffix}…",
        )
    try:
        listings = await _run_search(
            context, what, offer_type, times, since_days=since_days
        )
    except aa.ArbeitsagenturError:
        await context.bot.send_message(
            chat_id, "Не удалось получить данные от сервиса. Попробуй позже."
        )
        return
    if not listings:
        tips = ["😕 Ничего не найдено. Что можно сделать:"]
        if fresh:
            tips.append("• нажать «🔍 Искать все» — окно свежести узкое")
        tips.append("• ввести профессию по-немецки (например, Manager, Betriebswirt)")
        if times:
            tips.append("• убрать фильтр занятости — он сужает выдачу")
        tips.append("• попробовать более общее слово")
        tips.append("• /start — начать заново")
        await context.bot.send_message(chat_id, "\n".join(tips))
        return
    context.user_data["results"] = {"listings": listings, "offset": 0}
    found = (
        f"🆕 Найдено свежих (за {config.subscription_since_days} дн.): {len(listings)}."
        if fresh
        else f"Найдено: {len(listings)}."
    )
    await context.bot.send_message(chat_id, found)
    await _send_results_page(context, chat_id)


async def _create_subscription(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    offer_type: aa.OfferType,
    query: str | None,
    times: str | None,
) -> tuple[int, list[aa.JobListing], bool]:
    """Создаёт подписку и помечает текущие результаты как уже показанные.

    Возвращает (id, listings, created). Если идентичная подписка уже есть,
    created=False и повторного поиска/пометки не делаем (защита от дублей).
    """
    storage = _storage(context)
    sub_id, created = await asyncio.to_thread(
        storage.add_subscription, chat_id, int(offer_type), query or "", times or ""
    )
    if not created:
        return sub_id, [], False
    try:
        listings = await _run_search(
            context,
            query,
            offer_type,
            times,
            since_days=_config(context).subscription_since_days,
        )
    except aa.ArbeitsagenturError:
        listings = []
    await asyncio.to_thread(storage.mark_seen, sub_id, [i.refnr for i in listings])
    return sub_id, listings, True


async def _subscription_number(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, sub_id: int
) -> int:
    """Порядковый номер подписки для пользователя (1, 2, 3…), не внутренний id."""
    subs = await asyncio.to_thread(_storage(context).list_subscriptions, chat_id)
    for number, sub in enumerate(subs, start=1):
        if sub.id == sub_id:
            return number
    return len(subs)


async def _handle_search(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    offer_type: aa.OfferType,
) -> None:
    config = _config(context)
    if not _is_allowed(config, update):
        return
    what, times, invalid = _parse_query_and_times(" ".join(context.args or []))
    if invalid:
        await update.message.reply_text(
            "Неизвестный тип занятости: " + ", ".join(invalid) + ". "
            "Допустимо: vz, tz, ho, mj, snw."
        )
        return
    chat_id = update.effective_chat.id
    if what:
        what, note = await _resolve_query_full(what)
        if note:
            await context.bot.send_message(chat_id, note)
    await _search_and_send(context, chat_id, what, offer_type, times)


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _handle_search(update, context, aa.OfferType.JOB)


async def ausbildung_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _handle_search(update, context, aa.OfferType.AUSBILDUNG)


async def watch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config = _config(context)
    if not _is_allowed(config, update):
        return
    if not context.args:
        await update.message.reply_text(
            "Формат: /watch job|ausbildung <ключевые слова>"
        )
        return
    kind = context.args[0].lower()
    if kind not in ("job", "ausbildung"):
        await update.message.reply_text("Первый аргумент: job или ausbildung.")
        return
    offer_type = aa.OfferType.AUSBILDUNG if kind == "ausbildung" else aa.OfferType.JOB
    query, times, invalid = _parse_query_and_times(" ".join(context.args[1:]))
    if invalid:
        await update.message.reply_text(
            "Неизвестный тип занятости: " + ", ".join(invalid) + ". "
            "Допустимо: vz, tz, ho, mj, snw."
        )
        return
    chat_id = update.effective_chat.id
    if query:
        query, note = await _resolve_query_full(query)
        if note:
            await context.bot.send_message(chat_id, note)
    sub_id, listings, created = await _create_subscription(
        context, chat_id, offer_type, query, times
    )
    number = await _subscription_number(context, chat_id, sub_id)
    if not created:
        await update.message.reply_html(
            _subscription_exists_card(number, offer_type, query, times)
        )
        return
    await update.message.reply_html(
        _subscription_card(
            _config(context), number, offer_type, query, times, len(listings)
        )
    )
    if listings:
        await _send_listings(context, chat_id, listings[:_MAX_RESULTS])


def _subscription_card(
    config: Config,
    number: int,
    offer_type: aa.OfferType,
    query: str | None,
    times: str | None,
    count: int,
) -> str:
    """Наглядная карточка: на что именно оформлена подписка."""
    return "\n".join(
        [
            "✅ <b>Подписка оформлена</b>",
            "",
            f"📌 Тип: <b>{_offer_label(int(offer_type))}</b>",
            f"💼 Профессия: <b>{html.escape(query) if query else 'любая'}</b>",
            f"🕒 Занятость: <b>{_times_label(times) if times else 'любая'}</b>",
            f"📍 Город: <b>{html.escape(config.default_city)}</b> "
            f"({config.default_radius_km} км)",
            "",
            f"🔁 Проверяю раз в час — пришлю только новое. Сейчас актуально: <b>{count}</b>",
            f"🗑 Удалить: /unwatch {number}",
        ]
    )


def _subscription_exists_card(
    number: int,
    offer_type: aa.OfferType,
    query: str | None,
    times: str | None,
) -> str:
    """Сообщение, когда такая подписка уже есть — без создания дубля."""
    return "\n".join(
        [
            "ℹ️ <b>Такая подписка уже есть</b> — дубликат не создаю.",
            "",
            f"📌 Тип: <b>{_offer_label(int(offer_type))}</b>",
            f"💼 Профессия: <b>{html.escape(query) if query else 'любая'}</b>",
            f"🕒 Занятость: <b>{_times_label(times) if times else 'любая'}</b>",
            "",
            f"🗑 Удалить: /unwatch {number}",
        ]
    )


def _subscriptions_text(subs: list[Subscription]) -> str:
    if not subs:
        return "Подписок нет. Создай кнопкой «🔔 Подписаться» или командой /watch."
    lines = []
    for number, sub in enumerate(subs, start=1):
        line = f"№{number}: {_offer_label(sub.offer_type)}"
        if sub.query:
            line += f" · «{html.escape(sub.query)}»"
        if sub.arbeitszeit:
            line += f" · {html.escape(_times_label(sub.arbeitszeit))}"
        line += f"   (удалить: /unwatch {number})"
        lines.append(line)
    return "<b>Подписки:</b>\n" + "\n".join(lines)


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config = _config(context)
    if not _is_allowed(config, update):
        return
    chat_id = update.effective_chat.id
    subs = await asyncio.to_thread(_storage(context).list_subscriptions, chat_id)
    await update.message.reply_html(_subscriptions_text(subs))


async def unwatch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config = _config(context)
    if not _is_allowed(config, update):
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Формат: /unwatch <номер> (см. /list).")
        return
    number = int(context.args[0])
    chat_id = update.effective_chat.id
    storage = _storage(context)
    subs = await asyncio.to_thread(storage.list_subscriptions, chat_id)
    if not 1 <= number <= len(subs):
        await update.message.reply_text("Нет подписки с таким номером. См. /list.")
        return
    removed = await asyncio.to_thread(
        storage.remove_subscription, chat_id, subs[number - 1].id
    )
    if removed:
        await update.message.reply_text(f"Подписка №{number} удалена.")
    else:
        await update.message.reply_text("Не удалось удалить. См. /list.")


async def _refresh_search_screen(query, state: dict) -> None:
    """Перерисовывает экран поиска; молча игнорирует 'message is not modified'."""
    try:
        await query.edit_message_text(
            _search_title(state),
            parse_mode=ParseMode.HTML,
            reply_markup=_kb_search(state),
        )
    except BadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise


async def _close_old_menu(query) -> None:
    """Убирает кнопки у использованного сообщения, чтобы не было дублей меню."""
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except BadRequest:
        pass


async def _send_search_menu(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, state: dict
) -> None:
    """Присылает свежее меню снизу, чтобы не листать вверх к старому."""
    await context.bot.send_message(
        chat_id,
        _search_title(state),
        parse_mode=ParseMode.HTML,
        reply_markup=_kb_search(state),
    )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not _is_allowed(_config(context), update):
        await query.answer("Нет доступа.", show_alert=True)
        return
    await query.answer()
    data = query.data or ""
    state = _state(context)
    chat_id = query.message.chat_id

    if data == "nav:main":
        await query.edit_message_text("Что ищем?", reply_markup=_kb_main())
        return

    if data == "more":
        await _close_old_menu(query)
        await _send_results_page(context, chat_id)
        return

    if data.startswith("type:"):
        state["offer_type"] = int(data.split(":", 1)[1])
        state["query"] = None
        await _refresh_search_screen(query, state)
        return

    if data.startswith("az:"):
        code = data.split(":", 1)[1]
        codes = state["arbeitszeit"]
        if code in codes:
            codes.remove(code)
        else:
            codes.append(code)
        await _refresh_search_screen(query, state)
        return

    if data.startswith("cat:"):
        idx = int(data.split(":", 1)[1])
        _, keyword = CATEGORIES[idx]
        state["query"] = keyword
        await _close_old_menu(query)
        await _search_and_send(
            context, chat_id, keyword, aa.OfferType(state["offer_type"]),
            _state_times(state),
        )
        return

    if data == "act:search":
        await _close_old_menu(query)
        await _search_and_send(
            context, chat_id, state.get("query"),
            aa.OfferType(state["offer_type"]), _state_times(state),
        )
        return

    if data == "act:fresh":
        await _close_old_menu(query)
        await _search_and_send(
            context, chat_id, state.get("query"),
            aa.OfferType(state["offer_type"]), _state_times(state),
            fresh=True,
        )
        return

    if data == "act:watch":
        offer_type = aa.OfferType(state["offer_type"])
        times = _state_times(state)
        await _close_old_menu(query)
        sub_id, listings, created = await _create_subscription(
            context, chat_id, offer_type, state.get("query"), times
        )
        number = await _subscription_number(context, chat_id, sub_id)
        if created:
            card = _subscription_card(
                _config(context), number, offer_type,
                state.get("query"), times, len(listings),
            )
        else:
            card = _subscription_exists_card(
                number, offer_type, state.get("query"), times
            )
        await context.bot.send_message(
            chat_id, card, parse_mode=ParseMode.HTML
        )
        await _send_search_menu(context, chat_id, state)
        return

    if data == "act:list":
        subs = await asyncio.to_thread(
            _storage(context).list_subscriptions, chat_id
        )
        await context.bot.send_message(
            chat_id, _subscriptions_text(subs), parse_mode=ParseMode.HTML
        )
        await _send_search_menu(context, chat_id, state)
        return


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Свободный текст трактуем как поиск с текущим выбранным типом.

    Переводит русские слова и исправляет опечатки через словарь профессий.
    """
    if not _is_allowed(_config(context), update):
        return
    text = (update.message.text or "").strip()
    if not text:
        return
    chat_id = update.effective_chat.id
    state = _state(context)

    if text == BTN_HELP:
        await update.message.reply_html(HELP_TEXT, reply_markup=_reply_kb())
        return
    if text == BTN_SUBS:
        subs = await asyncio.to_thread(
            _storage(context).list_subscriptions, chat_id
        )
        await update.message.reply_html(_subscriptions_text(subs))
        return
    if text in (BTN_SEARCH, BTN_AUSB):
        state["offer_type"] = int(
            aa.OfferType.AUSBILDUNG if text == BTN_AUSB else aa.OfferType.JOB
        )
        state["query"] = None
        await update.message.reply_html(
            _search_title(state), reply_markup=_kb_search(state)
        )
        return

    query, note = await _resolve_query_full(text)
    if note:
        await context.bot.send_message(chat_id, note)
    state["query"] = query
    await _search_and_send(
        context, chat_id, query,
        aa.OfferType(state["offer_type"]), _state_times(state),
    )


async def poll_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Почасовая проверка всех подписок на новые объявления."""
    storage = _storage(context)
    subs = await asyncio.to_thread(storage.all_subscriptions)
    for sub in subs:
        await _poll_one(context, storage, sub)


async def _poll_one(
    context: ContextTypes.DEFAULT_TYPE,
    storage: Storage,
    sub: Subscription,
) -> None:
    try:
        listings = await _run_search(
            context,
            sub.query or None,
            aa.OfferType(sub.offer_type),
            sub.arbeitszeit or None,
            since_days=_config(context).subscription_since_days,
        )
    except aa.ArbeitsagenturError:
        logger.warning("Подписка #%s: API недоступно, пропускаю", sub.id)
        return
    by_refnr = {item.refnr: item for item in listings}
    new_refnrs = await asyncio.to_thread(
        storage.filter_new_refnrs, sub.id, list(by_refnr.keys())
    )
    if not new_refnrs:
        return
    await asyncio.to_thread(storage.mark_seen, sub.id, list(new_refnrs))
    fresh = [by_refnr[r] for r in new_refnrs]
    number = await _subscription_number(context, sub.chat_id, sub.id)
    await context.bot.send_message(
        chat_id=sub.chat_id,
        text=f"🔔 Новое по подписке №{number}: {len(fresh)}",
    )
    await _send_listings(context, sub.chat_id, fresh[:_MAX_RESULTS])


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Необработанная ошибка", exc_info=context.error)


async def _post_init(app: Application) -> None:
    """Закрепляет команды в меню бота (кнопка «/» у поля ввода)."""
    await app.bot.set_my_commands(
        [BotCommand(cmd, desc) for cmd, desc in BOT_COMMANDS]
    )


def build_application(config: Config) -> Application:
    app = Application.builder().token(config.bot_token).post_init(_post_init).build()
    app.bot_data["config"] = config
    app.bot_data["storage"] = Storage(config.db_path)

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", start_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("ausbildung", ausbildung_command))
    app.add_handler(CommandHandler("watch", watch_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("unwatch", unwatch_command))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)

    app.job_queue.run_repeating(
        poll_job,
        interval=config.poll_interval_minutes * 60,
        first=config.poll_interval_minutes * 60,
        name="poll_subscriptions",
    )
    return app


def _ensure_event_loop() -> None:
    """Python 3.14: get_event_loop() больше не создаёт loop автоматически.

    PTB рассчитывает на наличие event loop в главном потоке, поэтому
    создаём его явно, если он ещё не установлен.
    """
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


def main() -> None:
    config = Config.load()
    _ensure_event_loop()
    app = build_application(config)
    logger.info(
        "Бот запущен. Город=%s, радиус=%s км, опрос каждые %s мин.",
        config.default_city,
        config.default_radius_km,
        config.poll_interval_minutes,
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

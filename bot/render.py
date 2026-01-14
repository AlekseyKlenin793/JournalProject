from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from db import Session
from models import Journal
from utils import format_value
from state import user_journal_data, user_journal_base, user_filters


def send_journals_list(bot, message, rows):
    """
    rows: список кортежей (название, issn, price, currency, category)
    Сохраняем в user_journal_base (исходные результаты)
    и выставляем текущий view в user_journal_data равным базе.
    """
    user_id = message.from_user.id
    # Убираем возможные дубликаты по ISSN перед сохранением базы
    dedup = {}
    for r in rows:
        # ожидаем, что r[1] — issn
        issn = r[1] if len(r) > 1 else None
        if issn:
            dedup[issn] = r
    base_list = list(dedup.values())

    user_journal_base[user_id] = base_list
    user_journal_data[user_id] = list(base_list)  # view по умолчанию = база
    # Переносим флаг ограничения, если был установлен ранее
    # (обычно устанавливается в search_by_keyword)
    send_journals_page(bot, message.chat.id, user_id, 0)


def send_journals_page(bot, chat_id, user_id, page, message_id=None):
    """Вывод списка журналов с нормализованным белым списком и единым отображением пропусков."""
    journals = user_journal_data.get(user_id, [])
    if not journals:
        bot.send_message(chat_id, "❌ Нет сохранённых данных.")
        return

    per_page = 5
    total_pages = max(1, (len(journals) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start, end = page * per_page, page * per_page + per_page

    response = f"📚 *Журналы (стр. {page+1}/{total_pages}):*\n\n"
    active_filters = user_filters.get(user_id, {})

    def norm_category(cat):
        if not cat or str(cat).strip() in ["", "-", "—"]:
            return "—"
        return str(cat)

    with Session() as session:
        for i, row in enumerate(journals[start:end], start=start + 1):
            # row expected: (name, issn, price, currency, category)
            name, issn, price, currency, category = row
            price_str = format_value((price, currency), "currency")  # возвращает '—' при отсутствии

            # основной блок — по умолчанию показываем 3 поля: Название, ISSN, Цена, Категория
            response += f"{i}. *{name}*\n"
            response += f"   🔢 ISSN: {issn}\n"
            response += f"   💰 Цена: {price_str}\n"
            response += f"   🔖 Категория: {norm_category(category)}\n"

            # подгружаем дополнительные поля только если пользователь включил соответствующий фильтр
            j = session.query(Journal).filter(Journal.issn == issn).first()
            if j:
                # Индексы
                if "Индекс Хирша" in active_filters:
                    response += f"   📈 Индекс Хирша: {format_value(j.h_index)}\n"
                if "Индекс цитирования" in active_filters:
                    response += f"   🔗 Индекс цитирования: {format_value(j.citation_index)}\n"

                # Время публикации (если выбран фильтр по времени публикации)
                if "Время публикации" in active_filters:
                    time_val = format_value(j.publication_time_value)
                    time_unit = format_value(j.publication_time_unit, "unit")
                    time_str = f"{time_val} {time_unit}".strip()
                    if time_str in ["—", "— "]:
                        time_str = "Не указано"
                    response += f"   🕒 Время публикации: {time_str}\n"

                # Белый список показываем ТОЛЬКО если пользователь включил фильтр "Белый список"
                if "Белый список" in active_filters:
                    wl23_raw = j.white_list_level_2023
                    wl25_raw = j.white_list_level_2025

                    def has_val(v):
                        return v not in [None, "", "-", "—"]
                    if has_val(wl23_raw) or has_val(wl25_raw):
                        wl23 = format_value(wl23_raw)
                        wl25 = format_value(wl25_raw)
                        wl_lines = []
                        if wl23 != "—":
                            wl_lines.append(f"      • 2023 — {wl23}")
                        if wl25 != "—":
                            wl_lines.append(f"      • 2025 — {wl25}")
                        wl_block = "   🏅 Белый список:\n" + "\n".join(wl_lines)
                        response += wl_block + "\n"
                    else:
                        # если фильтр по белому списку включён, но у журнала нет значений — ничего не показываем
                        pass

            response += "\n"

    # предупреждение лимита только если флаг стоит и база реальна >= 50
    if user_journal_data.get(f"limit_warning_{user_id}", False) and len(user_journal_base.get(user_id, [])) >= 50:
        response += "⚠️ Точных совпадений не найдено, вывод ограничен 50 результатами.\n"

    # показываем активные фильтры внизу
    if active_filters:
        response += "\n⚙️ *Активные фильтры:*\n"
        for key, val in active_filters.items():
            response += f"• {key}: {val}\n"

    # кнопки
    markup = InlineKeyboardMarkup(row_width=2)
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Вперёд ➡️", callback_data=f"page_{page+1}"))
    if nav_buttons:
        markup.add(*nav_buttons)

    markup.add(InlineKeyboardButton("⚙️ Фильтрация", callback_data="open_filters"))
    markup.add(InlineKeyboardButton("📄 Экспорт в TXT", callback_data="export_txt"))

    if message_id:
        bot.edit_message_text(response, chat_id=chat_id, message_id=message_id,
                              parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(chat_id, response, parse_mode="Markdown", reply_markup=markup)


def send_journal_info(bot, message, journals):
    """Вывод детальной информации о журнале."""
    for j in journals:
        directions = "\n".join(
            f"• {d.direction_number or '—'} — {d.scientific_direction or '—'}"
            for d in getattr(j, "directions", [])
        ) or "Нет данных"

        def fmt(v):
            return v if v not in [None, "—", "", "-"] else "Не указано"

        publication_time = f"{format_value(j.publication_time_value)} {format_value(j.publication_time_unit, 'unit')}".strip()
        if publication_time in ["—", "— —", "Не указано", "Не указано Не указано"]:
            publication_time = "Не указано"

        price = format_value((j.publication_price, j.publication_currency), "currency")
        if price in ["—", "", None]:
            price = "Не указана"

        # Нормализация Белого списка
        wl23 = format_value(j.white_list_level_2023)
        wl25 = format_value(j.white_list_level_2025)

        if wl23 == "—" and wl25 == "—":
            wl_block = "🏅 *Белый список:* Отсутствует"
        else:
            lines = []
            if wl23 != "—":
                lines.append(f"      • 2023 — {wl23}")
            if wl25 != "—":
                lines.append(f"      • 2025 — {wl25}")
            wl_block = "🏅 *Белый список:*\n" + "\n".join(lines)

        response = (
            f"📚 *Название:* {fmt(j.journal_name)}\n"
            f"🔢 *ISSN:* {fmt(j.issn)}\n"
            f"📖 *Направления:*\n{directions}\n"
            f"📅 *Дата включения:* {fmt(j.inclusion_date)}\n"
            f"📈 *Индекс Хирша:* {format_value(j.h_index)}\n"
            f"🔗 *Индекс цитирования:* {format_value(j.citation_index)}\n"
            f"⏳ *Время публикации:* {publication_time}\n"
            f"💰 *Цена:* {price}\n"
            f"{wl_block}\n"
            f"🔖 *Категория:* {fmt(j.final_category)}\n"
            f"🌐 *Ссылка:* {fmt(j.url)}"
        )
        bot.reply_to(message, response, parse_mode="Markdown")

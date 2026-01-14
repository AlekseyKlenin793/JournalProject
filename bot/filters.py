from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from db import Session
from models import Journal
from state import user_filters, user_journal_base, user_journal_data
from render import send_journals_page


def open_filter_menu(bot, call):
    user_id = call.from_user.id
    markup = InlineKeyboardMarkup(row_width=2)

    # Новый порядок кнопок:
    # 1️⃣ Цена и Время публикации
    markup.add(
        InlineKeyboardButton("💰 Цена", callback_data="filter_price"),
        InlineKeyboardButton("🕒 Публикация", callback_data="filter_time")
    )

    # 2️⃣ Категория и Белый список
    markup.add(
        InlineKeyboardButton("🏷 Категория", callback_data="filter_category"),
        InlineKeyboardButton("🏅 Белый список", callback_data="filter_whitelist")
    )

    # 3️⃣ Индексы
    markup.add(
        InlineKeyboardButton("📈 Индекс Хирша", callback_data="filter_hindex"),
        InlineKeyboardButton("🔗 Цитирование", callback_data="filter_citation")
    )

    # Служебные кнопки — отдельные ряды
    markup.add(InlineKeyboardButton("✅ Применить", callback_data="apply_filters"))
    markup.add(InlineKeyboardButton("♻️ Сбросить", callback_data="reset_filters"))
    markup.add(InlineKeyboardButton("↩️ Назад", callback_data="return_list"))

    active = user_filters.get(user_id, {})
    active_text = "\n".join([f"• {k}: {v}" for k, v in active.items()]) or "—"
    text = f"⚙️ *Фильтрация*\n\nВыберите параметр для настройки:\n\n*Текущие фильтры:*\n{active_text}"

    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          parse_mode="Markdown", reply_markup=markup)


def open_filter_options(bot, call, filter_type):
    options = []
    if filter_type == "hindex":
        options = [("Указан", "hindex_exists"),
                   ("По возрастанию", "hindex_asc"),
                   ("По убыванию", "hindex_desc")]
    elif filter_type == "citation":
        options = [("Указан", "citation_exists"),
                   ("По возрастанию", "citation_asc"),
                   ("По убыванию", "citation_desc")]
    elif filter_type == "time":
        options = [("Указано", "time_exists"),
                   ("По возрастанию", "time_asc"),
                   ("По убыванию", "time_desc")]
    elif filter_type == "price":
        options = [("Указана", "price_exists"),
                   ("По возрастанию", "price_asc"),
                   ("По убыванию", "price_desc")]
    elif filter_type == "whitelist":
        options = [
            ("По возрастанию (2025)", "wl25_asc"),
            ("По убыванию (2025)", "wl25_desc"),
            ("По возрастанию (2023)", "wl23_asc"),
            ("По убыванию (2023)", "wl23_desc"),
            ("Наличие в списке (2023/2025)", "wl_exists")
        ]
    elif filter_type == "category":
        options = [("К1", "cat_K1"), ("К2", "cat_K2"), ("К3", "cat_K3")]

    markup = InlineKeyboardMarkup(row_width=2)
    for name, data in options:
        markup.add(InlineKeyboardButton(name, callback_data=f"setfilter_{data}"))
    markup.add(InlineKeyboardButton("↩️ Назад", callback_data="open_filters"))

    titles = {
        "hindex": "Индекс Хирша",
        "citation": "Индекс цитирования",
        "time": "Время публикации",
        "price": "Цена",
        "whitelist": "Белый список",
        "category": "Категория"
    }

    bot.edit_message_text(
        f"⚙️ *{titles[filter_type]}*\nВыберите способ фильтрации:",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown",
        reply_markup=markup
    )


def apply_filters(bot, call):
    user_id = call.from_user.id
    filters = user_filters.get(user_id, {})
    base_results = user_journal_base.get(user_id, [])

    if not base_results:
        bot.answer_callback_query(call.id, "❌ Нет данных для фильтрации.")
        return

    # убираем дубликаты по ISSN (базовый набор)
    seen = set()
    filtered_rows = []
    for row in base_results:
        issn = row[1] if len(row) > 1 else None
        if issn and issn not in seen:
            seen.add(issn)
            filtered_rows.append(row)

    with Session() as session:
        enriched = []
        for name, issn, price, currency, category in filtered_rows:
            j = session.query(Journal).filter(Journal.issn == issn).first()
            if not j:
                continue

            # проверка, указана ли числовая цена
            def price_is_specified(pub_price):
                try:
                    return pub_price is not None and float(pub_price) != 0
                except Exception:
                    return False

            skip = False
            for key, val in filters.items():
                if key == "Категория" and j.final_category != val:
                    skip = True
                    break
                if key == "Индекс Хирша" and val == "Указан" and j.h_index is None:
                    skip = True
                    break
                if key == "Индекс цитирования" and val == "Указан" and j.citation_index is None:
                    skip = True
                    break
                if key == "Время публикации" and val == "Указано" and j.publication_time_value is None:
                    skip = True
                    break
                if key == "Цена" and val == "Указана" and not price_is_specified(j.publication_price):
                    skip = True
                    break
                if key == "Белый список":
                    if "2025" in val and j.white_list_level_2025 in [None, "", "-", "—"]:
                        skip = True
                        break
                    if "2023" in val and j.white_list_level_2023 in [None, "", "-", "—"]:
                        skip = True
                        break

            if skip:
                continue

            enriched.append((
                name, issn, price, currency, category,
                j.h_index, j.citation_index,
                j.publication_time_value, j.publication_time_unit,
                j.white_list_level_2023, j.white_list_level_2025
            ))

        # --- сортировка ---
        def safe_num(v):
            try:
                if v is None:
                    return None
                return float(v)
            except Exception:
                return None

        # универсальный генератор ключа для сортировки числовых полей
        def make_key(index, descending=False):
            def getter(item):
                num = safe_num(item[index])
                is_missing = 1 if num is None else 0
                # отсутствующие значения всегда в конец при возрастании
                if num is None:
                    return is_missing, float('inf') if not descending else float('-inf')
                return (is_missing, -num) if descending else (is_missing, num)
            return getter

        for key, val in filters.items():
            descending = "убыванию" in val
            if key == "Индекс Хирша":
                enriched.sort(key=make_key(5, descending))
            elif key == "Индекс цитирования":
                enriched.sort(key=make_key(6, descending))
            elif key == "Время публикации":
                enriched.sort(key=make_key(7, descending))
            elif key == "Цена":
                enriched.sort(key=make_key(2, descending))
            elif key == "Белый список":
                def wl_key_for_year(item, year, descending=False):
                    idx = 10 if year == 2025 else 9
                    num = safe_num(item[idx])
                    is_missing = 1 if num is None else 0
                    if num is None:
                        return is_missing, float('inf') if not descending else float('-inf')
                    return (is_missing, -num) if descending else (is_missing, num)

                if "2025" in val:
                    enriched.sort(key=lambda x: wl_key_for_year(x, 2025, descending))
                elif "2023" in val:
                    enriched.sort(key=lambda x: wl_key_for_year(x, 2023, descending))
                elif "Наличие" in val:
                    def wl_exists_key(item):
                        v25 = safe_num(item[10])
                        v23 = safe_num(item[9])
                        has_any = 0 if (v25 is not None or v23 is not None) else 1
                        sub = v25 if v25 is not None else (v23 if v23 is not None else 0.0)
                        return has_any, sub
                    enriched.sort(key=wl_exists_key)

    # сохраняем view
    unique_filtered = []
    seen = set()
    for item in enriched:
        if item[1] not in seen:
            seen.add(item[1])
            unique_filtered.append(item[:5])

    if not unique_filtered:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("♻️ Сбросить фильтры", callback_data="reset_filters"))
        bot.edit_message_text(
            "❌ После применения фильтров не осталось подходящих журналов.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup
        )
        return

    user_journal_data[user_id] = unique_filtered
    user_journal_data[f"limit_warning_{user_id}"] = False
    send_journals_page(bot, call.message.chat.id, user_id, 0, call.message.message_id)
    bot.answer_callback_query(call.id, "Фильтры применены")


def reset_filters(bot, call):
    user_id = call.from_user.id
    user_filters[user_id] = {}
    # восстанавливаем view из базы (если база есть)
    base = user_journal_base.get(user_id, [])
    user_journal_data[user_id] = list(base)
    # сбрасываем флаг предупреждения
    user_journal_data.pop(f"limit_warning_{user_id}", None)
    bot.answer_callback_query(call.id, "Фильтры сброшены")
    # Редактируем сообщение: показываем страницу 0
    send_journals_page(bot, call.message.chat.id, user_id, 0, call.message.message_id)

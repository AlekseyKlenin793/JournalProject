import io
import os
import re
import logging

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from recommend import recommend_journals
from models import Journal
from utils import format_value
from db import Session
from search import search_by_issn, search_by_direction_code, search_by_keyword
from render import send_journals_page
from filters import (
    open_filter_menu, open_filter_options,
    apply_filters, reset_filters
)
from state import (
    user_search_history, user_filters,
    user_journal_data, user_journal_base, HISTORY_LIMIT
)

# -------------------- ЛОГИРОВАНИЕ --------------------

logging.basicConfig(
    filename="bot.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# -------------------- BOT INIT --------------------

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)


# -------------------- COMMANDS --------------------

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_first_name = message.from_user.first_name or "Пользователь"
    bot.reply_to(
        message,
        f"👋 Привет, <b>{user_first_name}</b>!\n\n"
        "Этот бот помогает находить <b>научные журналы</b> и <b>направления</b>.\n\n"
        "<b>Можно искать по:</b>\n"
        "- ISSN (например, <code>1234-5678</code>)\n"
        "- коду направления (например, <code>5.3.3</code>)\n"
        "- названию (например, <code>Физика</code>)\n\n"
        "ℹ️ Вы можете просмотреть историю поиска через кнопку /history",
        parse_mode="HTML"
    )


# -------------------- MAIN QUERY HANDLER --------------------

@bot.message_handler(func=lambda msg: not msg.text.startswith('/'))
def handle_query(message):
    query = message.text.strip()
    logging.info(f"Запрос от пользователя {message.from_user.id}: {query}")

    if len(query) < 3:
        bot.reply_to(message, "⚠️ Введите хотя бы 3 символа для поиска.")
        return

    user_id = message.from_user.id

    # --- сброс состояния ---
    user_filters[user_id] = {}
    user_journal_base[user_id] = []
    user_journal_data[user_id] = []
    user_journal_data.pop(f"limit_warning_{user_id}", None)

    # --- история ---
    user_search_history.setdefault(user_id, [])
    if query not in user_search_history[user_id]:
        user_search_history[user_id].append(query)
        if len(user_search_history[user_id]) > HISTORY_LIMIT:
            user_search_history[user_id] = user_search_history[user_id][-HISTORY_LIMIT:]

    issn_pattern = r"^\d{4}-\d{3}[0-9Xx]$"
    direction_code_pattern = r"^\d+\.\d+\.\d+$"

    if re.match(issn_pattern, query):
        search_by_issn(bot, message, query)
    elif re.match(direction_code_pattern, query):
        search_by_direction_code(bot, message, query)
    else:
        search_by_keyword(bot, message, query)


# -------------------- HISTORY --------------------

@bot.message_handler(commands=['history'])
def show_history(message):
    user_id = message.from_user.id
    history = user_search_history.get(user_id, [])

    if not history:
        bot.reply_to(message, "ℹ️ Ваша история поиска пуста.")
        return

    response = "🕘 *История поиска:*\n\n"
    markup = InlineKeyboardMarkup(row_width=1)

    for idx, query in enumerate(reversed(history), start=1):
        markup.add(
            InlineKeyboardButton(
                f"{idx}. {query}",
                callback_data=f"history_{len(history) - idx}"
            )
        )

    bot.send_message(
        message.chat.id,
        response,
        parse_mode="Markdown",
        reply_markup=markup
    )


# -------------------- RECOMMENDATIONS --------------------

@bot.message_handler(commands=['recommend'])
def recommend_handler(message):
    with Session() as session:
        recommend_journals(bot, message, session)


# -------------------- PAGINATION --------------------

@bot.callback_query_handler(func=lambda call: call.data.startswith("page_") or call.data == "noop")
def callback_page(call):
    if call.data == "noop":
        bot.answer_callback_query(call.id)
        return

    page = int(call.data.split("_")[1])
    send_journals_page(
        bot,
        call.message.chat.id,
        call.from_user.id,
        page,
        call.message.message_id
    )
    bot.answer_callback_query(call.id)


# -------------------- EXPORT --------------------

@bot.callback_query_handler(func=lambda call: call.data == "export_txt")
def callback_export(call):
    user_id = call.from_user.id
    journals = user_journal_data.get(user_id, [])
    filters = user_filters.get(user_id, {})

    if not journals:
        bot.answer_callback_query(call.id, "❌ Нет данных для экспорта.")
        return

    text_out = "Результаты поиска журналов\n\n"
    seen = set()

    with Session() as session:
        idx = 1
        for row in journals:
            if len(row) < 2:
                continue

            issn = row[1]
            if issn in seen:
                continue
            seen.add(issn)

            name, issn, price, currency, category = row
            j = session.query(Journal).filter(Journal.issn == issn).first()
            if not j:
                continue

            directions = "; ".join(
                f"{d.direction_number or '—'} — {d.scientific_direction or '—'}"
                for d in j.directions
            ) or "Нет данных"

            wl_lines = []
            if j.white_list_level_2023 not in [None, "", "-", "—"]:
                wl_lines.append(f"      • 2023 — {j.white_list_level_2023}")
            if j.white_list_level_2025 not in [None, "", "-", "—"]:
                wl_lines.append(f"      • 2025 — {j.white_list_level_2025}")
            wl_block = "\n".join(wl_lines) if wl_lines else "—"

            text_out += (
                f"{idx}. {name}\n"
                f"   ISSN: {j.issn or '—'}\n"
                f"   Направления: {directions}\n"
                f"   Дата включения: {j.inclusion_date or '—'}\n"
                f"   Индекс Хирша: {format_value(j.h_index)}\n"
                f"   Индекс цитирования: {format_value(j.citation_index)}\n"
                f"   Время публикации: {format_value(j.publication_time_value)} "
                f"{format_value(j.publication_time_unit, 'unit')}\n"
                f"   Цена: {format_value((j.publication_price, j.publication_currency), 'currency')}\n"
                f"   Белый список:\n{wl_block}\n"
                f"   Категория: {j.final_category or '—'}\n"
                f"   Ссылка: {j.url or '-'}\n\n"
            )
            idx += 1

    if filters:
        text_out += "------\nАктивные фильтры:\n"
        for k, v in filters.items():
            text_out += f"• {k}: {v}\n"

    buffer = io.BytesIO(text_out.encode("utf-8"))
    buffer.name = "journals_results.txt"

    bot.send_document(call.message.chat.id, buffer)
    bot.answer_callback_query(call.id, "✅ Файл успешно отправлен.")


# -------------------- HISTORY CALLBACK --------------------

@bot.callback_query_handler(func=lambda call: call.data.startswith("history_"))
def callback_history(call):
    user_id = call.from_user.id
    history = user_search_history.get(user_id, [])

    index = int(call.data.split("_")[1])
    if 0 <= index < len(history):
        query = history[index]
        fake_message = type(
            'obj',
            (object,),
            {
                'text': query,
                'from_user': call.from_user,
                'chat': call.message.chat,
                'message_id': call.message.message_id
            }
        )()
        handle_query(fake_message)

    bot.answer_callback_query(call.id)


# -------------------- FILTERS --------------------

@bot.callback_query_handler(func=lambda call: (
    call.data in ["open_filters", "apply_filters", "reset_filters", "return_list"]
    or call.data.startswith("filter_")
    or call.data.startswith("setfilter_")
))
def callback_filters(call):
    if call.data == "open_filters":
        open_filter_menu(bot, call)

    elif call.data.startswith("filter_"):
        open_filter_options(bot, call, call.data.split("_")[1])

    elif call.data.startswith("setfilter_"):
        user_id = call.from_user.id
        choice = call.data.replace("setfilter_", "")

        mapping = {
            "hindex_exists": ("Индекс Хирша", "Указан"),
            "hindex_asc": ("Индекс Хирша", "По возрастанию"),
            "hindex_desc": ("Индекс Хирша", "По убыванию"),
            "citation_exists": ("Индекс цитирования", "Указан"),
            "citation_asc": ("Индекс цитирования", "По возрастанию"),
            "citation_desc": ("Индекс цитирования", "По убыванию"),
            "time_exists": ("Время публикации", "Указано"),
            "time_asc": ("Время публикации", "По возрастанию"),
            "time_desc": ("Время публикации", "По убыванию"),
            "price_exists": ("Цена", "Указана"),
            "price_asc": ("Цена", "По возрастанию"),
            "price_desc": ("Цена", "По убыванию"),
            "wl25_asc": ("Белый список", "По возрастанию (2025)"),
            "wl25_desc": ("Белый список", "По убыванию (2025)"),
            "wl23_asc": ("Белый список", "По возрастанию (2023)"),
            "wl23_desc": ("Белый список", "По убыванию (2023)"),
            "wl_exists": ("Белый список", "Наличие в списке"),
            "cat_K1": ("Категория", "К1"),
            "cat_K2": ("Категория", "К2"),
            "cat_K3": ("Категория", "К3"),
        }

        key, val = mapping.get(choice)
        user_filters.setdefault(user_id, {})[key] = val
        open_filter_menu(bot, call)

    elif call.data == "apply_filters":
        apply_filters(bot, call)

    elif call.data == "reset_filters":
        reset_filters(bot, call)

    elif call.data == "return_list":
        send_journals_page(
            bot,
            call.message.chat.id,
            call.from_user.id,
            0,
            call.message.message_id
        )


# -------------------- START --------------------

if __name__ == "__main__":
    logging.info("Бот запущен и готов к работе.")
    bot.polling(none_stop=True)

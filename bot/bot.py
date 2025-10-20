import os
import re
import io
import logging
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import create_engine, Column, Integer, String, Text, Numeric, Date, ForeignKey, TIMESTAMP, or_
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.exc import SQLAlchemyError


logging.basicConfig(
    filename="bot.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
HISTORY_LIMIT = 20

bot = telebot.TeleBot(BOT_TOKEN)
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
Base = declarative_base()

user_journal_data = {}
user_search_history = {}


class Journal(Base):
    __tablename__ = "journals"
    id = Column(Integer, primary_key=True)
    journal_name = Column(String(1000), nullable=False)
    issn = Column(String(20), nullable=False)
    inclusion_date = Column(Date)
    h_index = Column(Numeric)
    citation_index = Column(Numeric)
    publication_time_value = Column(Numeric)
    publication_time_unit = Column(String(20))
    publication_price = Column(Numeric)
    publication_currency = Column(String(10))
    url = Column(Text)
    final_category = Column(String(100))
    timestamp = Column(TIMESTAMP)
    white_list_level_2023 = Column(String(100))
    white_list_level_2025 = Column(String(100))
    directions = relationship("Direction", back_populates="journal")


class Direction(Base):
    __tablename__ = "directions"
    id = Column(Integer, primary_key=True)
    journal_id = Column(Integer, ForeignKey("journals.id"))
    direction_number = Column(String(100))
    scientific_direction = Column(Text)
    journal = relationship("Journal", back_populates="directions")


def format_value(val, val_type="num", precision=3, zero_is_none=False):
    unit_map = {
        "weeks": "недель",
        "week": "неделя",
        "days": "дней",
        "day": "день",
        "months": "месяцев",
        "month": "месяц",
        "years": "лет",
        "year": "год"
    }

    if val_type == "num":
        try:
            val = float(val)
            if zero_is_none and val == 0:
                return "—"
            return int(val) if val == int(val) else round(val, precision)
        except (ValueError, TypeError):
            return "—"

    elif val_type == "currency":
        price, currency = val
        try:
            if price is None or float(price) == 0:
                return currency or "—"
            price_val = float(price)
            price_val = int(price_val) if price_val == int(price_val) else round(price_val, precision)
            return f"{price_val} {currency}".strip()
        except (ValueError, TypeError):
            return currency or "—"

    elif val_type == "unit":
        return unit_map.get(str(val or "").lower(), val or "")

    return val or "—"


def search_by_issn(message, query):
    with Session() as session:
        try:
            journals = session.query(Journal).filter(Journal.issn == query).all()
            if journals:
                send_journal_info(message, journals)
            else:
                bot.reply_to(message, "❌ Журнал с таким ISSN не найден.")
        except SQLAlchemyError as e:
            logging.error(f"Ошибка при поиске ISSN: {e}")
            bot.reply_to(message, "❌ Ошибка при выполнении запроса.")


def search_by_direction_code(message, query):
    with Session() as session:
        try:
            # Добавляем publication_currency в выборку
            results = (
                session.query(
                    Journal.journal_name,
                    Journal.issn,
                    Journal.publication_price,
                    Journal.publication_currency,
                    Journal.final_category
                )
                .join(Direction)
                .filter(Direction.direction_number == query)
                .all()
            )

            if results:
                send_journals_list(message, results)
            else:
                bot.reply_to(message, "❌ Журналы с таким кодом направления не найдены.")
        except SQLAlchemyError as e:
            logging.error(f"Ошибка при поиске по коду направления: {e}")
            bot.reply_to(message, "❌ Ошибка при выполнении запроса.")


def search_by_keyword(message, query, max_results=50):
    with Session() as session:
        try:
            # Точные совпадения по названию журнала
            exact_journal = session.query(Journal).filter(Journal.journal_name.ilike(query)).all()

            # Точные совпадения по направлению
            exact_direction = (
                session.query(
                    Journal.journal_name,
                    Journal.issn,
                    Journal.publication_price,
                    Journal.publication_currency,
                    Journal.final_category
                )
                .join(Direction)
                .filter(Direction.scientific_direction.ilike(query))
                .all()
            )

            if len(exact_journal) == 1:
                send_journal_info(message, exact_journal)
                return

            if exact_direction:
                user_journal_data[f"limit_warning_{message.from_user.id}"] = False
                send_journals_list(message, exact_direction)
                return

            # Поиск по подстроке
            results = (
                session.query(
                    Journal.journal_name,
                    Journal.issn,
                    Journal.publication_price,
                    Journal.publication_currency,
                    Journal.final_category
                )
                .join(Direction, isouter=True)
                .filter(
                    or_(
                        Journal.journal_name.ilike(f"%{query}%"),
                        Direction.scientific_direction.ilike(f"%{query}%")
                    )
                )
                .all()
            )

            if not results:
                bot.reply_to(message, "❌ Ничего не найдено по вашему запросу.")
                return

            # Убираем дубликаты по ISSN
            unique = {r[1]: r for r in results}
            results = list(unique.values())

            if len(results) == 1:
                journal = session.query(Journal).filter(Journal.issn == results[0][1]).all()
                send_journal_info(message, journal)
                return

            # Ограничение вывода и установка предупреждения
            if len(results) > max_results:
                limited_results = results[:max_results]
                user_journal_data[f"limit_warning_{message.from_user.id}"] = True
                send_journals_list(message, limited_results)
            else:
                user_journal_data[f"limit_warning_{message.from_user.id}"] = False
                send_journals_list(message, results)

        except SQLAlchemyError as e:
            logging.error(f"Ошибка при поиске по названию: {e}")
            bot.reply_to(message, "❌ Ошибка при выполнении запроса.")


def send_journal_info(message, journals):
    for j in journals:
        directions = "\n".join(
            f"• {d.direction_number or '—'} — {d.scientific_direction or '—'}"
            for d in getattr(j, "directions", [])
        ) or "Нет данных"

        response = (
            f"📚 *Название:* {getattr(j, 'journal_name', '—')}\n"
            f"🔢 *ISSN:* {getattr(j, 'issn', '—')}\n"
            f"📖 *Направления:*\n{directions}\n"
            f"📅 *Дата включения:* {getattr(j, 'inclusion_date', '—') or '—'}\n"
            f"📈 *Индекс Хирша:* {format_value(getattr(j, 'h_index', 0))}\n"
            f"🔗 *Индекс цитирования:* {format_value(getattr(j, 'citation_index', 0))}\n"
            f"⏳ *Время публикации:* {format_value(getattr(j, 'publication_time_value', '-'))} "
            f"{format_value(getattr(j, 'publication_time_unit', ''), 'unit')}\n"
            f"💰 *Цена:* {format_value((getattr(j, 'publication_price', None), getattr(j, 'publication_currency', '')), 'currency')}\n"
            f"🏅 *Белый список 2023:* {format_value(getattr(j, 'white_list_level_2023', '—'))}\n"
            f"🏅 *Белый список 2025:* {format_value(getattr(j, 'white_list_level_2025', '—'))}\n"
            f"🔖 *Категория:* {getattr(j, 'final_category', '—') or '—'}\n"
            f"🌐 *Ссылка:* {getattr(j, 'url', '-') or '-'}"
        )
        bot.reply_to(message, response, parse_mode="Markdown")


def send_journals_list(message, rows):
    user_id = message.from_user.id
    user_journal_data[user_id] = rows
    send_journals_page(message.chat.id, user_id, 0)


def send_journals_page(chat_id, user_id, page, message_id=None):
    journals = user_journal_data.get(user_id, [])
    if not journals:
        bot.send_message(chat_id, "❌ Нет сохранённых данных.")
        return

    per_page = 5
    total_pages = max(1, (len(journals) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start, end = page * per_page, page * per_page + per_page

    response = f"📚 *Журналы (стр. {page+1}/{total_pages}):*\n\n"

    for i, row in enumerate(journals[start:end], start=start + 1):
        name, issn, price, currency, category = row

        if price is None:
            price_str = f"- {currency or ''}".strip() or "-"
        else:
            price_val = int(price) if float(price) == int(price) else round(float(price), 2)
            price_str = f"{price_val} {currency or ''}".strip()

        response += (
            f"{i}. *{name}*\n"
            f"   🔢 ISSN: {issn}\n"
            f"   💰 Цена: {price_str}\n"
            f"   🏷️ Категория: {category or '-'}\n\n"
        )

    # Добавляем предупреждение, если нужно
    if user_journal_data.get(f"limit_warning_{user_id}", False):
        response += "⚠️ Точных совпадений не найдено, вывод ограничен 50 результатами. Пожалуйста, уточните запрос."

    # Кнопки навигации
    markup = InlineKeyboardMarkup(row_width=2)
    buttons = []

    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"page_{page-1}"))
    if page < total_pages - 1:
        buttons.append(InlineKeyboardButton("Вперёд ➡️", callback_data=f"page_{page+1}"))

    if buttons:
        markup.add(*buttons)  # В один ряд
    markup.add(InlineKeyboardButton("📄 Экспорт в TXT", callback_data="export_txt"))

    # Отправка или редактирование сообщения
    if message_id:
        bot.edit_message_text(
            response, chat_id=chat_id, message_id=message_id,
            parse_mode="Markdown", reply_markup=markup
        )
    else:
        bot.send_message(chat_id, response, parse_mode="Markdown", reply_markup=markup)


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


@bot.message_handler(func=lambda msg: not msg.text.startswith('/'))
def handle_query(message):
    query = message.text.strip()
    logging.info(f"Запрос от пользователя {message.from_user.id}: {query}")

    if len(query) < 3:
        bot.reply_to(message, "⚠️ Введите хотя бы 3 символа для поиска.")
        return

    # Сохраняем в историю
    user_id = message.from_user.id
    if user_id not in user_search_history:
        user_search_history[user_id] = []
    if query not in user_search_history[user_id]:
        user_search_history[user_id].append(query)
        # Ограничиваем длину истории
        if len(user_search_history[user_id]) > HISTORY_LIMIT:
            user_search_history[user_id] = user_search_history[user_id][-HISTORY_LIMIT:]

    issn_pattern = r"^\d{4}-\d{3}[0-9Xx]$"
    direction_code_pattern = r"^\d+\.\d+\.\d+$"

    if re.match(issn_pattern, query):
        search_by_issn(message, query)
    elif re.match(direction_code_pattern, query):
        search_by_direction_code(message, query)
    else:
        search_by_keyword(message, query)


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
        # callback_data = history_номер
        markup.add(InlineKeyboardButton(f"{idx}. {query}", callback_data=f"history_{len(history)-idx}"))

    bot.send_message(message.chat.id, response, parse_mode="Markdown", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("page_") or call.data == "noop")
def callback_page(call):
    if call.data == "noop":
        bot.answer_callback_query(call.id)
        return
    page = int(call.data.split("_")[1])
    send_journals_page(call.message.chat.id, call.from_user.id, page, call.message.message_id)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == "export_txt")
def callback_export(call):
    user_id = call.from_user.id
    journals = user_journal_data.get(user_id, [])
    if not journals:
        bot.answer_callback_query(call.id, "❌ Нет данных для экспорта.")
        return

    text_out = "Результаты поиска:\n\n"
    for i, row in enumerate(journals, start=1):
        text_out += f"{i}. {row[0]} — {row[1]} ({row[3]})\n"

    buffer = io.BytesIO(text_out.encode("utf-8"))
    buffer.name = "results.txt"
    bot.send_document(call.message.chat.id, buffer)
    bot.answer_callback_query(call.id, "✅ Файл отправлен.")


@bot.callback_query_handler(func=lambda call: call.data.startswith("history_"))
def callback_history(call):
    user_id = call.from_user.id
    history = user_search_history.get(user_id, [])

    index = int(call.data.split("_")[1])
    if 0 <= index < len(history):
        query = history[index]
        # Повторяем поиск
        fake_message = type('obj', (object,), {
            'text': query,
            'from_user': call.from_user,
            'chat': call.message.chat,
            'message_id': call.message.message_id  # <-- добавляем
        })()
        handle_query(fake_message)

    bot.answer_callback_query(call.id)


if __name__ == "__main__":
    logging.info("Бот запущен и готов к работе.")
    print("Бот запущен...")
    bot.polling(none_stop=True)

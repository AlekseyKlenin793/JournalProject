import logging
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import or_

from db import Session
from models import Journal, Direction
from render import send_journal_info, send_journals_list
from state import user_journal_data


def search_by_issn(bot, message, query):
    with Session() as session:
        try:
            journals = session.query(Journal).filter(Journal.issn == query).all()
            if journals:
                send_journal_info(bot, message, journals)
            else:
                bot.reply_to(message, "❌ Журнал с таким ISSN не найден.")
        except SQLAlchemyError as e:
            logging.error(f"Ошибка при поиске ISSN: {e}")
            bot.reply_to(message, "❌ Ошибка при выполнении запроса.")


def search_by_direction_code(bot, message, query):
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
                send_journals_list(bot, message, results)
            else:
                bot.reply_to(message, "❌ Журналы с таким кодом направления не найдены.")
        except SQLAlchemyError as e:
            logging.error(f"Ошибка при поиске по коду направления: {e}")
            bot.reply_to(message, "❌ Ошибка при выполнении запроса.")


def search_by_keyword(bot, message, query, max_results=50):
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
                send_journal_info(bot, message, exact_journal)
                return

            if exact_direction:
                user_journal_data[f"limit_warning_{message.from_user.id}"] = False
                send_journals_list(bot, message, exact_direction)
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
                send_journal_info(bot, message, journal)
                return

            # Ограничение вывода и установка предупреждения
            if len(results) > max_results:
                limited_results = results[:max_results]
                user_journal_data[f"limit_warning_{message.from_user.id}"] = True
                send_journals_list(bot, message, limited_results)
            else:
                user_journal_data[f"limit_warning_{message.from_user.id}"] = False
                send_journals_list(bot, message, results)

        except SQLAlchemyError as e:
            logging.error(f"Ошибка при поиске по названию: {e}")
            bot.reply_to(message, "❌ Ошибка при выполнении запроса.")

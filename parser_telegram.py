#!/usr/bin/env python3
"""
Crypto Telegram Parser with Database Integration
Парсит Telegram каналы криптовалют и сохраняет в PostgreSQL
Собирает сообщения от начала существования монеты до 60 дней
"""

import requests
from bs4 import BeautifulSoup
import psycopg2
from psycopg2 import sql
import json
from datetime import datetime, timedelta, timezone
import re
import time
import os
import sys
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()


class CryptoTelegramDBParser:
    def __init__(self):
        # Подключение к БД
        self.db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', '5432'),
            'database': os.getenv('DB_NAME', 'crypto_db'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', '')
        }

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

        # Период жизни монеты для сбора данных
        self.max_coin_age_days = 60

    def connect_db(self):
        """Подключение к базе данных"""
        try:
            return psycopg2.connect(**self.db_config)
        except Exception as e:
            print(f"❌ Database connection error: {e}")
            return None

    def get_ohlc_start_date(self, crypto):
        """Получение даты первой записи в OHLC таблице монеты"""
        if not crypto.get('ohlc_table_name'):
            return None

        conn = self.connect_db()
        if not conn:
            return None

        try:
            cur = conn.cursor()

            # Проверяем существование таблицы
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = %s
                )
            """, (crypto['ohlc_table_name'],))

            if not cur.fetchone()[0]:
                print(f"   ❌ OHLC table {crypto['ohlc_table_name']} does not exist")
                return None

            # Сначала проверяем, есть ли вообще записи в таблице
            count_query = sql.SQL("""
                SELECT COUNT(*) FROM {}
            """).format(sql.Identifier(crypto['ohlc_table_name']))

            cur.execute(count_query)
            count = cur.fetchone()[0]

            if count == 0:
                print(f"   ❌ OHLC table {crypto['ohlc_table_name']} is empty")
                return None

            print(f"   ✅ Found {count} OHLC records")

            # Получаем самую раннюю дату из OHLC таблицы
            # Преобразуем timestamp в datetime если это число (Unix timestamp)
            query = sql.SQL("""
                SELECT MIN(
                    CASE 
                        WHEN timestamp > 10000000000 THEN to_timestamp(timestamp / 1000)
                        WHEN timestamp > 10000000 THEN to_timestamp(timestamp)
                        ELSE to_timestamp(timestamp)
                    END
                ) 
                FROM {}
            """).format(sql.Identifier(crypto['ohlc_table_name']))

            cur.execute(query)
            result = cur.fetchone()

            if result and result[0]:
                # Если результат уже datetime, возвращаем как есть
                if isinstance(result[0], datetime):
                    return result[0]
                # Если результат число (Unix timestamp), конвертируем
                elif isinstance(result[0], (int, float)):
                    # Проверяем, в секундах или миллисекундах
                    if result[0] > 10000000000:  # Миллисекунды
                        return datetime.fromtimestamp(result[0] / 1000)
                    else:  # Секунды
                        return datetime.fromtimestamp(result[0])

            return None

        except Exception as e:
            print(f"❌ Error getting OHLC start date: {e}")
            # Попробуем альтернативный запрос
            try:
                # Пробуем прямой запрос без преобразования
                query = sql.SQL("""
                    SELECT MIN(timestamp) 
                    FROM {}
                    LIMIT 1
                """).format(sql.Identifier(crypto['ohlc_table_name']))

                cur.execute(query)
                result = cur.fetchone()

                if result and result[0]:
                    # Проверяем тип данных
                    timestamp_value = result[0]
                    print(f"   📊 Raw timestamp value: {timestamp_value} (type: {type(timestamp_value)})")

                    if isinstance(timestamp_value, datetime):
                        return timestamp_value
                    elif isinstance(timestamp_value, (int, float)):
                        # Unix timestamp
                        if timestamp_value > 10000000000:  # Миллисекунды
                            return datetime.fromtimestamp(timestamp_value / 1000)
                        else:  # Секунды
                            return datetime.fromtimestamp(timestamp_value)

            except Exception as e2:
                print(f"❌ Alternative query also failed: {e2}")

            return None
        finally:
            conn.close()

    def get_cryptocurrencies(self, limit=None):
        """Получение списка криптовалют из БД"""
        conn = self.connect_db()
        if not conn:
            return []

        try:
            cur = conn.cursor()
            # Получаем ВСЕ монеты с telegram_channels и ohlc_table_name
            query = """
                SELECT 
                    id, 
                    name, 
                    symbol, 
                    chain, 
                    coin_gecko_id, 
                    telegram_channels,
                    first_seen_at,
                    added_date,
                    ohlc_table_name,
                    CURRENT_DATE - COALESCE(added_date, first_seen_at::date) as age_days
                FROM cryptocurrencies
                WHERE telegram_channels IS NOT NULL 
                AND array_length(telegram_channels, 1) > 0
                AND coin_gecko_id IS NOT NULL
                AND ohlc_table_name IS NOT NULL
                ORDER BY first_seen_at DESC
            """

            if limit:
                query += f" LIMIT {limit}"

            cur.execute(query)

            cryptos = []
            for row in cur.fetchall():
                cryptos.append({
                    'id': row[0],
                    'name': row[1],
                    'symbol': row[2],
                    'chain': row[3],
                    'coin_gecko_id': row[4],
                    'telegram_channels': row[5] or [],
                    'first_seen_at': row[6],
                    'added_date': row[7],
                    'ohlc_table_name': row[8],
                    'age_days': row[9]
                })

            print(f"📊 Found {len(cryptos)} cryptocurrencies with Telegram channels and OHLC data")
            return cryptos

        except Exception as e:
            print(f"❌ Error fetching cryptocurrencies: {e}")
            return []
        finally:
            conn.close()

    def create_telegram_table(self, coin_gecko_id):
        """Создание таблицы для хранения Telegram сообщений"""
        # Используем coin_gecko_id для имени таблицы
        clean_id = re.sub(r'[^a-zA-Z0-9_]', '_', coin_gecko_id.lower())
        table_name = f"telegram_{clean_id}"

        conn = self.connect_db()
        if not conn:
            return None

        try:
            cur = conn.cursor()

            # Проверка существования таблицы
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = %s
                )
            """, (table_name,))

            table_exists = cur.fetchone()[0]

            if not table_exists:
                # Создание таблицы для сообщений
                create_table_query = sql.SQL("""
                    CREATE TABLE IF NOT EXISTS {} (
                        id SERIAL PRIMARY KEY,
                        crypto_id INTEGER REFERENCES cryptocurrencies(id),
                        message_id VARCHAR(100),
                        message_text TEXT,
                        message_date TIMESTAMP,
                        views INTEGER DEFAULT 0,
                        has_media BOOLEAN DEFAULT FALSE,
                        has_photo BOOLEAN DEFAULT FALSE,
                        has_video BOOLEAN DEFAULT FALSE,
                        links TEXT[],
                        message_url VARCHAR(500),
                        channel_name VARCHAR(255),
                        parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(message_id, channel_name)
                    )
                """).format(sql.Identifier(table_name))

                cur.execute(create_table_query)

                # Создание индексов
                indexes = [
                    f"CREATE INDEX IF NOT EXISTS idx_{table_name}_crypto_id ON {table_name}(crypto_id)",
                    f"CREATE INDEX IF NOT EXISTS idx_{table_name}_message_date ON {table_name}(message_date DESC)",
                    f"CREATE INDEX IF NOT EXISTS idx_{table_name}_views ON {table_name}(views DESC)",
                    f"CREATE INDEX IF NOT EXISTS idx_{table_name}_channel ON {table_name}(channel_name)"
                ]

                for idx in indexes:
                    cur.execute(idx)

                print(f"✅ Created table: {table_name}")
            else:
                print(f"✅ Table already exists: {table_name}")

            conn.commit()
            return table_name

        except Exception as e:
            print(f"❌ Error creating table: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()

    def parse_telegram_channel(self, channel_name, start_date, cutoff_date, max_pages=50):
        """Парсинг Telegram канала с учетом периода сбора"""
        messages = []
        before_id = None
        pages_parsed = 0
        messages_outside_range = 0

        print(
            f"   📅 Collecting messages from {start_date.strftime('%Y-%m-%d %H:%M')} to {cutoff_date.strftime('%Y-%m-%d %H:%M')}")

        while pages_parsed < max_pages:
            # Формируем URL с пагинацией
            if before_id:
                url = f'https://t.me/s/{channel_name}?before={before_id}'
            else:
                url = f'https://t.me/s/{channel_name}'

            try:
                response = self.session.get(url, timeout=10)

                if response.status_code != 200:
                    break

                soup = BeautifulSoup(response.text, 'html.parser')
                message_widgets = soup.find_all('div', class_='tgme_widget_message')

                if not message_widgets:
                    print(f"   ℹ️ No more messages found")
                    break

                page_messages = 0
                oldest_date_on_page = None
                stop_parsing = False

                for widget in message_widgets:
                    msg_data = self._extract_message(widget, channel_name)
                    if msg_data and msg_data.get('date'):
                        # Собираем сообщения в диапазоне от start_date до cutoff_date
                        if start_date <= msg_data['date'] <= cutoff_date:
                            messages.append(msg_data)
                            page_messages += 1

                            # Обновляем самую старую дату на странице
                            if not oldest_date_on_page or msg_data['date'] < oldest_date_on_page:
                                oldest_date_on_page = msg_data['date']
                        elif msg_data['date'] < start_date:
                            messages_outside_range += 1
                            # Если сообщение старше начальной даты, можно остановиться
                            stop_parsing = True
                        elif msg_data['date'] > cutoff_date:
                            messages_outside_range += 1

                # Извлекаем ID последнего сообщения для пагинации
                if message_widgets:
                    last_widget = message_widgets[-1]
                    data_post = last_widget.get('data-post', '')
                    if data_post:
                        before_id = data_post.split('/')[-1]

                pages_parsed += 1

                if page_messages > 0:
                    print(f"   📄 Page {pages_parsed}: {page_messages} messages collected")

                # Если достигли сообщений старше начальной даты, прекращаем
                if stop_parsing or (oldest_date_on_page and oldest_date_on_page < start_date):
                    print(f"   ⏹️ Reached messages older than {self.max_coin_age_days} days")
                    break

                # Небольшая пауза между запросами
                time.sleep(0.5)

            except Exception as e:
                print(f"   ❌ Error parsing page {pages_parsed + 1}: {e}")
                break

        print(f"   📊 Total: {len(messages)} messages collected")
        if messages_outside_range > 0:
            print(f"   ⏭️ Skipped {messages_outside_range} messages (outside date range)")

        return messages

    def _extract_message(self, widget, channel_name):
        """Извлечение данных сообщения"""
        try:
            msg_data = {}

            # ID сообщения
            msg_id = widget.get('data-post', '').split('/')[-1]
            if not msg_id:
                return None

            msg_data['message_id'] = f"{channel_name}_{msg_id}"

            # Текст
            text_elem = widget.find('div', class_='tgme_widget_message_text')
            msg_data['text'] = text_elem.get_text(strip=True) if text_elem else ''

            # Дата
            time_elem = widget.find('time')
            if time_elem and time_elem.get('datetime'):
                try:
                    msg_data['date'] = datetime.fromisoformat(
                        time_elem['datetime'].replace('T', ' ').replace('+00:00', ''))
                except:
                    msg_data['date'] = None
            else:
                msg_data['date'] = None

            # Просмотры
            views_elem = widget.find('span', class_='tgme_widget_message_views')
            views_text = views_elem.get_text(strip=True) if views_elem else '0'

            # Конвертация просмотров
            try:
                if 'K' in views_text:
                    msg_data['views'] = int(float(views_text.replace('K', '')) * 1000)
                elif 'M' in views_text:
                    msg_data['views'] = int(float(views_text.replace('M', '')) * 1000000)
                else:
                    msg_data['views'] = int(views_text.replace(',', ''))
            except:
                msg_data['views'] = 0

            # Медиа
            msg_data['has_photo'] = bool(widget.find('a', class_='tgme_widget_message_photo_wrap'))
            msg_data['has_video'] = bool(widget.find('video'))
            msg_data['has_media'] = msg_data['has_photo'] or msg_data['has_video']

            # Ссылки
            links = []
            for link in widget.find_all('a', href=True):
                href = link['href']
                if not href.startswith('https://t.me/'):
                    links.append(href)
            msg_data['links'] = links

            # URL сообщения
            msg_data['url'] = f"https://t.me/{channel_name}/{msg_id}"
            msg_data['channel_name'] = channel_name

            return msg_data

        except Exception as e:
            return None

    def find_telegram_channels(self, crypto):
        """Получение Telegram каналов из БД"""
        channels = []

        # Берем каналы из БД
        if crypto.get('telegram_channels'):
            channels = crypto['telegram_channels']
            print(f"✅ Found {len(channels)} Telegram channels from database")
            for channel in channels:
                print(f"   📱 @{channel}")
        else:
            print(f"⚠️ No Telegram channels in database for {crypto['name']}")

        return list(set(channels))  # Убираем дубликаты

    def save_messages_to_db(self, crypto_id, table_name, messages):
        """Сохранение сообщений в базу данных"""
        if not messages:
            return 0

        conn = self.connect_db()
        if not conn:
            return 0

        saved_count = 0
        updated_count = 0

        try:
            cur = conn.cursor()

            insert_query = sql.SQL("""
                INSERT INTO {} (
                    crypto_id, message_id, message_text, message_date,
                    views, has_media, has_photo, has_video, links,
                    message_url, channel_name
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (message_id, channel_name) DO UPDATE SET
                    views = EXCLUDED.views,
                    message_text = EXCLUDED.message_text,
                    parsed_at = CURRENT_TIMESTAMP
                RETURNING (xmax = 0) AS inserted
            """).format(sql.Identifier(table_name))

            for msg in messages:
                try:
                    cur.execute(insert_query, (
                        crypto_id,
                        msg['message_id'],
                        msg['text'],
                        msg.get('date'),
                        msg['views'],
                        msg['has_media'],
                        msg['has_photo'],
                        msg['has_video'],
                        msg.get('links', []),
                        msg['url'],
                        msg['channel_name']
                    ))

                    result = cur.fetchone()
                    if result[0]:  # Новая запись
                        saved_count += 1
                    else:  # Обновленная запись
                        updated_count += 1

                except Exception as e:
                    print(f"⚠️ Error saving message: {e}")
                    continue

            conn.commit()
            print(f"   💾 Saved: {saved_count} new, {updated_count} updated")

        except Exception as e:
            print(f"❌ Error saving messages: {e}")
            conn.rollback()
        finally:
            conn.close()

        return saved_count + updated_count

    def should_skip_parsing(self, crypto):
        """Проверка, нужно ли пропустить парсинг монеты"""
        # Монеты любого возраста могут парситься, но собираем только сообщения не старше 60 дней

        # Проверяем, когда последний раз парсили
        conn = self.connect_db()
        if not conn:
            return False, "Cannot check last parsed time"

        try:
            cur = conn.cursor()

            # Проверяем существование поля telegram_last_parsed
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'cryptocurrencies' 
                AND column_name = 'telegram_last_parsed'
            """)

            if not cur.fetchone():
                # Поле не существует, не пропускаем парсинг
                return False, None

            # Теперь безопасно проверяем значение
            cur.execute("""
                SELECT telegram_last_parsed 
                FROM cryptocurrencies 
                WHERE id = %s
            """, (crypto['id'],))

            result = cur.fetchone()
            if result and result[0]:
                last_parsed = result[0]
                hours_since_parsed = (datetime.now() - last_parsed.replace(
                    tzinfo=None)).total_seconds() / 3600 if last_parsed.tzinfo else (
                                                                                                datetime.now() - last_parsed).total_seconds() / 3600

                # Если парсили меньше 24 часов назад, пропускаем
                if hours_since_parsed < 24:
                    return True, f"Already parsed {hours_since_parsed:.1f} hours ago"

            return False, None

        except Exception as e:
            print(f"❌ Error checking last parsed: {e}")
            return False, None
        finally:
            conn.close()

    def process_all_cryptocurrencies(self, limit=None):
        """Обработка всех криптовалют"""
        print("\n🚀 STARTING CRYPTO TELEGRAM PARSER")
        print(f"📅 Collecting messages from OHLC start date (up to {self.max_coin_age_days} days)")
        print("=" * 60)

        # Получение списка криптовалют
        cryptos = self.get_cryptocurrencies(limit)

        if not cryptos:
            print("❌ No cryptocurrencies found with Telegram channels and OHLC data")
            return

        total_messages = 0
        processed_cryptos = 0
        skipped_cryptos = 0
        start_time = time.time()

        # Обработка каждой криптовалюты
        for i, crypto in enumerate(cryptos, 1):
            print(f"\n[{i}/{len(cryptos)}] 📊 Processing {crypto['name']} ({crypto['symbol']})")

            # Проверяем, нужно ли пропустить
            should_skip, reason = self.should_skip_parsing(crypto)
            if should_skip:
                print(f"⏭️ Skipping: {reason}")
                skipped_cryptos += 1
                continue

            # Получаем дату начала из OHLC таблицы
            ohlc_start_date = self.get_ohlc_start_date(crypto)
            if not ohlc_start_date:
                print(f"❌ No OHLC data found for {crypto['symbol']}")
                continue

            # Проверяем тип и конвертируем если необходимо
            if isinstance(ohlc_start_date, (int, float)):
                print(f"   ⚠️ Converting timestamp {ohlc_start_date} to datetime")
                if ohlc_start_date > 10000000000:  # Миллисекунды
                    start_date = datetime.fromtimestamp(ohlc_start_date / 1000)
                else:  # Секунды
                    start_date = datetime.fromtimestamp(ohlc_start_date)
            elif isinstance(ohlc_start_date, datetime):
                start_date = ohlc_start_date
            else:
                print(f"❌ Unexpected OHLC date type: {type(ohlc_start_date)}")
                continue

            # Получение Telegram каналов
            channels = self.find_telegram_channels(crypto)

            if not channels:
                print(f"❌ No Telegram channels found for {crypto['symbol']}")
                continue

            # Создание таблицы с использованием coin_gecko_id
            table_name = self.create_telegram_table(crypto['coin_gecko_id'])

            if not table_name:
                continue

            # Определяем период сбора данных
            # start_date = самая ранняя дата из OHLC (уже определена выше)

            # Приводим start_date к naive datetime если он aware
            if start_date.tzinfo is not None:
                start_date = start_date.replace(tzinfo=None)

            # cutoff_date = текущая дата или start_date + 60 дней (что раньше)
            cutoff_date = datetime.now()
            max_cutoff = start_date + timedelta(days=self.max_coin_age_days)

            # Ограничиваем период 60 днями
            if max_cutoff < cutoff_date:
                cutoff_date = max_cutoff

            days_period = (cutoff_date - start_date).days

            # Если cutoff_date в будущем, ограничиваем текущей датой
            if cutoff_date > datetime.now():
                cutoff_date = datetime.now()

            # ВАЖНО: Если период слишком маленький, расширяем start_date назад
            MIN_COLLECTION_DAYS = 7  # Минимум 7 дней для сбора
            if days_period < MIN_COLLECTION_DAYS:
                extended_start_date = start_date - timedelta(days=MIN_COLLECTION_DAYS - days_period)
                print(
                    f"   ⚠️ Period too short ({days_period} days), extending collection start to {extended_start_date.strftime('%Y-%m-%d')}")
                collection_start_date = extended_start_date
                days_period = (cutoff_date - collection_start_date).days
            else:
                collection_start_date = start_date

            print(f"   📅 OHLC start date: {start_date.strftime('%Y-%m-%d')}")
            print(
                f"   📅 Collection period: {collection_start_date.strftime('%Y-%m-%d')} to {cutoff_date.strftime('%Y-%m-%d')} ({days_period} days)")

            # Парсинг каждого найденного канала
            crypto_messages = 0

            for channel in channels:
                print(f"\n📡 Parsing @{channel}...")
                messages = self.parse_telegram_channel(channel, collection_start_date, cutoff_date)

                if messages:
                    saved = self.save_messages_to_db(crypto['id'], table_name, messages)
                    crypto_messages += saved
                else:
                    print(f"⚠️ No messages found in @{channel} for the specified period")

                time.sleep(1)  # Пауза между каналами

            if crypto_messages > 0:
                total_messages += crypto_messages
                processed_cryptos += 1

                # Обновление информации в основной таблице
                self.update_crypto_info(crypto['id'], table_name)

            # Показываем прогресс
            if i % 5 == 0:
                elapsed = time.time() - start_time
                avg_time = elapsed / i
                remaining = avg_time * (len(cryptos) - i)
                print(f"\n⏱️ Progress: {i}/{len(cryptos)} | "
                      f"Time: {int(elapsed // 60)}m {int(elapsed % 60)}s | "
                      f"ETA: ~{int(remaining // 60)}m")

        # Итоговая статистика
        total_time = time.time() - start_time
        print("\n" + "=" * 60)
        print("📊 PARSING COMPLETED")
        print(f"   Total time: {int(total_time // 60)}m {int(total_time % 60)}s")
        print(f"   Processed cryptos: {processed_cryptos}")
        print(f"   Skipped cryptos: {skipped_cryptos}")
        print(f"   Total messages saved: {total_messages}")
        if len(cryptos) > 0:
            print(f"   Average time per crypto: {total_time / len(cryptos):.2f}s")
        print("=" * 60)

    def update_crypto_info(self, crypto_id, table_name):
        """Обновление информации о криптовалюте"""
        conn = self.connect_db()
        if not conn:
            return

        try:
            cur = conn.cursor()

            # Проверяем существование полей
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'cryptocurrencies' 
                AND column_name IN ('telegram_table_name', 'telegram_message_count', 'telegram_last_parsed')
            """)

            existing_columns = [row[0] for row in cur.fetchall()]

            # Добавляем только те поля, которых нет
            if 'telegram_table_name' not in existing_columns:
                cur.execute("ALTER TABLE cryptocurrencies ADD COLUMN telegram_table_name VARCHAR(100)")
            if 'telegram_message_count' not in existing_columns:
                cur.execute("ALTER TABLE cryptocurrencies ADD COLUMN telegram_message_count INTEGER DEFAULT 0")
            if 'telegram_last_parsed' not in existing_columns:
                cur.execute("ALTER TABLE cryptocurrencies ADD COLUMN telegram_last_parsed TIMESTAMP")

            # Получаем количество сообщений в таблице
            count_query = sql.SQL("""
                SELECT COUNT(*) FROM {}
            """).format(sql.Identifier(table_name))

            cur.execute(count_query)
            message_count = cur.fetchone()[0]

            # Обновляем информацию
            cur.execute("""
                UPDATE cryptocurrencies 
                SET telegram_table_name = %s,
                    telegram_message_count = %s,
                    telegram_last_parsed = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (table_name, message_count, crypto_id))

            conn.commit()
            print(f"✅ Updated crypto info: {message_count} total messages")

        except Exception as e:
            print(f"❌ Error updating crypto info: {e}")
            conn.rollback()
        finally:
            conn.close()


def main():
    """Главная функция - автоматический запуск"""
    parser = CryptoTelegramDBParser()

    # Проверка аргументов командной строки
    limit = None
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
            print(f"⚠️ Limited mode: processing first {limit} cryptocurrencies")
        except ValueError:
            print(f"Invalid limit: {sys.argv[1]}")
            sys.exit(1)

    # Автоматический запуск
    parser.process_all_cryptocurrencies(limit=limit)


if __name__ == "__main__":
    main()
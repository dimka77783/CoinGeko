#!/usr/bin/env python3
"""
Асинхронный обновлятор OHLC данных для криптовалют
Создает таблицы с именем ohlc_{coin_gecko_id} БЕЗ ДАТ
"""

import asyncio
import aiohttp
import psycopg2
from psycopg2.extras import RealDictCursor
import logging
from datetime import datetime, timedelta
import os
import time
from typing import List, Dict, Optional, Tuple

# Настройка логирования
log_level = logging.DEBUG if os.environ.get('DEBUG', '').lower() == 'true' else logging.INFO
logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Константы
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': os.environ.get('DB_PORT', '5432'),
    'database': os.environ.get('DB_NAME', 'crypto_db'),
    'user': os.environ.get('DB_USER', 'crypto_user'),
    'password': os.environ.get('DB_PASSWORD', 'crypto_password')
}

# API настройки
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
OHLC_ENDPOINT = f"{COINGECKO_BASE_URL}/coins/{{coin_id}}/ohlc"

# Параметры обновления
MAX_CONCURRENT_REQUESTS = 2
REQUEST_DELAY = 5
RETRY_DELAY = 60
MAX_RETRIES = 3
DAYS_TO_FETCH = 14  # Получаем 14 дней данных
MAX_AGE_DAYS = 60  # Не обновлять монеты старше 60 дней
MIN_AGE_DAYS = 2  # Не обновлять монеты младше 2 дней

# Семафор для контроля параллельных запросов
semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

# Счетчики ошибок
error_counter = {
    '429': 0,
    '404': 0,
    'network': 0
}


def get_db_connection():
    """Создает подключение к БД"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к БД: {e}")
        return None


def safe_table_name(coin_gecko_id: str) -> str:
    """
    Создает безопасное имя таблицы из coin_gecko_id
    БЕЗ ДАТЫ - только префикс ohlc_ и обработанный ID
    """
    if not coin_gecko_id:
        return None

    # Приводим к нижнему регистру
    safe_name = coin_gecko_id.lower()

    # Заменяем все не-алфавитно-цифровые символы на подчеркивание
    safe_name = ''.join(c if c.isalnum() else '_' for c in safe_name)

    # Убираем множественные подчеркивания
    while '__' in safe_name:
        safe_name = safe_name.replace('__', '_')

    # Убираем подчеркивания в начале и конце
    safe_name = safe_name.strip('_')

    # Ограничиваем длину (PostgreSQL максимум 63 символа)
    if len(safe_name) > 50:  # Оставляем место для префикса
        safe_name = safe_name[:50]

    # Добавляем префикс
    return f"ohlc_{safe_name}"


def create_ohlc_table(table_name: str) -> bool:
    """Создает таблицу OHLC если не существует"""
    if not table_name:
        logger.error("❌ Пустое имя таблицы")
        return False

    conn = get_db_connection()
    if not conn:
        return False

    cursor = conn.cursor()
    try:
        # Проверяем существование таблицы
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = %s
            )
        """, (table_name,))

        if cursor.fetchone()[0]:
            logger.debug(f"ℹ️ Таблица {table_name} уже существует")
            return True

        # Создаем таблицу
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS "{table_name}" (
                id SERIAL PRIMARY KEY,
                timestamp BIGINT NOT NULL UNIQUE,
                datetime TIMESTAMP NOT NULL,
                date DATE NOT NULL,
                time TIME NOT NULL,
                open DECIMAL(20, 8) NOT NULL,
                high DECIMAL(20, 8) NOT NULL,
                low DECIMAL(20, 8) NOT NULL,
                close DECIMAL(20, 8) NOT NULL,
                volume DECIMAL(20, 8) DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Создаем индексы
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_timestamp ON "{table_name}"(timestamp)')
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_datetime ON "{table_name}"(datetime)')
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_date ON "{table_name}"(date)')

        conn.commit()
        logger.info(f"✅ Создана таблица {table_name}")
        return True

    except Exception as e:
        logger.error(f"❌ Ошибка создания таблицы {table_name}: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def update_coin_table_name(coin_id: int, new_table_name: str) -> bool:
    """Обновляет имя таблицы в записи криптовалюты"""
    conn = get_db_connection()
    if not conn:
        return False

    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE cryptocurrencies 
            SET ohlc_table_name = %s 
            WHERE id = %s
        """, (new_table_name, coin_id))

        conn.commit()
        logger.info(f"✅ Обновлено имя таблицы для coin_id={coin_id}: {new_table_name}")
        return True

    except Exception as e:
        logger.error(f"❌ Ошибка обновления имени таблицы: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def ensure_table_for_coin(coin_info: Dict) -> Optional[str]:
    """
    Проверяет и создает таблицу для монеты
    Возвращает имя таблицы или None при ошибке
    """
    coin_id = coin_info['id']
    coin_gecko_id = coin_info.get('coin_gecko_id')
    current_table_name = coin_info.get('ohlc_table_name')

    if not coin_gecko_id:
        logger.error(f"❌ Отсутствует coin_gecko_id для {coin_info['symbol']}")
        return None

    # Генерируем правильное имя таблицы БЕЗ ДАТЫ
    correct_table_name = safe_table_name(coin_gecko_id)

    if not correct_table_name:
        logger.error(f"❌ Не удалось сгенерировать имя таблицы для {coin_gecko_id}")
        return None

    # Логируем для отладки
    logger.debug(f"📝 coin_gecko_id: {coin_gecko_id} -> table_name: {correct_table_name}")

    # Если имя не совпадает или отсутствует - обновляем
    if current_table_name != correct_table_name:
        logger.info(f"📝 Обновление имени таблицы: {current_table_name} -> {correct_table_name}")
        update_coin_table_name(coin_id, correct_table_name)

    # Создаем таблицу если не существует
    if create_ohlc_table(correct_table_name):
        return correct_table_name

    return None


def get_coins_for_update():
    """Получает список монет для обновления OHLC"""
    conn = get_db_connection()
    if not conn:
        return []

    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        query = """
        SELECT 
            id,
            name,
            symbol,
            coin_gecko_id,
            added_date,
            ohlc_table_name,
            EXTRACT(EPOCH FROM (NOW() - added_date::timestamp))/86400 as days_since_listing
        FROM cryptocurrencies
        WHERE 
            -- Есть CoinGecko ID
            coin_gecko_id IS NOT NULL 
            AND coin_gecko_id != ''
            -- Монета старше MIN_AGE_DAYS
            AND added_date::timestamp < NOW() - INTERVAL '%s days'
            -- Монета младше MAX_AGE_DAYS
            AND added_date::timestamp > NOW() - INTERVAL '%s days'
        ORDER BY added_date DESC
        LIMIT 50
        """

        cursor.execute(query, (MIN_AGE_DAYS, MAX_AGE_DAYS))
        coins = cursor.fetchall()

        logger.info(f"📊 Найдено {len(coins)} монет для обновления")
        return coins

    except Exception as e:
        logger.error(f"❌ Ошибка при получении монет: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


async def fetch_ohlc_data(session: aiohttp.ClientSession, coin_id: str) -> Optional[List[Dict]]:
    """Получает OHLC данные с CoinGecko API"""

    if not coin_id or not coin_id.strip():
        logger.error("❌ Пустой coin_id")
        return None

    coin_id = coin_id.strip()
    url = OHLC_ENDPOINT.format(coin_id=coin_id)

    params = {
        'vs_currency': 'usd',
        'days': DAYS_TO_FETCH
    }

    headers = {
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
    }

    logger.debug(f"🌐 Запрос OHLC: {url} (days={DAYS_TO_FETCH})")

    async with semaphore:
        for attempt in range(MAX_RETRIES):
            try:
                await asyncio.sleep(REQUEST_DELAY)

                async with session.get(url, params=params, headers=headers, timeout=30) as response:

                    if response.status == 200:
                        data = await response.json()

                        if data and isinstance(data, list):
                            ohlc_list = []

                            for item in data:
                                if len(item) >= 5:
                                    timestamp = item[0]
                                    dt = datetime.fromtimestamp(timestamp / 1000)

                                    ohlc_list.append({
                                        'timestamp': timestamp,
                                        'datetime': dt,
                                        'date': dt.date(),
                                        'time': dt.time(),
                                        'open': float(item[1]),
                                        'high': float(item[2]),
                                        'low': float(item[3]),
                                        'close': float(item[4])
                                    })

                            logger.info(f"✅ Получено {len(ohlc_list)} OHLC записей для {coin_id}")
                            error_counter['429'] = max(0, error_counter['429'] - 1)
                            return ohlc_list

                        else:
                            logger.warning(f"⚠️ Пустой ответ для {coin_id}")
                            return []

                    elif response.status == 404:
                        error_counter['404'] += 1
                        logger.error(f"❌ Монета не найдена: {coin_id}")
                        return None

                    elif response.status == 429:
                        error_counter['429'] += 1
                        retry_after = int(response.headers.get('Retry-After', RETRY_DELAY))
                        logger.warning(
                            f"⚠️ Rate limit для {coin_id} (попытка {attempt + 1}/{MAX_RETRIES}), ожидание {retry_after} сек")
                        await asyncio.sleep(retry_after)

                    else:
                        text = await response.text()
                        logger.error(f"❌ HTTP {response.status} для {coin_id}: {text[:200]}")
                        break

            except asyncio.TimeoutError:
                error_counter['network'] += 1
                logger.warning(f"⏱️ Таймаут для {coin_id} (попытка {attempt + 1}/{MAX_RETRIES})")

            except Exception as e:
                error_counter['network'] += 1
                logger.error(f"❌ Ошибка для {coin_id}: {e}")

            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(10 * (attempt + 1))

    return None


def save_ohlc_to_db(table_name: str, coin_info: Dict, ohlc_data: List[Dict]) -> Tuple[int, int]:
    """Сохраняет OHLC данные в БД без дубликатов"""

    if not ohlc_data or not table_name:
        return 0, 0

    conn = get_db_connection()
    if not conn:
        return 0, 0

    cursor = conn.cursor()

    # Получаем timestamp даты листинга
    if isinstance(coin_info['added_date'], str):
        listing_date = datetime.strptime(coin_info['added_date'], '%Y-%m-%d')
    else:
        listing_date = datetime.combine(coin_info['added_date'], datetime.min.time())

    listed_timestamp = listing_date.timestamp() * 1000

    saved_count = 0
    skipped_count = 0

    try:
        for ohlc in ohlc_data:
            # Фильтрация данных

            # 1. Проверяем, что данные не старше даты листинга
            if ohlc['timestamp'] < listed_timestamp:
                skipped_count += 1
                continue

            # 2. Проверяем, что данные не из будущего
            if ohlc['timestamp'] > time.time() * 1000:
                skipped_count += 1
                continue

            # 3. Проверяем корректность OHLC
            if (ohlc['high'] < ohlc['low'] or
                    ohlc['high'] < ohlc['open'] or
                    ohlc['high'] < ohlc['close'] or
                    ohlc['low'] > ohlc['open'] or
                    ohlc['low'] > ohlc['close']):
                skipped_count += 1
                continue

            # 4. Проверяем на разумные значения
            prices = [ohlc['open'], ohlc['high'], ohlc['low'], ohlc['close']]
            if any(p <= 0 for p in prices):
                skipped_count += 1
                continue

            try:
                # Вставляем с ON CONFLICT DO NOTHING для избежания дубликатов
                cursor.execute(f"""
                    INSERT INTO "{table_name}" 
                    (timestamp, datetime, date, time, open, high, low, close)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (timestamp) DO NOTHING
                """, (
                    ohlc['timestamp'],
                    ohlc['datetime'],
                    ohlc['date'],
                    ohlc['time'],
                    ohlc['open'],
                    ohlc['high'],
                    ohlc['low'],
                    ohlc['close']
                ))

                if cursor.rowcount > 0:
                    saved_count += 1

            except Exception as e:
                logger.error(f"❌ Ошибка вставки записи: {e}")
                skipped_count += 1

        conn.commit()

        if skipped_count > 0:
            logger.debug(f"⚠️ Пропущено записей: {skipped_count}")

        return saved_count, skipped_count

    except Exception as e:
        logger.error(f"❌ Ошибка сохранения в {table_name}: {e}")
        conn.rollback()
        return 0, 0
    finally:
        cursor.close()
        conn.close()


def get_table_stats(table_name: str) -> Dict:
    """Получает статистику по таблице OHLC"""
    if not table_name:
        return {}

    conn = get_db_connection()
    if not conn:
        return {}

    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cursor.execute(f"""
            SELECT 
                COUNT(*) as total_records,
                MIN(datetime) as first_record,
                MAX(datetime) as last_record
            FROM "{table_name}"
        """)

        result = cursor.fetchone()
        return dict(result) if result else {}

    except Exception as e:
        logger.debug(f"Ошибка получения статистики для {table_name}: {e}")
        return {}
    finally:
        cursor.close()
        conn.close()


async def update_coin_ohlc(session: aiohttp.ClientSession, coin: Dict) -> bool:
    """Обновляет OHLC данные для одной монеты"""

    name = coin['name']
    symbol = coin['symbol']
    coin_id = coin['coin_gecko_id']
    days_since_listing = coin.get('days_since_listing', 0)

    logger.info(f"\n🔄 Обновление {name} ({symbol})")
    logger.info(f"  📅 Возраст: {days_since_listing:.1f} дней")
    logger.info(f"  🆔 CoinGecko ID: {coin_id}")

    # Проверяем/создаем таблицу
    table_name = ensure_table_for_coin(coin)
    if not table_name:
        logger.error(f"  ❌ Не удалось создать таблицу")
        return False

    logger.info(f"  📁 Таблица: {table_name}")

    # Обновляем информацию о таблице в объекте монеты
    coin['ohlc_table_name'] = table_name

    # Получаем текущую статистику таблицы
    table_stats = get_table_stats(table_name)

    if table_stats:
        logger.info(f"  📊 Текущих записей: {table_stats.get('total_records', 0)}")
        if table_stats.get('last_record'):
            logger.info(f"  📅 Последняя запись: {table_stats['last_record']}")

    # Получаем OHLC данные
    ohlc_data = await fetch_ohlc_data(session, coin_id)

    if ohlc_data is None:
        logger.error(f"  ❌ Не удалось получить данные")
        return False

    if not ohlc_data:
        logger.warning(f"  ⚠️ Нет OHLC данных")
        return False

    # Сохраняем в БД
    saved_count, skipped_count = save_ohlc_to_db(table_name, coin, ohlc_data)

    # Получаем обновленную статистику
    new_stats = get_table_stats(table_name)

    if saved_count > 0:
        logger.info(f"  ✅ Сохранено новых записей: {saved_count}")
    else:
        logger.info(f"  ℹ️ Нет новых данных (все записи уже существуют)")

    if new_stats:
        logger.info(f"  📊 Итого записей: {new_stats.get('total_records', 0)}")

    return True


async def update_batch(session: aiohttp.ClientSession, coins: List[Dict]) -> Tuple[int, int]:
    """Обновляет батч монет"""

    successful = 0
    failed = 0

    tasks = [update_coin_ohlc(session, coin) for coin in coins]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"❌ Ошибка в задаче для {coins[i]['symbol']}: {result}")
            failed += 1
        elif result:
            successful += 1
        else:
            failed += 1

    return successful, failed


def get_db_stats():
    """Получает общую статистику БД"""
    conn = get_db_connection()
    if not conn:
        return {}

    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Общее количество монет
        cursor.execute("SELECT COUNT(*) as total FROM cryptocurrencies")
        total_coins = cursor.fetchone()['total']

        # Монеты с CoinGecko ID
        cursor.execute("""
            SELECT COUNT(*) as with_id 
            FROM cryptocurrencies 
            WHERE coin_gecko_id IS NOT NULL AND coin_gecko_id != ''
        """)
        with_id = cursor.fetchone()['with_id']

        # Активные монеты (младше MAX_AGE_DAYS)
        cursor.execute("""
            SELECT COUNT(*) as active 
            FROM cryptocurrencies 
            WHERE added_date::timestamp > NOW() - INTERVAL '%s days'
            AND coin_gecko_id IS NOT NULL AND coin_gecko_id != ''
        """, (MAX_AGE_DAYS,))
        active_coins = cursor.fetchone()['active']

        # Монеты с OHLC таблицами
        cursor.execute("""
            SELECT COUNT(*) as with_ohlc
            FROM cryptocurrencies c
            WHERE c.ohlc_table_name IS NOT NULL
            AND EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = c.ohlc_table_name
            )
        """)
        with_ohlc = cursor.fetchone()['with_ohlc']

        return {
            'total_coins': total_coins,
            'with_id': with_id,
            'active_coins': active_coins,
            'with_ohlc': with_ohlc
        }

    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики: {e}")
        return {}
    finally:
        cursor.close()
        conn.close()


async def main():
    """Основная функция обновления"""
    print("=" * 60)
    print("🔄 ОБНОВЛЕНИЕ OHLC ДАННЫХ (БЕЗ ДАТ В ИМЕНАХ ТАБЛИЦ)")
    print(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"API URL: {OHLC_ENDPOINT}")
    print(f"Период данных: {DAYS_TO_FETCH} дней")
    print(f"Макс. одновременных запросов: {MAX_CONCURRENT_REQUESTS}")
    print(f"Задержка между запросами: {REQUEST_DELAY} сек")
    print("=" * 60)

    # Получаем и показываем статистику
    stats = get_db_stats()
    if stats:
        print("\n📊 Статистика БД:")
        print(f"  Всего монет: {stats.get('total_coins', 0)}")
        print(f"  С CoinGecko ID: {stats.get('with_id', 0)}")
        print(f"  Активных (<{MAX_AGE_DAYS} дней): {stats.get('active_coins', 0)}")
        print(f"  С OHLC таблицами: {stats.get('with_ohlc', 0)}")

    # Получаем монеты для обновления
    coins = get_coins_for_update()

    if not coins:
        print("\n✅ Нет монет для обновления")
        return

    print(f"\n🔄 Начинаем обновление {len(coins)} монет...")
    print("📌 Таблицы будут создаваться БЕЗ ДАТ в именах!")

    # Создаем сессию
    timeout = aiohttp.ClientTimeout(total=60, connect=15)
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT_REQUESTS)

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:

        # Обрабатываем батчами
        batch_size = 5
        total_successful = 0
        total_failed = 0

        for i in range(0, len(coins), batch_size):
            batch = coins[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(coins) + batch_size - 1) // batch_size

            print(f"\n📦 Батч {batch_num}/{total_batches} ({len(batch)} монет)")

            successful, failed = await update_batch(session, batch)
            total_successful += successful
            total_failed += failed

            # Пауза между батчами
            if i + batch_size < len(coins):
                print(f"⏸️ Пауза между батчами...")
                await asyncio.sleep(15)

    # Итоговая статистика
    print(f"\n📊 Результаты обновления:")
    print(f"  ✅ Успешно: {total_successful}")
    print(f"  ❌ Ошибок: {total_failed}")
    if (total_successful + total_failed) > 0:
        print(f"  📈 Успешность: {total_successful / (total_successful + total_failed) * 100:.1f}%")

    # Статистика ошибок
    if any(error_counter.values()):
        print(f"\n⚠️ Ошибки:")
        if error_counter['429']:
            print(f"  Rate limit (429): {error_counter['429']}")
        if error_counter['404']:
            print(f"  Не найдено (404): {error_counter['404']}")
        if error_counter['network']:
            print(f"  Сетевые ошибки: {error_counter['network']}")

    print("\n✅ Обновление завершено")
    print("📌 Все таблицы созданы БЕЗ ДАТ в именах!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
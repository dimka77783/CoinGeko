#!/usr/bin/env python3
"""
Асинхронный парсер криптовалют с улучшенным поиском названий
"""
import aiohttp
import asyncio
import json
import os
import re
from datetime import datetime, timedelta
import time
import ssl
import psycopg2
from psycopg2.pool import SimpleConnectionPool
import sys
from typing import List, Dict, Optional, Tuple
import logging

# Настройка логирования
log_level = logging.DEBUG if os.environ.get('DEBUG', '').lower() == 'true' else logging.INFO
logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Настройки
BASE_URL = "https://www.coingecko.com/ru/new-cryptocurrencies"
API_BASE = "https://api.coingecko.com/api/v3"
MAX_COINS = int(os.environ.get('MAX_COINS', 30))
MIN_AGE_DAYS = 1
MAX_CONCURRENT_REQUESTS = 3  # Максимум одновременных запросов

# Увеличенные задержки для избежания блокировки
DELAYS = {
    'between_coins': 15,
    'before_search': 5,
    'after_ohlc': 8,
    'rate_limit': 65,
    'after_400_error': 20,
    'after_429_error': 120
}

# База данных
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': os.environ.get('DB_PORT', '5432'),
    'database': os.environ.get('DB_NAME', 'crypto_db'),
    'user': os.environ.get('DB_USER', 'crypto_user'),
    'password': os.environ.get('DB_PASSWORD', 'crypto_password')
}

# Глобальный пул соединений
db_pool = None

# Счетчик ошибок
error_counter = {
    '400': 0,
    '429': 0,
    'last_429': None,
    'consecutive_400': 0
}

# Семафор для ограничения количества одновременных запросов
request_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)


def init_db_pool():
    """Инициализация пула соединений к БД"""
    global db_pool
    try:
        db_pool = SimpleConnectionPool(1, 10, **DB_CONFIG)
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка создания пула БД: {e}")
        return False


def get_db_connection():
    """Получение соединения из пула"""
    if db_pool:
        return db_pool.getconn()
    return None


def put_db_connection(conn):
    """Возврат соединения в пул"""
    if db_pool and conn:
        db_pool.putconn(conn)


def close_db_pool():
    """Закрытие пула соединений"""
    global db_pool
    if db_pool:
        db_pool.closeall()
        db_pool = None


def create_ssl_context():
    """SSL контекст для HTTPS"""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def clean_text(html):
    """Очищает HTML от тегов"""
    text = re.sub(r'<[^>]+>', '', html)
    return ' '.join(text.split()).strip()


def extract_percent(cell):
    """Извлекает процент из ячейки"""
    text = clean_text(cell)
    match = re.search(r'([-+]?\d+[,.]?\d*%)', text)
    return match.group(1) if match else text or "N/A"


def parse_date(text):
    """Преобразует текст даты в YYYY-MM-DD"""
    now = datetime.now()

    if "недавно" in text or "около 1 часа" in text:
        return now.strftime('%Y-%m-%d')

    days_match = re.search(r'(\d+)\s*дн', text)
    if days_match:
        days = int(days_match.group(1))
        return (now - timedelta(days=days)).strftime('%Y-%m-%d')

    hours_match = re.search(r'(\d+)\s*час', text)
    if hours_match:
        hours = int(hours_match.group(1))
        return (now - timedelta(hours=hours)).strftime('%Y-%m-%d')

    return now.strftime('%Y-%m-%d')


async def fetch_page(session: aiohttp.ClientSession) -> Optional[str]:
    """Асинхронная загрузка страницы с новыми монетами"""
    logger.info("🌐 Загрузка страницы CoinGecko...")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8'
    }

    try:
        async with session.get(BASE_URL, headers=headers, ssl=False, timeout=30) as response:
            html = await response.text()
            logger.info(f"✅ Страница загружена: {len(html)} байт")
            return html
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки: {e}")
        return None


def parse_row_improved(row_html: str) -> Optional[Dict]:
    """Улучшенный парсинг с правильным извлечением имени и символа"""
    crypto = {}

    # Извлекаем все ячейки
    cells = re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL)
    if len(cells) < 11:
        return None

    # ПАРСИНГ ИМЕНИ И СИМВОЛА ИЗ ЯЧЕЙКИ 2
    name_cell = cells[2]

    # Отладка для первой монеты
    if logger.level == logging.DEBUG:
        logger.debug(f"Содержимое ячейки с именем: {name_cell[:200]}...")

    # Паттерны для извлечения имени - обновлены на основе реальной структуры
    name_patterns = [
        r'class="[^"]*tw-font-[^"]*"[^>]*>([^<]+)<',  # Текст с font классом (основной паттерн)
        r'class="[^"]*font-[^"]*"[^>]*>([^<]+)<',  # Альтернативный font класс
        r'data-view-component="true"[^>]*>([^<]+)<',  # Текст с data-view-component
        r'>([^<>]+)<br',  # Текст перед <br>
        r'<div[^>]*>([^<]+)</div>',  # Текст внутри div
        r'<a[^>]*>([^<]+)</a>',  # Текст в ссылке
    ]

    crypto['name'] = "Unknown"
    for pattern in name_patterns:
        matches = re.findall(pattern, name_cell)
        for match in matches:
            name = match.strip()
            # Проверяем что это имя, а не символ или другой текст
            if (name and
                    len(name) >= 2 and
                    not name.isupper() and  # Имя обычно не полностью в верхнем регистре
                    not re.match(r'^[A-Z0-9]+$', name) and  # Не только заглавные и цифры
                    name not in ['', ' ', '\n', '\t']):
                crypto['name'] = name
                break
        if crypto['name'] != "Unknown":
            break

    # ПАРСИНГ СИМВОЛА - ищем в очищенном тексте после имени
    # Сначала получаем очищенный текст
    clean_text_content = re.sub(r'<[^>]+>', ' ', name_cell)
    clean_text_content = ' '.join(clean_text_content.split())

    crypto['symbol'] = ""

    # Сначала пробуем найти символ в HTML структуре
    symbol_patterns = [
        r'<span[^>]*class="[^"]*tw-text-gray-500[^"]*"[^>]*>([^<]+)</span>',
        r'<span[^>]*class="[^"]*gray[^"]*"[^>]*>([^<]+)</span>',
        r'<div[^>]*class="[^"]*tw-text-gray[^"]*"[^>]*>([^<]+)</div>',
        r'alt="([A-Z0-9]+)"',  # Символ в alt атрибуте изображения
    ]

    for pattern in symbol_patterns:
        matches = re.findall(pattern, name_cell, re.IGNORECASE)
        for match in matches:
            symbol = match.strip().upper()
            if (symbol and
                    len(symbol) >= 2 and
                    len(symbol) <= 20 and
                    not symbol.startswith('$') and
                    symbol != crypto['name'].upper() and
                    re.match(r'^[A-Z0-9]+$', symbol)):
                crypto['symbol'] = symbol
                break
        if crypto['symbol']:
            break

    # Если не нашли в HTML, ищем в очищенном тексте
    if not crypto['symbol'] and crypto['name'] != "Unknown":
        # Ищем текст после имени
        name_pos = clean_text_content.find(crypto['name'])
        if name_pos != -1:
            after_name = clean_text_content[name_pos + len(crypto['name']):].strip()
            words = after_name.split()
            if words:
                # Первое слово после имени обычно символ
                potential_symbol = words[0].upper()
                # Очищаем от специальных символов
                potential_symbol = re.sub(r'[^A-Z0-9]', '', potential_symbol)
                if potential_symbol and len(potential_symbol) >= 2 and len(potential_symbol) <= 10:
                    crypto['symbol'] = potential_symbol

    # Если символ все еще не найден, ищем любое слово в верхнем регистре
    if not crypto['symbol']:
        words = clean_text_content.split()
        for word in words:
            word_cleaned = re.sub(r'[^A-Z0-9]', '', word.upper())
            if (word_cleaned and
                    len(word_cleaned) >= 2 and
                    len(word_cleaned) <= 10 and
                    word_cleaned != crypto['name'].upper() and
                    word_cleaned not in ['THE', 'AND', 'FOR', 'WITH', 'NEW', 'CRYPTO']):  # Исключаем служебные слова
                crypto['symbol'] = word_cleaned
                break

    # Специальная обработка для монет с символами в нижнем регистре
    if not crypto['symbol'] and crypto['name'] not in ["Unknown", ""]:
        # Для монет типа "Rose", "aixrp", "farthouse", "Runnit"
        # где символ может совпадать с именем
        name_as_symbol = re.sub(r'[^A-Z0-9]', '', crypto['name'].upper())
        if len(name_as_symbol) >= 2 and len(name_as_symbol) <= 10:
            crypto['symbol'] = name_as_symbol

    # Если имя все еще Unknown, но есть символ, используем символ как имя
    if crypto['name'] == "Unknown" and crypto['symbol']:
        # Ищем более подходящее имя в очищенном тексте
        words = clean_text_content.split()
        for word in words:
            if (word and
                    len(word) > len(crypto['symbol']) and
                    not word.isupper() and
                    crypto['symbol'].upper() in word.upper()):
                crypto['name'] = word
                break

        # Если не нашли, используем символ как имя
        if crypto['name'] == "Unknown":
            crypto['name'] = crypto['symbol'].title()

    # Остальные поля
    crypto['price'] = clean_text(cells[3]) if len(cells) > 3 else "N/A"
    crypto['change_24h'] = extract_percent(cells[4]) if len(cells) > 4 else "N/A"
    crypto['chain'] = clean_text(cells[5]) if len(cells) > 5 else "Unknown"
    crypto['market_cap'] = clean_text(cells[7]) if len(cells) > 7 else "N/A"
    crypto['fdv'] = clean_text(cells[9]) if len(cells) > 9 else "N/A"

    # Дата добавления
    added_text = clean_text(cells[10]) if len(cells) > 10 else "недавно"
    crypto['added'] = parse_date(added_text)
    crypto['added_raw'] = added_text

    # Отладочная информация
    if not crypto['symbol'] or crypto['name'] == "Unknown":
        logger.warning(f"  ⚠️ Проблема с парсингом: {crypto['name']} ({crypto['symbol']})")
        clean_cell = re.sub(r'<[^>]+>', ' ', name_cell)
        logger.debug(f"     Содержимое: {clean_cell[:100]}...")

    return crypto


def parse_html(html: str) -> List[Dict]:
    """Парсит HTML и извлекает данные о монетах"""
    logger.info("🔍 Парсинг данных о монетах...")

    cryptos = []

    # Ищем строки таблицы
    table_pattern = r'<tr[^>]*class="[^"]*hover:tw-bg[^"]*"[^>]*>(.*?)</tr>'
    rows = re.findall(table_pattern, html, re.DOTALL)

    logger.info(f"📊 Найдено строк: {len(rows)}, обработаем: {min(len(rows), MAX_COINS)}")

    # Отладка: выводим первую строку для анализа структуры
    if rows and len(rows) > 0:
        logger.debug("Пример первой строки HTML:")
        logger.debug(rows[0][:500] + "...")

    for i, row in enumerate(rows[:MAX_COINS]):
        crypto = parse_row_improved(row)
        if crypto:
            cryptos.append(crypto)
            logger.info(f"  [{i + 1}] {crypto['name']} ({crypto['symbol']})")

    return cryptos


async def search_coin_id(session: aiohttp.ClientSession, name: str, symbol: str) -> Optional[str]:
    """Асинхронный поиск ID монеты в CoinGecko API"""
    logger.info(f"  🔍 Поиск ID для {name} ({symbol})...")

    # Адаптивная задержка
    if error_counter['429'] > 0:
        extra_delay = min(error_counter['429'] * 15, 90)
        await asyncio.sleep(DELAYS['before_search'] + extra_delay)
    elif error_counter['consecutive_400'] > 3:
        await asyncio.sleep(DELAYS['before_search'] + 10)
    else:
        await asyncio.sleep(DELAYS['before_search'])

    search_queries = []
    if symbol:
        search_queries.append(symbol.lower())
    if name and name != "Unknown":
        search_queries.append(name.lower())

    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
        'Accept': 'application/json'
    }

    for query in search_queries:
        if not query:
            continue

        url = f"{API_BASE}/search?query={query}"

        try:
            async with request_semaphore:
                async with session.get(url, headers=headers, ssl=False, timeout=15) as response:
                    if response.status == 200:
                        data = await response.json()
                        error_counter['consecutive_400'] = 0

                        if 'coins' in data and data['coins']:
                            # Точное совпадение по символу
                            if symbol:
                                for coin in data['coins']:
                                    if coin.get('symbol', '').upper() == symbol.upper():
                                        logger.info(f"    ✅ Найден: {coin['id']}")
                                        return coin['id']

                            # Поиск по названию
                            if name and name != "Unknown":
                                name_lower = name.lower()
                                for coin in data['coins']:
                                    coin_name = coin.get('name', '').lower()
                                    if name_lower in coin_name or coin_name in name_lower:
                                        logger.info(f"    ⚠️ Найден по названию: {coin['id']}")
                                        return coin['id']

                            # Первый результат если символ совпадает
                            if symbol and data['coins']:
                                first_coin = data['coins'][0]
                                if first_coin.get('symbol', '').upper() == symbol.upper():
                                    logger.info(f"    ⚠️ Использован первый результат: {first_coin['id']}")
                                    return first_coin['id']

                    elif response.status == 429:
                        error_counter['429'] += 1
                        wait_time = DELAYS['after_429_error']
                        logger.warning(f"    ⚠️ Rate limit (429), ожидание {wait_time} сек...")
                        await asyncio.sleep(wait_time)
                    elif response.status == 400:
                        error_counter['400'] += 1
                        error_counter['consecutive_400'] += 1
                        logger.warning(f"    ⚠️ Bad Request (400)")
                        await asyncio.sleep(DELAYS['after_400_error'])
                        return None

        except Exception as e:
            logger.error(f"    ❌ Ошибка: {e}")

    logger.warning(f"    ❌ ID не найден")
    return None


async def fetch_ohlc(session: aiohttp.ClientSession, coin_id: str, age_days: int) -> Optional[List[Dict]]:
    """Асинхронное получение OHLC данных"""
    days_to_fetch = max(1, min(age_days, 7))

    url_variants = [
        f"{API_BASE}/coins/{coin_id}/ohlc?vs_currency=usd&days={days_to_fetch}",
        f"{API_BASE}/coins/{coin_id}/ohlc?vs_currency=usd&days=1",
        f"{API_BASE}/coins/{coin_id}/market_chart?vs_currency=usd&days={days_to_fetch}&interval=hourly"
    ]

    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
        'Accept': 'application/json'
    }

    for url_index, url in enumerate(url_variants):
        max_retries = 2 if url_index == 0 else 1
        retry_count = 0

        while retry_count < max_retries:
            try:
                async with request_semaphore:
                    async with session.get(url, headers=headers, ssl=False, timeout=20) as response:
                        if response.status == 200:
                            data = await response.json()
                            error_counter['consecutive_400'] = 0

                            ohlc_data = []

                            if isinstance(data, list) and data:
                                for candle in data:
                                    if len(candle) >= 5:
                                        timestamp = candle[0]
                                        dt = datetime.fromtimestamp(timestamp / 1000)

                                        ohlc_data.append({
                                            'timestamp': timestamp,
                                            'datetime': dt,
                                            'date': dt.date(),
                                            'time': dt.time(),
                                            'open': candle[1],
                                            'high': candle[2],
                                            'low': candle[3],
                                            'close': candle[4]
                                        })

                            elif isinstance(data, dict) and 'prices' in data:
                                prices = data.get('prices', [])
                                if prices:
                                    for i in range(0, len(prices), 24):
                                        daily_prices = prices[i:i + 24]
                                        if daily_prices:
                                            timestamp = daily_prices[0][0]
                                            dt = datetime.fromtimestamp(timestamp / 1000)

                                            daily_values = [p[1] for p in daily_prices]
                                            ohlc_data.append({
                                                'timestamp': timestamp,
                                                'datetime': dt,
                                                'date': dt.date(),
                                                'time': dt.time(),
                                                'open': daily_values[0],
                                                'high': max(daily_values),
                                                'low': min(daily_values),
                                                'close': daily_values[-1]
                                            })

                            if ohlc_data:
                                logger.info(f"    ✅ Получено {len(ohlc_data)} свечей")
                                await asyncio.sleep(DELAYS['after_ohlc'])
                                return ohlc_data

                        elif response.status == 429:
                            retry_count += 1
                            error_counter['429'] += 1
                            wait_time = DELAYS['after_429_error'] * retry_count
                            logger.warning(
                                f"    ⚠️ Rate limit 429 (попытка {retry_count}/{max_retries}), ожидание {wait_time} сек...")
                            await asyncio.sleep(wait_time)

                        elif response.status == 400:
                            error_counter['400'] += 1
                            error_counter['consecutive_400'] += 1

                            if url_index < len(url_variants) - 1:
                                logger.info(f"    ℹ️ Ошибка 400, пробуем альтернативный endpoint...")
                                await asyncio.sleep(DELAYS['after_400_error'])
                                break
                            else:
                                logger.info(f"    ℹ️ OHLC недоступны для этой монеты")
                                return None

            except Exception as e:
                logger.error(f"    ❌ Ошибка OHLC: {e}")
                return None

    return None


async def process_crypto(session: aiohttp.ClientSession, crypto: Dict, index: int, total: int) -> Dict:
    """Асинхронная обработка одной криптовалюты"""
    age_days = (datetime.now() - datetime.strptime(crypto['added'], '%Y-%m-%d')).days

    if age_days >= MIN_AGE_DAYS and crypto['symbol']:
        logger.info(f"\n🔍 [{index}/{total}] {crypto['name']} ({crypto['symbol']}) - {age_days} дней")

        coin_id = await search_coin_id(session, crypto['name'], crypto['symbol'])
        if coin_id:
            crypto['coin_id'] = coin_id
            ohlc = await fetch_ohlc(session, coin_id, age_days)
            if ohlc:
                crypto['ohlc'] = ohlc
                return crypto
    else:
        if not crypto['symbol']:
            logger.info(f"⏭️  [{index}/{total}] {crypto['name']} - нет символа")
        else:
            logger.info(f"⏭️  [{index}/{total}] {crypto['name']} - слишком новая ({age_days} дней)")

    return crypto


def save_to_database(cryptos: List[Dict]):
    """Сохраняет данные в БД (синхронная функция)"""
    conn = get_db_connection()
    if not conn:
        return

    cursor = conn.cursor()
    new_count = 0
    updated_count = 0
    ohlc_count = 0
    skipped_count = 0

    logger.info("\n💾 Сохранение в БД...")

    try:
        for crypto in cryptos:
            if not crypto['symbol']:
                logger.warning(f"  ⚠️ Пропускаем монету без символа: {crypto['name']}")
                skipped_count += 1
                continue

            # ИЗМЕНЕНИЕ: Проверяем существование только по символу
            cursor.execute("""
                SELECT id, ohlc_table_name, coin_gecko_id, name, added_date
                FROM cryptocurrencies 
                WHERE symbol = %s
            """, (crypto['symbol'],))

            existing = cursor.fetchone()

            if existing:
                crypto_id, ohlc_table, existing_coin_id, existing_name, existing_date = existing

                logger.info(f"  🔄 Монета уже существует: {crypto['name']} ({crypto['symbol']}) от {existing_date}")

                # Обновляем только если есть новая информация
                updates = []
                params = []

                # Обновляем coin_gecko_id если его не было
                if crypto.get('coin_id') and not existing_coin_id:
                    updates.append("coin_gecko_id = %s")
                    params.append(crypto['coin_id'])
                    logger.info(f"    📝 Обновляем coin_gecko_id: {crypto['coin_id']}")

                # Обновляем имя если было Unknown
                if crypto['name'] != "Unknown" and existing_name == "Unknown":
                    updates.append("name = %s")
                    params.append(crypto['name'])
                    logger.info(f"    📝 Обновляем имя: {crypto['name']}")

                # Обновляем цену и другие метрики
                updates.extend([
                    "price = %s",
                    "change_24h = %s",
                    "market_cap = %s",
                    "fdv = %s",
                    "last_updated_at = CURRENT_TIMESTAMP"
                ])
                params.extend([
                    crypto['price'],
                    crypto['change_24h'],
                    crypto['market_cap'],
                    crypto['fdv']
                ])

                if updates:
                    params.append(crypto_id)
                    cursor.execute(f"""
                        UPDATE cryptocurrencies 
                        SET {', '.join(updates)}
                        WHERE id = %s
                    """, params)
                    updated_count += 1

                # Обрабатываем OHLC данные
                if 'ohlc' in crypto and crypto['ohlc']:
                    if not ohlc_table and crypto.get('coin_id'):
                        # Если таблицы нет, но есть coin_id - создадим при следующем запуске updater.py
                        logger.info(f"    ℹ️ OHLC таблица будет создана updater.py")
                    elif ohlc_table:
                        # Сохраняем OHLC если таблица есть
                        saved_candles = 0
                        for candle in crypto['ohlc']:
                            try:
                                cursor.execute(f"""
                                    INSERT INTO {ohlc_table} 
                                    (timestamp, datetime, date, time, open, high, low, close)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                                    ON CONFLICT (timestamp) DO NOTHING
                                """, (
                                    candle['timestamp'], candle['datetime'],
                                    candle['date'], candle['time'],
                                    candle['open'], candle['high'],
                                    candle['low'], candle['close']
                                ))
                                if cursor.rowcount > 0:
                                    saved_candles += 1
                            except Exception as e:
                                logger.debug(f"    ⚠️ Ошибка вставки OHLC: {e}")

                        if saved_candles > 0:
                            ohlc_count += saved_candles
                            logger.info(f"    📊 Сохранено {saved_candles} новых OHLC свечей")

            else:
                # Новая монета - вставляем
                cursor.execute("""
                    INSERT INTO cryptocurrencies 
                    (name, symbol, chain, price, change_24h, market_cap, 
                     fdv, added_date, added_raw, coin_gecko_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    crypto['name'], crypto['symbol'], crypto['chain'],
                    crypto['price'], crypto['change_24h'], crypto['market_cap'],
                    crypto['fdv'], crypto['added'], crypto['added_raw'],
                    crypto.get('coin_id')
                ))
                crypto_id = cursor.fetchone()[0]
                new_count += 1
                logger.info(f"  ✅ Добавлена новая монета: {crypto['name']} ({crypto['symbol']})")

            conn.commit()

    except Exception as e:
        logger.error(f"❌ Ошибка БД: {e}")
        conn.rollback()
    finally:
        cursor.close()
        put_db_connection(conn)

    logger.info(f"\n📊 Итоги сохранения:")
    logger.info(f"  ✅ Новых монет: {new_count}")
    logger.info(f"  🔄 Обновлено существующих: {updated_count}")
    logger.info(f"  📈 OHLC записей: {ohlc_count}")
    logger.info(f"  ⏭️  Пропущено: {skipped_count}")


async def main():
    """Главная асинхронная функция"""
    print("=" * 60)
    print("🚀 АСИНХРОННЫЙ ПАРСЕР КРИПТОВАЛЮТ")
    print(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Минимальный возраст для OHLC: {MIN_AGE_DAYS} день")
    print(f"Макс. одновременных запросов: {MAX_CONCURRENT_REQUESTS}")
    print("=" * 60)

    # Инициализация пула БД
    if not init_db_pool():
        sys.exit(1)

    # Создаем асинхронную сессию
    async with aiohttp.ClientSession() as session:
        # Загружаем страницу
        html = await fetch_page(session)
        if not html:
            logger.error("❌ Не удалось загрузить страницу")
            close_db_pool()
            return

        # Парсим данные
        cryptos = parse_html(html)
        logger.info(f"\n✅ Найдено {len(cryptos)} монет")

        # Статистика распознавания
        with_symbol = sum(1 for c in cryptos if c['symbol'])
        logger.info(f"📊 Монет с символами: {with_symbol}/{len(cryptos)}")

        # Обрабатываем монеты асинхронно, но с ограничением
        logger.info(f"\n📊 Получение OHLC данных...")

        # Разбиваем на батчи для контроля нагрузки
        batch_size = 5
        for i in range(0, len(cryptos), batch_size):
            batch = cryptos[i:i + batch_size]

            # Обрабатываем батч
            tasks = []
            for j, crypto in enumerate(batch):
                task = process_crypto(session, crypto, i + j + 1, len(cryptos))
                tasks.append(task)

            # Ждем завершения батча
            results = await asyncio.gather(*tasks)

            # Обновляем данные
            for j, result in enumerate(results):
                cryptos[i + j] = result

            # Пауза между батчами
            if i + batch_size < len(cryptos):
                await asyncio.sleep(DELAYS['between_coins'])

        # Статистика
        successful_ohlc = sum(1 for c in cryptos if 'ohlc' in c and c['ohlc'])
        failed_ohlc = sum(1 for c in cryptos if c['symbol'] and
                          (datetime.now() - datetime.strptime(c['added'], '%Y-%m-%d')).days >= MIN_AGE_DAYS and
                          ('ohlc' not in c or not c['ohlc']))

        logger.info(f"\n📊 Статистика обработки:")
        logger.info(f"  Успешно получено OHLC: {successful_ohlc}")
        logger.info(f"  Не удалось получить OHLC: {failed_ohlc}")
        logger.info(f"  Ошибок 400: {error_counter['400']}")
        logger.info(f"  Ошибок 429: {error_counter['429']}")

        # Сохраняем в БД (синхронно)
        save_to_database(cryptos)

    # Закрываем пул БД
    close_db_pool()

    print("\n✅ Парсер завершил работу")
    print("=" * 60)


if __name__ == "__main__":
    # Запускаем асинхронный код
    asyncio.run(main())
#!/usr/bin/env python3
"""
CoinGecko Scraper with Cloudflare Bypass
Использует cloudscraper для обхода защиты
Пропускает криптовалюты с уже существующими социальными ссылками
"""

import cloudscraper
import psycopg2
import time
import os
from datetime import datetime
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import re
import sys

load_dotenv()


class CoinGeckoScraperUpdated:
    def __init__(self):
        self.db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', '5432'),
            'database': os.getenv('DB_NAME', 'crypto_db'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', '')
        }

        # Используем cloudscraper вместо requests
        self.scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            }
        )

        # Дополнительные заголовки
        self.scraper.headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,ru;q=0.8',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
        })

    def connect_db(self):
        """Подключение к БД"""
        try:
            return psycopg2.connect(**self.db_config)
        except Exception as e:
            print(f"❌ Database connection error: {e}")
            return None

    def check_existing_social_links(self, crypto_id):
        """Проверка наличия социальных ссылок у криптовалюты"""
        conn = self.connect_db()
        if not conn:
            return False

        try:
            cur = conn.cursor()

            # Проверяем наличие любых социальных ссылок
            cur.execute("""
                SELECT 
                    COALESCE(array_length(telegram_channels, 1), 0) +
                    COALESCE(array_length(twitter_accounts, 1), 0) +
                    COALESCE(array_length(discord_links, 1), 0) +
                    COALESCE(array_length(reddit_communities, 1), 0) +
                    COALESCE(array_length(github_links, 1), 0) +
                    COALESCE(array_length(official_websites, 1), 0) +
                    COALESCE(array_length(instagram_accounts, 1), 0) as total_links,
                    social_links_updated
                FROM cryptocurrencies
                WHERE id = %s
            """, (crypto_id,))

            result = cur.fetchone()

            if result and result[0] > 0:
                # Есть социальные ссылки
                updated_date = result[1]
                if updated_date:
                    days_ago = (datetime.now() - updated_date).days
                    print(f"   ✅ Already has {result[0]} social links (updated {days_ago} days ago)")
                else:
                    print(f"   ✅ Already has {result[0]} social links")
                return True

            return False

        except Exception as e:
            print(f"❌ Error checking existing links: {e}")
            return False
        finally:
            conn.close()

    def get_crypto_list(self, limit=None, skip_existing=True):
        """Получение списка криптовалют с coin_gecko_id"""
        conn = self.connect_db()
        if not conn:
            return []

        try:
            cur = conn.cursor()

            if skip_existing:
                # Запрос только тех, у кого нет социальных ссылок
                query = """
                    SELECT id, name, symbol, coin_gecko_id
                    FROM cryptocurrencies
                    WHERE coin_gecko_id IS NOT NULL
                    AND (
                        telegram_channels IS NULL OR 
                        array_length(telegram_channels, 1) IS NULL OR
                        array_length(telegram_channels, 1) = 0
                    )
                    AND (
                        twitter_accounts IS NULL OR 
                        array_length(twitter_accounts, 1) IS NULL OR
                        array_length(twitter_accounts, 1) = 0
                    )
                    AND (
                        official_websites IS NULL OR 
                        array_length(official_websites, 1) IS NULL OR
                        array_length(official_websites, 1) = 0
                    )
                    ORDER BY market_cap DESC NULLS LAST
                """
            else:
                # Запрос всех с coin_gecko_id
                query = """
                    SELECT id, name, symbol, coin_gecko_id
                    FROM cryptocurrencies
                    WHERE coin_gecko_id IS NOT NULL
                    ORDER BY market_cap DESC NULLS LAST
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
                    'coin_gecko_id': row[3]
                })

            return cryptos

        except Exception as e:
            print(f"❌ Error fetching cryptocurrencies: {e}")
            return []
        finally:
            conn.close()

    def extract_social_links(self, coin_gecko_id):
        """Извлечение социальных ссылок с CoinGecko"""
        social_links = {
            'telegram': [],
            'twitter': [],
            'discord': [],
            'reddit': [],
            'website': [],
            'github': [],
            'instagram': []
        }

        try:
            # Пробуем разные варианты URL
            base_urls = [
                f"https://www.coingecko.com/ru/Криптовалюты/{coin_gecko_id}",
                f"https://www.coingecko.com/en/coins/{coin_gecko_id}",
            ]

            response = None
            successful_url = None

            for base_url in base_urls:
                print(f"🔍 Trying: {base_url}")

                try:
                    response = self.scraper.get(base_url, timeout=20)

                    if response.status_code == 200:
                        successful_url = base_url
                        break
                    elif response.status_code == 404:
                        print(f"   ❌ Page not found (404)")
                    else:
                        print(f"   ⚠️ Status: {response.status_code}")

                except Exception as e:
                    print(f"   ❌ Error: {str(e)[:100]}")
                    continue

                time.sleep(2)

            if not response or response.status_code != 200:
                print(f"❌ Failed to fetch page for {coin_gecko_id}")
                return social_links

            print(f"✅ Successfully fetched: {successful_url}")
            soup = BeautifulSoup(response.text, 'html.parser')

            # ГЛАВНЫЙ МЕТОД: Ищем секцию "Сообщество"
            # Поиск по тексту "Сообщество" или "Community"
            community_sections = []

            # Ищем все div с текстом "Сообщество" или "Community"
            for div in soup.find_all('div', class_=lambda x: x and 'tw-text-gray-500' in str(x)):
                text = div.get_text(strip=True)
                if text in ['Сообщество', 'Community', 'Социальные сети', 'Social']:
                    # Нашли заголовок секции, теперь ищем контейнер с ссылками
                    parent = div.find_parent('div')
                    if parent:
                        # Ищем следующий элемент после заголовка
                        next_sibling = parent.find_next_sibling()
                        if next_sibling:
                            community_sections.append(next_sibling)

                        # Также проверяем родительский контейнер
                        grand_parent = parent.find_parent('div')
                        if grand_parent:
                            community_sections.append(grand_parent)

            # Обрабатываем найденные секции
            for section in community_sections:
                # Ищем все ссылки в секции
                links = section.find_all('a', href=True)

                for link in links:
                    href = link.get('href', '')
                    if not href:
                        continue

                    # Извлекаем текст кнопки
                    button_text = link.get_text(strip=True)

                    # Проверяем иконки
                    icon = link.find('i', class_=True)
                    icon_classes = ' '.join(icon.get('class', [])) if icon else ''

                    # Telegram
                    if 't.me/' in href or 'telegram' in href.lower() or 'telegram' in button_text.lower() or 'fa-telegram' in icon_classes:
                        channel = self._extract_telegram_channel(href)
                        if channel:
                            social_links['telegram'].append(channel)
                            print(f"   📱 Found Telegram: @{channel}")

                    # Twitter/X
                    elif 'twitter.com/' in href or 'x.com/' in href or 'twitter' in button_text.lower() or 'fa-twitter' in icon_classes or 'fa-x-twitter' in icon_classes:
                        username = self._extract_twitter_username(href)
                        if username:
                            social_links['twitter'].append(username)
                            print(f"   🐦 Found Twitter: @{username}")

                    # Discord
                    elif 'discord' in href.lower() or 'discord' in button_text.lower() or 'fa-discord' in icon_classes:
                        social_links['discord'].append(href)
                        print(f"   💬 Found Discord: {href}")

                    # Reddit
                    elif 'reddit.com' in href or 'reddit' in button_text.lower() or 'fa-reddit' in icon_classes:
                        if 'reddit.com/r/' in href:
                            subreddit = href.split('reddit.com/r/')[-1].split('/')[0].split('?')[0]
                            if subreddit:
                                social_links['reddit'].append(subreddit)
                                print(f"   📡 Found Reddit: r/{subreddit}")

                    # GitHub
                    elif 'github.com' in href or 'github' in button_text.lower() or 'fa-github' in icon_classes:
                        social_links['github'].append(href)
                        print(f"   💻 Found GitHub: {href}")

                    # Instagram
                    elif 'instagram.com' in href or 'instagram' in button_text.lower() or 'fa-instagram' in icon_classes:
                        username = self._extract_instagram_username(href)
                        if username:
                            if 'instagram' not in social_links:
                                social_links['instagram'] = []
                            social_links['instagram'].append(username)
                            print(f"   📸 Found Instagram: @{username}")

                    # Website (исключаем социальные сети и pump.fun)
                    elif href.startswith('http') and not any(social in href.lower() for social in
                                                             ['t.me', 'telegram', 'twitter', 'x.com', 'discord',
                                                              'reddit', 'github', 'instagram',
                                                              'coingecko', 'facebook', 'youtube', 'linkedin',
                                                              'medium', 'pump.fun', 'slack.com']):
                        # Проверяем, является ли это блокчейн-обозревателем
                        if any(explorer in href.lower() for explorer in ['etherscan.io', 'ethplorer.io', 'bscscan.com',
                                                                         'polygonscan.com', 'solscan.io', 'explorer',
                                                                         'scan']):
                            social_links['website'].append(href)
                            print(f"   🌐 Обозреватели: {href}")
                        else:
                            social_links['website'].append(href)
                            print(f"   🌐 Веб-сайт: {href}")

            # Дополнительный поиск: ищем контейнеры с классами tw-flex
            containers_with_links = soup.find_all('div', class_=re.compile(r'tw-flex.*tw-items-center.*tw-gap-1'))

            for container in containers_with_links:
                links = container.find_all('a', href=True)

                for link in links:
                    href = link.get('href', '')

                    # Используем ту же логику категоризации
                    self._categorize_social_link(href, link, social_links)

            # Удаляем дубликаты
            for key in social_links:
                social_links[key] = list(set(social_links[key]))

            # Итоговая информация
            total_found = sum(len(links) for links in social_links.values())
            if total_found > 0:
                print(f"✅ Total social links found: {total_found}")
            else:
                print("⚠️ No social links found")

            return social_links

        except Exception as e:
            print(f"❌ Error parsing {coin_gecko_id}: {e}")
            return social_links

    def _categorize_social_link(self, href, link_element, social_links):
        """Категоризация социальной ссылки с учетом контекста"""
        if not href:
            return

        # Получаем текст и иконки
        link_text = link_element.get_text(strip=True).lower()
        icon = link_element.find('i', class_=True)
        icon_classes = ' '.join(icon.get('class', [])).lower() if icon else ''

        # Telegram
        if any(ind in href.lower() + link_text + icon_classes for ind in ['t.me/', 'telegram']):
            channel = self._extract_telegram_channel(href)
            if channel and channel not in social_links['telegram']:
                social_links['telegram'].append(channel)

        # Twitter/X
        elif any(ind in href.lower() + link_text + icon_classes for ind in
                 ['twitter.com/', 'x.com/', 'twitter', 'fa-x-twitter']):
            username = self._extract_twitter_username(href)
            if username and username not in social_links['twitter']:
                social_links['twitter'].append(username)

        # Discord
        elif any(ind in href.lower() + link_text + icon_classes for ind in ['discord.gg/', 'discord.com/', 'discord']):
            if href not in social_links['discord']:
                social_links['discord'].append(href)

        # Reddit
        elif any(ind in href.lower() + link_text + icon_classes for ind in ['reddit.com/', 'reddit']):
            if 'reddit.com/r/' in href:
                subreddit = href.split('reddit.com/r/')[-1].split('/')[0].split('?')[0]
                if subreddit and subreddit not in social_links['reddit']:
                    social_links['reddit'].append(subreddit)

        # GitHub
        elif any(ind in href.lower() + link_text + icon_classes for ind in ['github.com/', 'github']):
            if href not in social_links['github']:
                social_links['github'].append(href)

        # Instagram
        elif any(ind in href.lower() + link_text + icon_classes for ind in ['instagram.com/', 'instagram']):
            username = self._extract_instagram_username(href)
            if username and 'instagram' in social_links and username not in social_links['instagram']:
                social_links['instagram'].append(username)

        # Website
        elif href.startswith('http') and not any(social in href.lower() for social in
                                                 ['t.me', 'telegram', 'twitter', 'x.com', 'discord', 'reddit', 'github',
                                                  'coingecko', 'facebook', 'youtube', 'linkedin', 'medium',
                                                  'instagram', 'pump.fun', 'slack.com']):
            if href not in social_links['website']:
                social_links['website'].append(href)

    def _extract_telegram_channel(self, url):
        """Извлечение имени канала из Telegram URL"""
        try:
            if not url or 'joinchat' in url or 'addstickers' in url:
                return None

            # Очистка URL
            url = url.strip()

            # Паттерн для извлечения
            patterns = [
                r't\.me/([a-zA-Z0-9_]+)',
                r'telegram\.me/([a-zA-Z0-9_]+)',
            ]

            for pattern in patterns:
                match = re.search(pattern, url)
                if match:
                    channel = match.group(1)
                    # Проверка валидности
                    if channel and len(channel) > 3 and channel not in ['share', 'joinchat']:
                        return channel

        except Exception as e:
            print(f"Error extracting Telegram channel: {e}")
        return None

    def _extract_twitter_username(self, url):
        """Извлечение username из Twitter URL"""
        try:
            if not url:
                return None

            # Паттерны для Twitter
            patterns = [
                r'twitter\.com/([a-zA-Z0-9_]+)',
                r'x\.com/([a-zA-Z0-9_]+)',
            ]

            for pattern in patterns:
                match = re.search(pattern, url)
                if match:
                    username = match.group(1)
                    # Исключаем служебные страницы
                    if username not in ['intent', 'share', 'search', 'login', 'signup', 'home']:
                        return username

        except Exception as e:
            print(f"Error extracting Twitter username: {e}")
        return None

    def _extract_instagram_username(self, url):
        """Извлечение username из Instagram URL"""
        try:
            if not url:
                return None

            # Паттерн для Instagram
            pattern = r'instagram\.com/([a-zA-Z0-9_.]+)'

            match = re.search(pattern, url)
            if match:
                username = match.group(1)
                # Исключаем служебные страницы
                if username not in ['p', 'reel', 'explore', 'accounts', 'login', 'direct']:
                    return username

        except Exception as e:
            print(f"Error extracting Instagram username: {e}")
        return None

    def update_crypto_social_links(self, crypto_id, social_links):
        """Обновление социальных ссылок в БД"""
        conn = self.connect_db()
        if not conn:
            return False

        try:
            cur = conn.cursor()

            # Добавляем колонки если их нет
            cur.execute("""
                ALTER TABLE cryptocurrencies 
                ADD COLUMN IF NOT EXISTS telegram_channels TEXT[],
                ADD COLUMN IF NOT EXISTS twitter_accounts TEXT[],
                ADD COLUMN IF NOT EXISTS discord_links TEXT[],
                ADD COLUMN IF NOT EXISTS reddit_communities TEXT[],
                ADD COLUMN IF NOT EXISTS github_links TEXT[],
                ADD COLUMN IF NOT EXISTS official_websites TEXT[],
                ADD COLUMN IF NOT EXISTS instagram_accounts TEXT[],
                ADD COLUMN IF NOT EXISTS social_links_updated TIMESTAMP
            """)

            # Обновляем данные
            cur.execute("""
                UPDATE cryptocurrencies 
                SET telegram_channels = %s,
                    twitter_accounts = %s,
                    discord_links = %s,
                    reddit_communities = %s,
                    github_links = %s,
                    official_websites = %s,
                    instagram_accounts = %s,
                    social_links_updated = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (
                social_links['telegram'],
                social_links['twitter'],
                social_links['discord'],
                social_links['reddit'],
                social_links['github'],
                social_links['website'],
                social_links.get('instagram', []),
                crypto_id
            ))

            conn.commit()
            return True

        except Exception as e:
            print(f"❌ Error updating social links: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()

    def run(self, limit=None, skip_existing=True, force_update=False):
        """
        Запуск парсинга

        Args:
            limit: Ограничение количества криптовалют
            skip_existing: Пропускать криптовалюты с существующими ссылками
            force_update: Принудительно обновить все (игнорировать skip_existing)
        """
        print("\n" + "=" * 60)
        print("🚀 COINGECKO SCRAPER WITH CLOUDFLARE BYPASS")
        print("=" * 60)
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        if force_update:
            print("⚠️  FORCE UPDATE MODE: Will update all cryptocurrencies")
            skip_existing = False
        elif skip_existing:
            print("✅ SKIP MODE: Will skip cryptocurrencies with existing social links")

        cryptos = self.get_crypto_list(limit, skip_existing)
        total = len(cryptos)

        if total == 0:
            if skip_existing:
                print("✅ No cryptocurrencies without social links found")
                print("   All cryptocurrencies already have social links!")
            else:
                print("❌ No cryptocurrencies found")
            return

        print(f"📊 Found {total} cryptocurrencies to process")
        if limit:
            print(f"⚠️  Limited to first {limit} cryptos")

        print("\nStarting scraping...\n")

        success_count = 0
        telegram_count = 0
        error_count = 0
        skipped_count = 0
        start_time = time.time()

        for i, crypto in enumerate(cryptos, 1):
            print(f"\n[{i}/{total}] {crypto['name']} ({crypto['symbol']})")
            print(f"CoinGecko ID: {crypto['coin_gecko_id']}")

            # Дополнительная проверка на случай, если skip_existing=False
            if not force_update and self.check_existing_social_links(crypto['id']):
                skipped_count += 1
                continue

            try:
                # Извлекаем социальные ссылки
                social_links = self.extract_social_links(crypto['coin_gecko_id'])

                # Обновляем в БД если что-то нашли
                if any(social_links.values()):
                    if self.update_crypto_social_links(crypto['id'], social_links):
                        success_count += 1

                        if social_links['telegram']:
                            telegram_count += 1

                        # Выводим результаты
                        for platform, links in social_links.items():
                            if links:
                                print(f"   {platform}: {', '.join(links[:3])}")  # Первые 3 ссылки
                else:
                    print("   ⚠️ No social links found")

            except Exception as e:
                print(f"   ❌ Error: {e}")
                error_count += 1

            # Прогресс
            if i % 5 == 0:
                elapsed = time.time() - start_time
                avg_time = elapsed / i
                remaining = avg_time * (total - i)

                print(f"\n📊 Progress: {i}/{total} ({i / total * 100:.1f}%)")
                print(f"⏱️  Time: {int(elapsed // 60)}m {int(elapsed % 60)}s | "
                      f"Remaining: ~{int(remaining // 60)}m")
                print(f"✅ Success: {success_count} | 📱 Telegram: {telegram_count} | "
                      f"⏭️  Skipped: {skipped_count} | ❌ Errors: {error_count}")

            # Пауза между запросами
            delay = 5 + (i % 10) * 0.5  # Увеличиваем паузу каждые 10 запросов
            time.sleep(delay)

        # Финальная статистика
        total_time = time.time() - start_time

        print("\n" + "=" * 60)
        print("📊 SCRAPING COMPLETED")
        print("=" * 60)
        print(f"Total time: {int(total_time // 60)}m {int(total_time % 60)}s")
        print(f"Processed: {total}")
        print(f"Successful: {success_count}")
        print(f"With Telegram: {telegram_count}")
        print(f"Skipped: {skipped_count}")
        print(f"Errors: {error_count}")
        if total > 0:
            print(f"Average time per crypto: {total_time / total:.2f}s")
        print("=" * 60)


def main():
    """Автоматический запуск"""
    # Проверка зависимостей
    try:
        import cloudscraper
    except ImportError:
        print("❌ cloudscraper not installed!")
        print("Please run: pip install cloudscraper")
        return

    # Обработка аргументов командной строки
    limit = None
    force_update = False

    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            if arg == '--force':
                force_update = True
                print("⚠️  Force update mode enabled")
            elif arg == '--help':
                print("\nUsage: python parser_coingecko_social.py [limit] [--force]")
                print("\nOptions:")
                print("  limit    Number of cryptocurrencies to process")
                print("  --force  Force update all cryptocurrencies (ignore existing)")
                print("\nExamples:")
                print("  python parser_coingecko_social.py")
                print("  python parser_coingecko_social.py 10")
                print("  python parser_coingecko_social.py 10 --force")
                return
            else:
                try:
                    limit = int(arg)
                    print(f"⚠️  Limited mode: {limit} cryptos")
                except ValueError:
                    print(f"Invalid argument: {arg}")

    # Запуск скрапера
    scraper = CoinGeckoScraperUpdated()
    scraper.run(limit=limit, force_update=force_update)


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
import os
import psycopg2
from selenium import webdriver
from selenium.webdriver.common.by import By
from datetime import datetime

# Загрузка переменных из .env файла
try:
    from dotenv import load_dotenv

    load_dotenv()
    print("✅ Переменные из .env загружены")
except ImportError:
    print("⚠️ python-dotenv не установлен, используются системные переменные")

# Настройки БД из .env файла
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': os.environ.get('DB_PORT', '5432'),
    'database': os.environ.get('DB_NAME', 'crypto_db'),
    'user': os.environ.get('DB_USER', 'crypto_user'),
    'password': os.environ.get('DB_PASSWORD', 'crypto_password')
}


def setup_driver():
    """Настройка браузера"""
    print("🔧 Запуск браузера...")
    options = webdriver.ChromeOptions()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    options.add_argument('--window-size=1920,1080')

    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(8)
    print("   ✅ Браузер готов")
    return driver


def get_projects_from_db(limit=10):
    """Получаем проекты из БД"""
    try:
        connection = psycopg2.connect(**DB_CONFIG)
        cursor = connection.cursor()

        query = """
        SELECT id, project_name, project_symbol, project_url 
        FROM cryptorank_upcoming 
        WHERE project_url IS NOT NULL 
        AND project_url != ''
        ORDER BY id 
        LIMIT %s
        """

        cursor.execute(query, (limit,))
        projects = cursor.fetchall()
        connection.close()

        print(f"📊 Получено проектов из БД: {len(projects)}")
        return [{'id': row[0], 'name': row[1], 'symbol': row[2], 'url': row[3]} for row in projects]

    except Exception as e:
        print(f"❌ Ошибка БД: {e}")
        return []


def find_platforms_on_project_page(driver, project):
    """Находим платформы на странице конкретного проекта с бесконечными попытками"""
    platforms_found = []
    attempt = 0
    max_wait_time = 300  # Максимальная задержка 5 минут

    while True:
        attempt += 1
        try:
            print(f"\n🔍 Сканирование: {project['name']} ({project['symbol']}) - попытка {attempt}")
            print(f"🌐 URL: {project['url']}")

            # Заходим на страницу проекта с увеличенным таймаутом
            driver.set_page_load_timeout(60)  # 60 секунд на загрузку страницы
            driver.get(project['url'])
            time.sleep(5)

            # Прокручиваем страницу для загрузки всех элементов
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # ============ ПОИСК "TRENDING TOKEN SALES" ============
            trending_elements = driver.find_elements(By.XPATH,
                                                     "//*[contains(text(), 'Trending Token Sales') and not(self::script) and not(ancestor::script)]")

            visible_trending_elements = []
            for element in trending_elements:
                try:
                    if element.is_displayed() and element.size['width'] > 0 and element.size['height'] > 0:
                        visible_trending_elements.append(element)
                except:
                    continue

            trending_y_position = None
            if visible_trending_elements:
                positions = [elem.location['y'] for elem in visible_trending_elements if elem.location['y'] > 100]
                if positions:
                    trending_y_position = max(positions)
                    print(f"   🎯 'Trending Token Sales' найден на Y={trending_y_position}")

            # ============ ПОИСК FUNDRAISING ССЫЛОК ============
            fundraising_links = driver.find_elements(By.XPATH, "//a[contains(@href, '/fundraising-platforms/')]")
            print(f"   💰 Найдено fundraising ссылок: {len(fundraising_links)}")

            for link in fundraising_links:
                try:
                    position = link.location
                    text = link.text.strip()
                    href = link.get_attribute('href')
                    title = link.get_attribute('title') or ''

                    # Извлекаем название платформы из URL
                    platform_name = ""
                    if '/fundraising-platforms/' in href:
                        platform_name = href.split('/fundraising-platforms/')[-1]
                        platform_name = platform_name.replace('-', ' ').title()

                    # Определяем позицию относительно Trending Token Sales
                    position_status = "unknown"
                    if trending_y_position:
                        if position['y'] < trending_y_position:
                            position_status = "above"
                        else:
                            position_status = "below"

                    platform_info = {
                        'project_id': project['id'],
                        'project_name': project['name'],
                        'project_url': project['url'],
                        'platform_name': platform_name,
                        'platform_text': text,
                        'platform_title': title,
                        'platform_href': href,
                        'position_x': position['x'],
                        'position_y': position['y'],
                        'position_status': position_status,
                        'trending_position': trending_y_position
                    }

                    platforms_found.append(platform_info)

                    status_emoji = "✅" if position_status == "above" else "🚫" if position_status == "below" else "❓"
                    print(f"      {status_emoji} {platform_name} | {text} | Y={position['y']}")

                except Exception as e:
                    print(f"      ❌ Ошибка обработки ссылки: {e}")

            # Если успешно получили данные, выходим из цикла
            print(f"   ✅ Успешно обработан проект {project['name']}")
            return platforms_found

        except Exception as e:
            print(f"   ❌ Ошибка попытки {attempt}: {e}")

            # Вычисляем время ожидания (экспоненциальный рост с максимумом)
            wait_time = min(attempt * 10, max_wait_time)  # 10, 20, 30, ..., до 300 секунд
            print(f"   ⏳ Ожидание {wait_time} секунд перед попыткой {attempt + 1}...")
            time.sleep(wait_time)

            # Перезапускаем браузер при серьезных ошибках
            if any(keyword in str(e).lower() for keyword in ['timeout', 'connection', 'refused', 'reset']):
                print(f"   🔄 Перезапуск браузера из-за проблем с соединением...")
                try:
                    driver.quit()
                    time.sleep(5)
                    driver = setup_driver()
                except Exception as restart_error:
                    print(f"   ⚠️ Ошибка перезапуска браузера: {restart_error}")
                    time.sleep(10)  # Дополнительная пауза при проблемах с браузером
                    try:
                        driver = setup_driver()
                    except:
                        print(f"   💥 Не удалось перезапустить браузер, пауза 30 секунд...")
                        time.sleep(30)
                        driver = setup_driver()

            # Логируем прогресс каждые 10 попыток
            if attempt % 10 == 0:
                print(f"   📊 Попытка {attempt}: продолжаем попытки с задержкой {wait_time}с")


def remove_duplicates(platforms):
    """Удаляем дубликаты платформ"""
    print(f"\n🔧 УДАЛЕНИЕ ДУБЛИКАТОВ:")
    print("-" * 30)
    print(f"📊 Платформ до удаления дубликатов: {len(platforms)}")

    # Используем set для отслеживания уникальных комбинаций
    seen = set()
    unique_platforms = []

    for platform in platforms:
        # Создаем уникальный ключ на основе проекта и платформы
        key = (
            platform['project_id'],
            platform['platform_name'].lower().strip(),
            platform['platform_href']
        )

        if key not in seen:
            seen.add(key)
            unique_platforms.append(platform)

    duplicates_removed = len(platforms) - len(unique_platforms)
    print(f"🗑️ Удалено дубликатов: {duplicates_removed}")
    print(f"✅ Уникальных платформ: {len(unique_platforms)}")

    return unique_platforms


def update_launchpads_in_db(platforms):
    """Обновляем поле launchpad в таблице cryptorank_upcoming"""
    print(f"\n💾 ОБНОВЛЕНИЕ LAUNCHPAD В БД (ТОЛЬКО ВАЛИДНЫЕ ПЛАТФОРМЫ):")
    print("-" * 60)

    try:
        connection = psycopg2.connect(**DB_CONFIG)
        cursor = connection.cursor()

        # Группируем ТОЛЬКО валидные платформы (выше Trending Token Sales) по project_id
        platforms_by_project = {}
        for platform in platforms:
            # Сохраняем только платформы со статусом "above" (✅)
            if platform['position_status'] != 'above':
                continue

            project_id = platform['project_id']
            platform_name = platform['platform_name']

            if project_id not in platforms_by_project:
                platforms_by_project[project_id] = set()

            if platform_name and platform_name.strip():
                platforms_by_project[project_id].add(platform_name.strip())

        updated_count = 0

        for project_id, platform_names in platforms_by_project.items():
            if not platform_names:
                continue

            # Получаем текущее значение launchpad для проекта
            cursor.execute("SELECT launchpad FROM cryptorank_upcoming WHERE id = %s", (project_id,))
            result = cursor.fetchone()

            if result:
                current_launchpad = result[0]

                # Парсим существующие платформы из JSON
                existing_platforms = set()
                if current_launchpad:
                    try:
                        if isinstance(current_launchpad, str):
                            # Если это строка JSON
                            existing_data = json.loads(current_launchpad)
                        else:
                            # Если это уже объект Python
                            existing_data = current_launchpad

                        if isinstance(existing_data, list):
                            existing_platforms = set(existing_data)
                        elif isinstance(existing_data, str):
                            # Если в JSON лежит строка через запятую
                            existing_platforms = set(p.strip() for p in existing_data.split(',') if p.strip())
                    except (json.JSONDecodeError, TypeError):
                        # Если не JSON, пытаемся парсить как строку
                        if isinstance(current_launchpad, str):
                            existing_platforms = set(p.strip() for p in current_launchpad.split(',') if p.strip())

                # Объединяем с новыми ВАЛИДНЫМИ платформами (только уникальные)
                all_platforms = existing_platforms.union(platform_names)

                # Создаем JSON массив
                launchpad_json = json.dumps(sorted(list(all_platforms)), ensure_ascii=False)

                # Сравниваем с текущим значением
                current_platforms_set = existing_platforms
                new_platforms_set = all_platforms

                # Обновляем только если есть изменения
                if current_platforms_set != new_platforms_set:
                    cursor.execute(
                        "UPDATE cryptorank_upcoming SET launchpad = %s WHERE id = %s",
                        (launchpad_json, project_id)
                    )
                    updated_count += 1

                    # Получаем название проекта для отчета
                    cursor.execute("SELECT project_name FROM cryptorank_upcoming WHERE id = %s", (project_id,))
                    project_result = cursor.fetchone()
                    project_name = project_result[0] if project_result else f"ID_{project_id}"

                    platforms_str = ', '.join(sorted(list(all_platforms)))
                    print(f"   ✅ {project_name}: {platforms_str}")

        connection.commit()
        connection.close()

        print(f"\n📊 Обновлено проектов: {updated_count}")
        print(f"💾 Всего обработано проектов: {len(platforms_by_project)}")
        print(f"🎯 Сохранены только валидные платформы (выше 'Trending Token Sales')")

    except Exception as e:
        print(f"❌ Ошибка обновления БД: {e}")
        import traceback
        print(traceback.format_exc())


def save_platforms_to_json(platforms):
    """Сохраняем найденные платформы в JSON файл"""
    try:
        # Удаляем дубликаты перед сохранением
        unique_platforms = remove_duplicates(platforms)

        # Подготавливаем данные для JSON
        json_data = {
            "scan_info": {
                "timestamp": datetime.now().isoformat(),
                "total_platforms_found": len(platforms),
                "unique_platforms": len(unique_platforms),
                "duplicates_removed": len(platforms) - len(unique_platforms),
                "total_projects": len(set(p['project_name'] for p in unique_platforms))
            },
            "platforms": unique_platforms
        }

        # Сохраняем в JSON файл
        filename = f"found_platforms_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)

        print(f"✅ Сохранено {len(unique_platforms)} уникальных платформ в файл: {filename}")

        # Обновляем БД
        update_launchpads_in_db(unique_platforms)

        return filename

    except Exception as e:
        print(f"❌ Ошибка сохранения JSON: {e}")
        return None


def analyze_platforms(platforms):
    """Анализируем найденные платформы"""
    print(f"\n📊 АНАЛИЗ НАЙДЕННЫХ ПЛАТФОРМ:")
    print("=" * 50)

    if not platforms:
        print("❌ Платформы не найдены")
        return

    # Удаляем дубликаты для анализа
    unique_platforms = remove_duplicates(platforms)

    # Группируем по проектам
    by_projects = {}
    for platform in unique_platforms:
        project_name = platform['project_name']
        if project_name not in by_projects:
            by_projects[project_name] = []
        by_projects[project_name].append(platform)

    print(f"📈 Всего проектов проверено: {len(by_projects)}")
    print(f"💰 Всего уникальных платформ: {len(unique_platforms)}")

    # Уникальные платформы
    unique_platform_names = set()
    above_count = 0
    below_count = 0

    for platform in unique_platforms:
        unique_platform_names.add(platform['platform_name'])
        if platform['position_status'] == 'above':
            above_count += 1
        elif platform['position_status'] == 'below':
            below_count += 1

    print(f"🎯 Уникальных названий платформ: {len(unique_platform_names)}")
    print(f"✅ Платформ выше 'Trending Token Sales': {above_count}")
    print(f"🚫 Платформ ниже 'Trending Token Sales': {below_count}")

    # Топ платформ
    platform_counts = {}
    for platform in unique_platforms:
        name = platform['platform_name']
        platform_counts[name] = platform_counts.get(name, 0) + 1

    print(f"\n🏆 ТОП-10 САМЫХ ЧАСТЫХ ПЛАТФОРМ:")
    for i, (platform, count) in enumerate(sorted(platform_counts.items(), key=lambda x: x[1], reverse=True)[:10], 1):
        print(f"   {i:2d}. {platform:<20} - {count} проектов")

    # Детали по проектам
    print(f"\n📋 ДЕТАЛИ ПО ПРОЕКТАМ:")
    for project_name, project_platforms in by_projects.items():
        print(f"\n   🎯 {project_name}:")
        for platform in project_platforms:
            status = "✅" if platform['position_status'] == 'above' else "🚫" if platform['position_status'] == 'below' else "❓"
            print(f"      {status} {platform['platform_name']}")

    return unique_platforms


def main():
    """Главная функция"""
    driver = setup_driver()
    all_platforms = []

    try:
        print("🔍 ПОИСК ПЛАТФОРМ НА ВСЕХ СТРАНИЦАХ ПРОЕКТОВ")
        print("=" * 60)

        # Получаем проекты из БД
        projects = get_projects_from_db(limit=20)  # Ограничиваем для тестирования
        if not projects:
            print("❌ Проекты в БД не найдены")
            return

        # Сканируем каждый проект с бесконечными попытками
        for i, project in enumerate(projects, 1):
            print(f"\n🚀 Проект {i}/{len(projects)}:")

            platforms = find_platforms_on_project_page(driver, project)
            all_platforms.extend(platforms)

            # Пауза между запросами для предотвращения блокировки
            time.sleep(3)

        # Анализируем результаты (возвращает уникальные платформы)
        unique_platforms = analyze_platforms(all_platforms)

        # Сохраняем результаты в JSON (функция сама удалит дубликаты)
        if all_platforms:
            json_filename = save_platforms_to_json(all_platforms)

    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")

    finally:
        driver.quit()
        print("\n🔒 Браузер закрыт")


if __name__ == "__main__":
    main()
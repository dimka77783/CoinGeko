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
    """Находим платформы на странице конкретного проекта"""
    platforms_found = []

    try:
        print(f"\n🔍 Сканирование: {project['name']} ({project['symbol']})")
        print(f"🌐 URL: {project['url']}")

        # Заходим на страницу проекта
        driver.get(project['url'])
        time.sleep(3)

        # Прокручиваем страницу для загрузки всех элементов
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)

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

    except Exception as e:
        print(f"   ❌ Ошибка сканирования проекта {project['name']}: {e}")

    return platforms_found


def save_platforms_to_json(platforms):
    """Сохраняем найденные платформы в JSON файл"""
    try:
        # Подготавливаем данные для JSON
        json_data = {
            "scan_info": {
                "timestamp": datetime.now().isoformat(),
                "total_platforms": len(platforms),
                "total_projects": len(set(p['project_name'] for p in platforms))
            },
            "platforms": platforms
        }

        # Сохраняем в JSON файл
        filename = f"found_platforms_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)

        print(f"✅ Сохранено {len(platforms)} платформ в файл: {filename}")
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

    # Группируем по проектам
    by_projects = {}
    for platform in platforms:
        project_name = platform['project_name']
        if project_name not in by_projects:
            by_projects[project_name] = []
        by_projects[project_name].append(platform)

    print(f"📈 Всего проектов проверено: {len(by_projects)}")
    print(f"💰 Всего платформ найдено: {len(platforms)}")

    # Уникальные платформы
    unique_platforms = set()
    above_count = 0
    below_count = 0

    for platform in platforms:
        unique_platforms.add(platform['platform_name'])
        if platform['position_status'] == 'above':
            above_count += 1
        elif platform['position_status'] == 'below':
            below_count += 1

    print(f"🎯 Уникальных платформ: {len(unique_platforms)}")
    print(f"✅ Платформ выше 'Trending Token Sales': {above_count}")
    print(f"🚫 Платформ ниже 'Trending Token Sales': {below_count}")

    # Топ платформ
    platform_counts = {}
    for platform in platforms:
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
            status = "✅" if platform['position_status'] == 'above' else "🚫" if platform[
                                                                                   'position_status'] == 'below' else "❓"
            print(f"      {status} {platform['platform_name']} ({platform['platform_text']})")


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

        # Сканируем каждый проект
        for i, project in enumerate(projects, 1):
            print(f"\n🚀 Проект {i}/{len(projects)}:")

            platforms = find_platforms_on_project_page(driver, project)
            all_platforms.extend(platforms)

            # Небольшая пауза между запросами
            time.sleep(1)

        # Сохраняем результаты в JSON
        if all_platforms:
            json_filename = save_platforms_to_json(all_platforms)

        # Анализируем результаты
        analyze_platforms(all_platforms)

    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")

    finally:
        driver.quit()
        print("\n🔒 Браузер закрыт")


if __name__ == "__main__":
    main()
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


def get_projects_from_db(limit=20):
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


def find_trending_token_sales_position(driver):
    """Находим позицию блока Trending Token Sales для определения нижней границы"""
    try:
        trending_elements = driver.find_elements(By.XPATH,
                                                 "//*[contains(text(), 'Trending Token Sales') and not(self::script) and not(ancestor::script)]")

        for element in trending_elements:
            try:
                if element.is_displayed() and element.size['width'] > 0 and element.size['height'] > 0:
                    y_position = element.location['y']
                    if y_position > 100:  # Игнорируем скрытые элементы
                        return y_position
            except:
                continue

        return None
    except Exception as e:
        print(f"   ⚠️ Ошибка поиска Trending Token Sales: {e}")
        return None


def find_investors_section(driver):
    """Находим блок с инвесторами"""
    investors_selectors = [
        "//*[contains(text(), 'Investors and Backers')]",
        "//*[contains(text(), 'Investors & Backers')]",
        "//*[contains(text(), 'Backers')]",
        "//*[contains(text(), 'Investors')]"
    ]

    for selector in investors_selectors:
        try:
            elements = driver.find_elements(By.XPATH, selector)
            for element in elements:
                try:
                    if element.is_displayed() and element.size['width'] > 0:
                        return element
                except:
                    continue
        except:
            continue

    return None


def get_investors_container(investors_section):
    """Получаем контейнер с инвесторами"""
    container_selectors = [
        "./following-sibling::div[1]",
        "./parent::*/following-sibling::div[1]",
        "./parent::div",
        "./ancestor::div[contains(@class, 'section')][1]",
        "./ancestor::section[1]"
    ]

    for selector in container_selectors:
        try:
            container = investors_section.find_element(By.XPATH, selector)
            return container
        except:
            continue

    # Если ничего не найдено, используем сам элемент
    return investors_section


def collect_investors_from_page(container, project, search_top, search_bottom):
    """Собираем инвесторов с текущей страницы"""
    investors = []
    found_links = set()

    # Селекторы для поиска инвесторов в блоке
    selectors = [
        ".//a[contains(@href, '/funds/')]",
        ".//a[contains(@href, '/investors/')]",
        ".//a[contains(@href, '/companies/')]",
        ".//a"  # Все ссылки в блоке инвесторов
    ]

    for selector in selectors:
        try:
            elements = container.find_elements(By.XPATH, selector)
            for element in elements:
                try:
                    href = element.get_attribute('href')
                    text = element.text.strip()
                    position = element.location

                    # Проверяем границы
                    if position['y'] < search_top or position['y'] > search_bottom:
                        continue

                    # Избегаем дубликатов
                    if not href or href in found_links or not text or len(text) < 3:
                        continue

                    # Проверяем релевантность ссылки
                    is_investor = (
                            '/funds/' in href or
                            '/investors/' in href or
                            '/companies/' in href or
                            any(keyword in href.lower() for keyword in ['fund', 'capital', 'ventures', 'labs'])
                    )

                    if is_investor or selector == ".//a":
                        found_links.add(href)

                        # Извлекаем название инвестора
                        if '/funds/' in href:
                            url_name = href.split('/funds/')[-1].replace('-', ' ').title()
                        elif '/investors/' in href:
                            url_name = href.split('/investors/')[-1].replace('-', ' ').title()
                        elif '/companies/' in href:
                            url_name = href.split('/companies/')[-1].replace('-', ' ').title()
                        else:
                            url_name = text

                        # Выбираем лучшее название
                        final_name = text if len(text) > len(url_name) and text != url_name else url_name

                        investor = {
                            'project_id': project['id'],
                            'project_name': project['name'],
                            'project_url': project['url'],
                            'investor_name': final_name,
                            'investor_text': text,
                            'investor_href': href,
                            'position_x': position['x'],
                            'position_y': position['y']
                        }

                        investors.append(investor)

                except Exception as e:
                    continue

        except Exception as e:
            continue

    return investors


def find_next_page_button(container):
    """Ищем кнопку следующей страницы - обновленная версия для CryptoRank"""

    # Специфичные селекторы для CryptoRank
    cryptorank_selectors = [
        # Кнопка Next по aria-label
        ".//button[@aria-label='Next page' and not(@disabled)]",

        # Кнопка с SVG стрелкой вправо (по содержимому path)
        ".//button[not(@disabled) and .//svg//path[contains(@d, '18 12l-8.998') or contains(@d, 'M6.994 5.002')]]",

        # Кнопки пагинации с классами styles_button (не выбранные и не отключенные)
        ".//button[contains(@class, 'styles_button__') and not(contains(@class, 'styles_selected__')) and not(@disabled) and .//span[contains(@class, 'styles_text__')]]"
    ]

    # Базовые селекторы
    base_selectors = [
        ".//button[contains(text(), 'Next')]",
        ".//button[contains(@class, 'next')]",
        ".//a[contains(text(), 'Next')]",
        ".//a[contains(@class, 'next')]",
        ".//button[contains(text(), '→')]",
        ".//a[contains(text(), '→')]",
        ".//button[contains(text(), '>')]",
        ".//a[contains(text(), '>')]",
        ".//button[text()='>']",
        ".//a[text()='>']"
    ]

    # Объединяем все селекторы (сначала специфичные для CryptoRank)
    all_selectors = cryptorank_selectors + base_selectors

    for selector in all_selectors:
        try:
            buttons = container.find_elements(By.XPATH, selector)
            for button in buttons:
                try:
                    if button.is_displayed() and button.is_enabled():
                        # Дополнительная проверка для базовых селекторов со стрелками
                        if selector in [".//button[contains(text(), '>')]", ".//a[contains(text(), '>')]"]:
                            button_text = button.text.strip()
                            if button_text == '>' or button_text in ['>', '→', '▶', '❯']:
                                return button
                        else:
                            return button
                except:
                    continue
        except:
            continue

    return None


def find_next_page_button_advanced(container):
    """Расширенный поиск кнопки следующей страницы с учетом числовой пагинации"""

    # Сначала пробуем стандартные селекторы
    next_button = find_next_page_button(container)
    if next_button:
        return next_button

    # Специфичные селекторы для CryptoRank пагинации
    try:
        # 1. Ищем кнопку "Next page" по aria-label
        next_buttons = container.find_elements(By.XPATH,
                                               ".//button[@aria-label='Next page' and not(@disabled)]")
        if next_buttons:
            for btn in next_buttons:
                if btn.is_displayed() and btn.is_enabled():
                    print(f"   🎯 Найдена кнопка Next по aria-label")
                    return btn

        # 2. Ищем кнопку с SVG стрелкой вправо (по структуре path)
        svg_next_buttons = container.find_elements(By.XPATH,
                                                   ".//button[not(@disabled)]//svg//path[contains(@d, '18 12l-8.998') or contains(@d, 'M6.994 5.002')]")
        if svg_next_buttons:
            for svg_path in svg_next_buttons:
                try:
                    # Поднимаемся до кнопки
                    button = svg_path.find_element(By.XPATH, "./ancestor::button[1]")
                    if button.is_displayed() and button.is_enabled():
                        print(f"   🎯 Найдена кнопка Next по SVG")
                        return button
                except:
                    continue

    except Exception as e:
        print(f"   ⚠️ Ошибка поиска кнопки Next: {e}")

    # Если не нашли кнопку Next, ищем числовую пагинацию
    try:
        # Ищем все кнопки пагинации в контейнере
        page_buttons = container.find_elements(By.XPATH,
                                               ".//button[contains(@class, 'styles_button__') and .//span[contains(@class, 'styles_text__')]]")

        current_page = None
        max_page = 0
        page_elements = {}

        for button in page_buttons:
            try:
                if not button.is_displayed() or not button.is_enabled():
                    continue

                # Получаем текст из span внутри кнопки
                span = button.find_element(By.XPATH, ".//span[contains(@class, 'styles_text__')]")
                text = span.text.strip()

                # Проверяем является ли текст номером страницы
                if text.isdigit():
                    page_num = int(text)
                    page_elements[page_num] = button
                    max_page = max(max_page, page_num)

                    # Определяем текущую страницу по классу selected
                    classes = button.get_attribute('class') or ''
                    if 'styles_selected__' in classes:
                        current_page = page_num
                        print(f"   📍 Текущая страница: {page_num}")

            except:
                continue

        # Если нашли текущую страницу, ищем следующую
        if current_page is not None and current_page < max_page:
            next_page = current_page + 1
            if next_page in page_elements:
                print(f"   ➡️ Переход на страницу {next_page}")
                return page_elements[next_page]

        # Если не смогли определить текущую, но есть страницы - берем страницу 2
        elif page_elements and 2 in page_elements:
            print(f"   ➡️ Переход на страницу 2 (по умолчанию)")
            return page_elements[2]

    except Exception as e:
        print(f"   ⚠️ Ошибка поиска числовой пагинации: {e}")

    return None


def process_pagination_improved(driver, container, project, search_top, search_bottom):
    """Улучшенная обработка пагинации с поддержкой числовой навигации"""
    all_investors = []
    current_page = 1
    max_pages = 10

    # Собираем с первой страницы
    investors = collect_investors_from_page(container, project, search_top, search_bottom)
    all_investors.extend(investors)
    print(f"   📄 Страница {current_page}: найдено {len(investors)} инвесторов")

    # Проверяем наличие пагинации (используем расширенный поиск)
    has_pagination = find_next_page_button_advanced(container) is not None

    if not has_pagination:
        print(f"   📄 Пагинация не обнаружена")
        return all_investors

    print(f"   🔄 Обнаружена пагинация, обрабатываем дополнительные страницы...")

    # Обрабатываем остальные страницы
    while current_page < max_pages:
        next_button = find_next_page_button_advanced(container)

        if not next_button:
            print(f"   ⏹️ Кнопка следующей страницы не найдена")
            break

        try:
            current_page += 1
            print(f"   📄 Переход на страницу {current_page}...")

            # Прокручиваем к кнопке перед кликом
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
            time.sleep(1)

            # Кликаем по кнопке
            driver.execute_script("arguments[0].click();", next_button)
            time.sleep(3)  # Увеличиваем время ожидания для загрузки

            # Собираем данные с новой страницы
            investors = collect_investors_from_page(container, project, search_top, search_bottom)

            if not investors:
                print(f"   ⏹️ Страница {current_page} пуста или не загрузилась")
                break

            all_investors.extend(investors)
            print(f"   📄 Страница {current_page}: найдено {len(investors)} инвесторов")

            # Дополнительная проверка - если получили те же данные, выходим
            if len(all_investors) > len(investors) * current_page * 0.8:  # Примерная проверка на дубликаты
                unique_names = set(inv['investor_name'] for inv in all_investors)
                if len(unique_names) < len(all_investors) * 0.5:  # Слишком много дубликатов
                    print(f"   ⚠️ Обнаружено много дубликатов, возможно пагинация не работает")
                    break

        except Exception as e:
            print(f"   ❌ Ошибка перехода на страницу {current_page}: {e}")
            break

    return all_investors


def scan_project_investors(driver, project, max_retries=3):
    """Сканируем инвесторов конкретного проекта"""

    for attempt in range(max_retries):
        try:
            print(f"\n🔍 {project['name']} ({project['symbol']}) - попытка {attempt + 1}/{max_retries}")
            print(f"🌐 {project['url']}")

            # Загружаем страницу
            driver.set_page_load_timeout(60)
            driver.get(project['url'])
            time.sleep(5)

            # Прокручиваем для загрузки контента
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Находим границы поиска
            trending_position = find_trending_token_sales_position(driver)
            if trending_position:
                print(f"   🎯 Trending Token Sales на Y={trending_position}")

            # Находим блок инвесторов
            investors_section = find_investors_section(driver)
            if not investors_section:
                print(f"   ⚠️ Блок инвесторов не найден")
                return []

            print(f"   📍 Блок инвесторов найден: '{investors_section.text.strip()}'")

            # Получаем контейнер
            container = get_investors_container(investors_section)

            # Определяем границы поиска
            search_top = investors_section.location['y']
            search_bottom = trending_position if trending_position else float('inf')

            print(f"   📏 Границы поиска: Y={search_top} - Y={search_bottom}")

            # Обрабатываем пагинацию (используем улучшенную версию)
            investors = process_pagination_improved(driver, container, project, search_top, search_bottom)

            print(f"   ✅ Найдено инвесторов: {len(investors)}")
            for investor in investors:
                print(f"      👥 {investor['investor_name']}")

            return investors

        except Exception as e:
            print(f"   ❌ Ошибка попытки {attempt + 1}: {e}")

            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 5
                print(f"   ⏳ Ожидание {wait_time} секунд...")
                time.sleep(wait_time)

                # Перезапуск браузера при критических ошибках
                if "timeout" in str(e).lower() or "connection" in str(e).lower():
                    print(f"   🔄 Перезапуск браузера...")
                    try:
                        driver.quit()
                        time.sleep(3)
                        driver = setup_driver()
                    except:
                        pass
            else:
                print(f"   💥 Все попытки исчерпаны")

    return []


def remove_duplicates(investors):
    """Удаляем дубликаты инвесторов"""
    print(f"\n🔧 Удаление дубликатов:")
    print(f"📊 До: {len(investors)} инвесторов")

    seen = set()
    unique = []

    for investor in investors:
        key = (
            investor['project_id'],
            investor['investor_name'].lower().strip(),
            investor.get('investor_href', '')
        )

        if key not in seen:
            seen.add(key)
            unique.append(investor)

    print(f"🗑️ Удалено дубликатов: {len(investors) - len(unique)}")
    print(f"✅ Уникальных: {len(unique)}")

    return unique


def save_to_json(investors):
    """Сохраняем результаты в JSON"""
    try:
        unique_investors = remove_duplicates(investors)

        data = {
            "scan_info": {
                "timestamp": datetime.now().isoformat(),
                "total_found": len(investors),
                "unique_investors": len(unique_investors),
                "duplicates_removed": len(investors) - len(unique_investors),
                "projects_scanned": len(set(inv['project_name'] for inv in unique_investors))
            },
            "investors": unique_investors
        }

        filename = f"investors_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"✅ Сохранено в {filename}")
        print(f"   👥 Уникальных инвесторов: {len(unique_investors)}")

        return filename

    except Exception as e:
        print(f"❌ Ошибка сохранения: {e}")
        return None


def analyze_results(investors):
    """Анализируем результаты"""
    if not investors:
        print("❌ Нет данных для анализа")
        return

    unique_investors = remove_duplicates(investors)

    print(f"\n📊 АНАЛИЗ РЕЗУЛЬТАТОВ:")
    print("=" * 40)

    # Общая статистика
    projects = {}
    investor_counts = {}

    for inv in unique_investors:
        # По проектам
        project = inv['project_name']
        if project not in projects:
            projects[project] = []
        projects[project].append(inv)

        # По инвесторам
        name = inv['investor_name']
        investor_counts[name] = investor_counts.get(name, 0) + 1

    print(f"📈 Проектов обработано: {len(projects)}")
    print(f"👥 Уникальных инвесторов: {len(set(inv['investor_name'] for inv in unique_investors))}")
    print(f"🔗 Инвесторов со ссылками: {sum(1 for inv in unique_investors if inv.get('investor_href'))}")

    # Топ инвесторов
    print(f"\n🏆 ТОП-10 ИНВЕСТОРОВ:")
    top_investors = sorted(investor_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    for i, (name, count) in enumerate(top_investors, 1):
        print(f"   {i:2d}. {name:<30} - {count} проектов")

    # По проектам
    print(f"\n📋 ПО ПРОЕКТАМ:")
    for project_name, project_investors in projects.items():
        print(f"\n   🎯 {project_name} ({len(project_investors)} инвесторов):")
        for inv in project_investors:
            print(f"      👥 {inv['investor_name']}")


def main():
    """Главная функция"""
    driver = setup_driver()
    all_investors = []

    try:
        print("🔍 СБОР ИНВЕСТОРОВ ИЗ БЛОКОВ 'INVESTORS AND BACKERS'")
        print("=" * 60)

        # Получаем проекты
        projects = get_projects_from_db(20)
        if not projects:
            print("❌ Проекты не найдены")
            return

        # Сканируем каждый проект
        for i, project in enumerate(projects, 1):
            print(f"\n🚀 Проект {i}/{len(projects)}:")

            investors = scan_project_investors(driver, project)
            all_investors.extend(investors)

            # Пауза между проектами
            time.sleep(2)

        # Анализируем и сохраняем
        analyze_results(all_investors)

        if all_investors:
            save_to_json(all_investors)

    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")

    finally:
        driver.quit()
        print("\n🔒 Браузер закрыт")


if __name__ == "__main__":
    main()
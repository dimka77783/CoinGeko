#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import time
import re
import os
import psycopg2
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime

# --- Настройки БД ---
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': os.environ.get('DB_PORT', '5432'),
    'database': os.environ.get('DB_NAME', 'crypto_db'),
    'user': os.environ.get('DB_USER', 'crypto_user'),
    'password': os.environ.get('DB_PASSWORD', 'crypto_password')
}


def setup_driver():
    """Настройка браузера с включёнными стилями и шрифтами"""
    print("🔧 Запуск браузера...")
    options = Options()

    # Важно: включаем стили и шрифты, иначе легенда не отображается
    chrome_prefs = {
        "profile.default_content_settings": {
            "images": 2,      # Можно отключить
            "javascript": 1   # Обязательно включено
        },
        "profile.managed_default_content_settings": {
            "images": 2,
            "stylesheets": 1,  # ✅ ВКЛЮЧЕНО
            "fonts": 1,        # ✅ ВКЛЮЧЕНО
            "javascript": 1,
            "plugins": 2,
            "popups": 2,
            "geolocation": 2,
            "notifications": 2
        }
    }

    # Уберите комментарий, чтобы видеть браузер (для отладки)
    # options.add_argument('--headless=new')

    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

    options.add_experimental_option("prefs", chrome_prefs)
    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(10)
    print("   ✅ Браузер запущен (стили и шрифты включены)")
    return driver


def get_projects_from_db(limit=20):
    """Получаем проекты из таблицы cryptorank_upcoming"""
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
        return [
            {'id': row[0], 'name': row[1], 'symbol': row[2], 'url': row[3].strip()}
            for row in projects
        ]
    except Exception as e:
        print(f"❌ Ошибка БД: {e}")
        return []


def is_ico_page(url):
    """Проверяем, что это ICO-страница"""
    return '/ico/' in url.lower()


def find_tokenomics_section(driver):
    """Ищем секцию Tokenomics"""
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//h2[contains(text(), 'Tokenomics')]"))
        )
        header = driver.find_element(By.XPATH, "//h2[contains(text(), 'Tokenomics')]")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", header)
        time.sleep(1)
        print("   ✅ Секция 'Tokenomics' найдена")
        return True
    except Exception as e:
        print(f"   ⚠️ Секция 'Tokenomics' не найдена: {e}")
        return False


def parse_initial_values(driver):
    """Парсим 'Initial values'"""
    values = {}
    try:
        container = driver.find_element(By.XPATH, "//h3[contains(text(), 'Initial values')]/following-sibling::div")
        items = container.find_elements(By.XPATH, ".//div[contains(@class, 'styles_tokenomics_item__')]")
        for item in items:
            try:
                label_elem = item.find_element(By.XPATH, ".//p[contains(@class, 'bxOQXY')]")
                value_elem = item.find_element(By.XPATH, ".//p[contains(@class, 'iBRAOB')]")
                label = label_elem.text.strip().rstrip(':')
                value = value_elem.text.strip()
                if label and value:
                    values[label] = value
            except:
                continue
    except Exception as e:
        print(f"   ⚠️ Не удалось распарсить Initial values: {e}")
    return values if values else None


def parse_token_allocation(driver):
    """Парсим 'Token allocation'"""
    allocation = {}
    try:
        container = driver.find_element(By.XPATH, "//h3[contains(text(), 'Token allocation')]/following-sibling::div")
        items = container.find_elements(By.XPATH, ".//div[contains(@class, 'styles_tokenomics_item__')]")
        for item in items:
            try:
                label_elem = item.find_element(By.XPATH, ".//p[contains(@class, 'bxOQXY')]")
                value_elem = item.find_element(By.XPATH, ".//p[contains(@class, 'iBRAOB')]")
                label = label_elem.text.strip().rstrip(':')
                value = value_elem.text.strip()
                if '\n' in value:
                    value = value.split('\n')[0].strip()
                if label and value:
                    allocation[label] = value
            except:
                continue
    except Exception as e:
        print(f"   ⚠️ Не удалось распарсить Token allocation: {e}")
    return allocation if allocation else None


def parse_distribution_chart(driver):
    """Парсим распределение из <ul class='sc-3b4c91db-0'> с отладкой"""
    distribution = []
    try:
        # Явное ожидание появления списка
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, "//ul[contains(@class, 'sc-3b4c91db-0')]"))
        )
        # Прокрутка к секции
        tokenomics = driver.find_element(By.XPATH, "//h2[contains(text(), 'Tokenomics')]")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tokenomics)
        time.sleep(2)

        # Поиск списка
        list_container = driver.find_element(By.XPATH, "//ul[contains(@class, 'sc-3b4c91db-0')]")
        items = list_container.find_elements(By.XPATH, ".//li")
        print(f"   🎯 Найдено {len(items)} элементов в легенде")

        for i, item in enumerate(items):
            try:
                # Прокрутка к элементу
                driver.execute_script("arguments[0].scrollIntoView({block: 'nearest'});", item)
                time.sleep(0.5)

                # Поиск категории
                category_elem = item.find_element(By.XPATH, ".//p[contains(@class, 'hMaTTx')]")
                category = category_elem.text.strip()

                # Поиск процента
                percentage_elem = item.find_element(By.XPATH, ".//div[contains(@class, 'fsLhYV')]//span")
                percentage = percentage_elem.text.strip()

                print(f"   🔎 [{i+1}] Категория: '{category}', Процент: '{percentage}'")

                if category and percentage:
                    distribution.append({
                        'category': category,
                        'percentage': percentage
                    })
                else:
                    print(f"   ⚠️ [{i+1}] Пропущено: пустой текст")
            except Exception as e:
                print(f"   ❌ [{i+1}] Ошибка: {e}")
                continue

        if distribution:
            print(f"   ✅ Успешно: найдено {len(distribution)} категорий распределения")
            return distribution
        else:
            print("   ⚠️ Все элементы найдены, но текст не извлечён")
    except Exception as e:
        print(f"   ⚠️ Не удалось найти легенду распределения: {e}")
    return None


def scan_project_tokenomics(driver, project, max_retries=3):
    """Парсим токеномику с одной страницы"""
    for attempt in range(max_retries):
        try:
            print(f"\n🔍 Парсим токеномику: {project['name']} (попытка {attempt + 1}/{max_retries})")

            if not is_ico_page(project['url']):
                print("   ⚠️ Пропуск: не ICO-страница")
                return None

            print(f"🌐 Открываем: {project['url']}")
            driver.get(project['url'])

            # Явное ожидание загрузки страницы
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

            if not find_tokenomics_section(driver):
                return None

            # Сбор данных
            data = {
                'project_id': project['id'],
                'project_name': project['name'],
                'project_symbol': project['symbol'],
                'ico_url': project['url'],
                'scraped_at': datetime.now().isoformat()
            }

            data['initial_values'] = parse_initial_values(driver)
            data['token_allocation'] = parse_token_allocation(driver)
            data['distribution'] = parse_distribution_chart(driver)

            print(f"   ✅ Успешно: токеномика собрана")
            return data

        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
            if attempt < max_retries - 1:
                time.sleep(3 + attempt * 2)
                driver.refresh()
            else:
                print(f"   💥 Все попытки исчерпаны")
    return None


def save_to_json(data_list):
    """Сохраняем результат в JSON"""
    result = {
        "summary": {
            "total_projects": len(data_list),
            "scraped_at": datetime.now().isoformat()
        },
        "tokenomics": data_list
    }
    filename = f"tokenomics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n✅ Данные сохранены в: {filename}")
    return filename


def main():
    print("📊 ПАРСИНГ ТОКЕНОМИКИ С ICO-СТРАНИЦ (из БД)")
    print("=" * 60)

    driver = setup_driver()
    all_tokenomics = []

    try:
        projects = get_projects_from_db(limit=20)
        if not projects:
            print("❌ Нет проектов для обработки")
            return

        for i, project in enumerate(projects, 1):
            print(f"\n🚀 [{i}/{len(projects)}] Обработка: {project['name']}")
            data = scan_project_tokenomics(driver, project)
            if data is not None:
                all_tokenomics.append(data)
            time.sleep(2)  # Антибан

    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
    finally:
        driver.quit()
        print("\n🔒 Браузер закрыт")

    # Сохранение в JSON
    if all_tokenomics:
        save_to_json(all_tokenomics)

        print(f"\n📋 Пример данных:")
        ex = all_tokenomics[0]
        print(f"  🪙 {ex['project_name']}")
        if ex['initial_values']:
            print(f"     📈 {ex['initial_values']}")
        if ex['token_allocation']:
            print(f"     📦 {ex['token_allocation']}")
        if ex['distribution']:
            top = ", ".join([f"{d['category']}({d['percentage']})" for d in ex['distribution'][:3]])
            print(f"     🎯 {top}")
    else:
        print("❌ Ничего не найдено.")


if __name__ == "__main__":
    main()
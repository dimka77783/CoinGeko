#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from datetime import datetime


class DeduplicatedRoundsParser:
    def __init__(self):
        self.base_url = "https://cryptorank.io"

    def setup_driver(self, headless=True):
        """Настройка браузера"""
        options = webdriver.ChromeOptions()

        if headless:
            options.add_argument('--headless')

        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        options.add_argument('--window-size=1920,1080')

        driver = webdriver.Chrome(options=options)
        return driver

    def find_unique_round_cards(self, driver):
        """Поиск только уникальных карточек раундов"""
        print("🔍 Поиск уникальных карточек раундов...")

        # Основной селектор для карточек раундов
        main_selector = "//div[contains(@class, 'sc-d0f02631-0') and contains(@class, 'dRuXgm')]"

        try:
            cards = driver.find_elements(By.XPATH, main_selector)
            print(f"   Найдено потенциальных карточек: {len(cards)}")

            # Фильтруем и дедуплицируем
            unique_cards = self.deduplicate_cards(cards)

            print(f"✅ Уникальных карточек: {len(unique_cards)}")
            return unique_cards

        except Exception as e:
            print(f"❌ Ошибка поиска карточек: {e}")
            return []

    def deduplicate_cards(self, cards):
        """Удаление дублирующих карточек"""
        print("   🔄 Дедупликация карточек...")

        unique_cards = []
        seen_signatures = set()

        for card in cards:
            try:
                # Создаем уникальную подпись карточки
                signature = self.create_card_signature(card)

                if signature and signature not in seen_signatures:
                    # Проверяем, что это действительно валидная карточка раунда
                    if self.is_valid_round_card(card):
                        unique_cards.append(card)
                        seen_signatures.add(signature)
                        print(f"      ✓ Уникальная карточка: {signature[:50]}...")

            except Exception as e:
                print(f"      ❌ Ошибка анализа карточки: {e}")
                continue

        return unique_cards

    def create_card_signature(self, card):
        """Создание уникальной подписи карточки для дедупликации"""
        try:
            card_text = card.text.strip()

            # Извлекаем ключевые характеристики
            round_type = self.extract_round_type(card_text)
            platform = self.extract_platform_from_text(card_text)
            raising_amount = self.extract_raising_amount(card_text)
            token_price = self.extract_token_price(card_text)
            tokens_for_sale = self.extract_tokens_for_sale(card_text)

            # Создаем подпись из ключевых данных
            signature_parts = [
                round_type or "unknown",
                platform or "no_platform",
                raising_amount or "no_amount",
                token_price or "no_price",
                tokens_for_sale or "no_tokens"
            ]

            signature = "|".join(signature_parts)
            return signature

        except:
            return None

    def is_valid_round_card(self, card):
        """Проверка валидности карточки раунда"""
        try:
            card_text = card.text.strip()

            # Должен содержать тип раунда
            round_types = ['IDO', 'Private', 'Seed', 'Strategic', 'Public', 'Angel', 'Pre-sale']
            has_round_type = any(rtype in card_text for rtype in round_types)

            # Должен содержать финансовую информацию
            has_financial_info = any(indicator in card_text for indicator in ['$', 'Raising', 'Price'])

            # Минимальная длина текста (исключаем пустые элементы)
            has_sufficient_content = len(card_text) > 50

            return has_round_type and has_financial_info and has_sufficient_content

        except:
            return False

    def extract_round_type(self, text):
        """Извлечение типа раунда"""
        round_types = ['IDO', 'Private', 'Seed', 'Strategic', 'Public', 'Angel', 'Pre-sale']
        for rtype in round_types:
            if rtype in text:
                return rtype
        return None

    def extract_platform_from_text(self, text):
        """Извлечение платформы из текста"""
        platforms = [
            'Poolz Finance', 'Seedify', 'Eesee', 'AITECH PAD', 'KingdomStarter',
            'Spores Network', 'Echo', 'Polkastarter', 'DAO Maker', 'TrustSwap',
            'Coin Terminal', 'BSCS', 'GameFi'
        ]

        for platform in platforms:
            if platform in text:
                return platform
        return None

    def extract_raising_amount(self, text):
        """Извлечение суммы сбора"""
        match = re.search(r'Raising[:\s]*(\$\s*[\d,\.]+[KMB]?)', text)
        if match:
            return match.group(1).strip()
        return None

    def extract_token_price(self, text):
        """Извлечение цены токена"""
        match = re.search(r'Price[:\s]*(\$\s*[\d\.]+)', text)
        if match:
            return match.group(1).strip()
        return None

    def extract_tokens_for_sale(self, text):
        """Извлечение количества токенов"""
        match = re.search(r'Tokens For Sale[:\s]*([\d,\.]+)', text)
        if match:
            return match.group(1).strip()
        return None

    def extract_complete_card_data(self, card, card_number):
        """Полное извлечение данных из карточки"""
        try:
            card_text = card.text.strip()

            data = {
                'id': card_number,
                'type': self.extract_round_type(card_text),
                'status': self.extract_status(card_text),
                'date': self.extract_date(card_text),
                'raising_amount': self.extract_raising_amount(card_text),
                'token_price': self.extract_token_price(card_text),
                'tokens_for_sale': self.extract_tokens_for_sale(card_text),
                'platform': self.extract_platform_info_complete(card),
                'lockup': self.extract_lockup(card_text),
                'raw_text_preview': card_text[:200] + "..." if len(card_text) > 200 else card_text
            }

            return data

        except Exception as e:
            print(f"   ❌ Ошибка извлечения данных карточки {card_number}: {e}")
            return None

    def extract_status(self, text):
        """Извлечение статуса"""
        if 'Upcoming' in text:
            return 'Upcoming'
        elif 'Active' in text or 'Live' in text:
            return 'Active'
        elif 'Ended' in text:
            return 'Ended'
        return None

    def extract_date(self, text):
        """Извлечение даты"""
        date_match = re.search(r'(\d{1,2}\s+\w+\s+\d{4}(?:\s*[—\-]\s*\d{1,2}\s+\w+\s+\d{4})?)', text)
        if date_match:
            return date_match.group(1)
        elif 'TBA' in text:
            return 'TBA'
        return None

    def extract_platform_info_complete(self, card):
        """Полное извлечение информации о платформе"""
        try:
            # 1. Поиск в ссылках
            platform_links = card.find_elements(By.XPATH, ".//a[contains(@href, '/fundraising-platforms/')]")
            for link in platform_links:
                text = link.text.strip()
                if text and len(text) > 1:
                    return {
                        'name': text,
                        'url': link.get_attribute('href'),
                        'source': 'link'
                    }

            # 2. Поиск в тексте
            card_text = card.text
            platform_name = self.extract_platform_from_text(card_text)
            if platform_name:
                return {
                    'name': platform_name,
                    'source': 'text'
                }

            return None

        except:
            return None

    def extract_lockup(self, text):
        """Извлечение условий lock-up"""
        lockup_match = re.search(r'Lock-up[:\s]*([^\n]+)', text)
        if lockup_match:
            return lockup_match.group(1).strip()[:100]  # Ограничиваем длину
        return None

    def parse_project_rounds_clean(self, project_url):
        """Чистый парсинг раундов проекта без дублей"""
        driver = self.setup_driver(headless=True)

        try:
            print(f"🎯 Парсинг проекта: {project_url}")
            driver.get(project_url)
            time.sleep(3)

            # Получаем название проекта
            project_name = "Unknown"
            try:
                h1_elements = driver.find_elements(By.XPATH, "//h1")
                if h1_elements:
                    project_name = h1_elements[0].text.strip()
            except:
                pass

            # Ищем уникальные карточки
            unique_cards = self.find_unique_round_cards(driver)

            if not unique_cards:
                return {
                    'project_name': project_name,
                    'url': project_url,
                    'status': 'No rounds found',
                    'rounds_count': 0,
                    'rounds': []
                }

            # Извлекаем данные из уникальных карточек
            rounds_data = []
            for i, card in enumerate(unique_cards, 1):
                card_data = self.extract_complete_card_data(card, i)
                if card_data:
                    rounds_data.append(card_data)
                    print(
                        f"   ✓ Раунд {i}: {card_data['type']} | {card_data['raising_amount']} | {card_data.get('platform', {}).get('name', 'N/A')}")

            result = {
                'project_name': project_name,
                'url': project_url,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'status': 'Success',
                'rounds_count': len(rounds_data),
                'rounds': rounds_data
            }

            return result

        except Exception as e:
            print(f"❌ Ошибка парсинга: {e}")
            return {
                'project_name': project_name,
                'url': project_url,
                'status': f'Error: {str(e)}',
                'rounds_count': 0,
                'rounds': []
            }
        finally:
            driver.quit()

    def save_clean_results(self, data, filename=None):
        """Сохранение чистых результатов"""
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'rounds_clean_{timestamp}.json'

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"\n💾 Чистые результаты сохранены в {filename}")
        return filename

    def print_clean_summary(self, results):
        """Вывод чистой сводки"""
        if isinstance(results, list):
            print(f"\n📊 ЧИСТАЯ СВОДКА ПО {len(results)} ПРОЕКТАМ:")
            print("=" * 70)

            for project in results:
                print(f"\n📁 {project.get('project_name', 'Unknown')}")
                print(f"   Уникальных раундов: {project.get('rounds_count', 0)}")
                print(f"   Статус: {project.get('status', 'Unknown')}")

                for i, round_data in enumerate(project.get('rounds', []), 1):
                    rtype = round_data.get('type', 'N/A')
                    status = round_data.get('status', 'N/A')
                    amount = round_data.get('raising_amount', 'N/A')
                    platform_info = round_data.get('platform', {})
                    platform = platform_info.get('name', 'N/A') if platform_info else 'N/A'
                    date = round_data.get('date', 'N/A')

                    print(f"     {i}. {rtype} | {status} | {amount} | {platform} | {date}")

        else:
            # Один проект
            print(f"\n📊 РЕЗУЛЬТАТ:")
            print(f"Проект: {results.get('project_name', 'Unknown')}")
            print(f"Уникальных раундов: {results.get('rounds_count', 0)}")

            for i, round_data in enumerate(results.get('rounds', []), 1):
                rtype = round_data.get('type', 'N/A')
                status = round_data.get('status', 'N/A')
                amount = round_data.get('raising_amount', 'N/A')
                platform_info = round_data.get('platform', {})
                platform = platform_info.get('name', 'N/A') if platform_info else 'N/A'
                date = round_data.get('date', 'N/A')

                print(f"  {i}. {rtype} | {status} | {amount} | {platform} | {date}")


def main():
    """Главная функция с дедупликацией"""
    print("🚀 Парсер раундов CryptoRank с дедупликацией")
    print("=" * 60)

    parser = DeduplicatedRoundsParser()

    # Тестируем на проекте Uomi
    test_url = "https://cryptorank.io/ico/uomi"

    print(f"📋 Тестирование дедупликации на: {test_url}")

    result = parser.parse_project_rounds_clean(test_url)

    # Выводим чистую сводку
    parser.print_clean_summary(result)

    # Сохраняем чистые результаты
    filename = parser.save_clean_results(result)

    print(f"\n✅ Готово! Теперь должно быть ровно 7 уникальных раундов")
    print(f"💾 Чистые данные в {filename}")


if __name__ == "__main__":
    main()
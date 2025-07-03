#!/usr/bin/env python3
"""
Скрипт для очистки всех таблиц в базе данных криптовалют
"""
import psycopg2
import os
import sys

# База данных
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': os.environ.get('DB_PORT', '5432'),
    'database': os.environ.get('DB_NAME', 'crypto_db'),
    'user': os.environ.get('DB_USER', 'crypto_user'),
    'password': os.environ.get('DB_PASSWORD', 'crypto_password')
}


def drop_all_tables():
    """Удаляет ВСЕ таблицы из базы данных"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        print("🔄 Подключение к БД...")
        print(f"   База данных: {DB_CONFIG['database']}")
        print(f"   Хост: {DB_CONFIG['host']}")

        # Получаем список ВСЕХ таблиц в схеме public
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
        all_tables = cursor.fetchall()

        print(f"\n📊 Найдено всего таблиц: {len(all_tables)}")

        if len(all_tables) == 0:
            print("✅ База данных уже пуста!")
            return

        # Показываем список таблиц
        print("\n📋 Таблицы для удаления:")
        for i, table in enumerate(all_tables[:10], 1):
            print(f"   {i}. {table[0]}")
        if len(all_tables) > 10:
            print(f"   ... и еще {len(all_tables) - 10} таблиц")

        # Спрашиваем подтверждение
        print(f"\n⚠️  КРИТИЧЕСКОЕ ПРЕДУПРЕЖДЕНИЕ!")
        print(f"   Это действие ПОЛНОСТЬЮ УДАЛИТ ВСЕ ТАБЛИЦЫ И ДАННЫЕ!")
        print(f"   Будет удалено {len(all_tables)} таблиц.")
        print(f"   Структура базы данных будет полностью уничтожена.")
        print(f"   ЭТО ДЕЙСТВИЕ НЕОБРАТИМО!")

        confirmation1 = input("\n❓ Вы АБСОЛЮТНО уверены? Введите 'DELETE ALL TABLES': ")

        if confirmation1 != 'DELETE ALL TABLES':
            print("❌ Операция отменена")
            return

        confirmation2 = input("❓ Последнее предупреждение! Введите 'YES I AM SURE': ")

        if confirmation2 != 'YES I AM SURE':
            print("❌ Операция отменена")
            return

        print("\n🗑️  Начинаем ПОЛНОЕ УДАЛЕНИЕ ВСЕХ ТАБЛИЦ...")

        # Отключаем проверки внешних ключей
        cursor.execute("SET session_replication_role = replica;")

        # Удаляем все таблицы
        deleted_tables = 0
        for table_name in all_tables:
            try:
                cursor.execute(f"DROP TABLE IF EXISTS \"{table_name[0]}\" CASCADE")
                deleted_tables += 1
                print(f"   🗑️  Удалена таблица: {table_name[0]} ({deleted_tables}/{len(all_tables)})")
            except Exception as e:
                print(f"   ⚠️ Ошибка при удалении {table_name[0]}: {e}")

        # Включаем обратно проверки внешних ключей
        cursor.execute("SET session_replication_role = DEFAULT;")

        # Удаляем все последовательности (sequences)
        cursor.execute("""
            SELECT sequence_name 
            FROM information_schema.sequences 
            WHERE sequence_schema = 'public'
        """)
        sequences = cursor.fetchall()

        for seq_name in sequences:
            try:
                cursor.execute(f"DROP SEQUENCE IF EXISTS \"{seq_name[0]}\" CASCADE")
                print(f"   🗑️  Удалена последовательность: {seq_name[0]}")
            except Exception as e:
                print(f"   ⚠️ Ошибка при удалении последовательности {seq_name[0]}: {e}")

        # Удаляем все функции пользователя
        cursor.execute("""
            SELECT routine_name 
            FROM information_schema.routines 
            WHERE routine_schema = 'public' 
            AND routine_type = 'FUNCTION'
        """)
        functions = cursor.fetchall()

        for func_name in functions:
            try:
                cursor.execute(f"DROP FUNCTION IF EXISTS \"{func_name[0]}\" CASCADE")
                print(f"   🗑️  Удалена функция: {func_name[0]}")
            except Exception as e:
                print(f"   ⚠️ Ошибка при удалении функции {func_name[0]}: {e}")

        # Применяем изменения
        conn.commit()

        # Проверяем результат
        cursor.execute("""
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        remaining_tables = cursor.fetchone()[0]

        print(f"\n📊 Результат полного удаления:")
        print(f"   ✅ Удалено таблиц: {deleted_tables}")
        print(f"   ✅ Удалено последовательностей: {len(sequences)}")
        print(f"   ✅ Удалено функций: {len(functions)}")
        print(f"   📊 Оставшихся таблиц: {remaining_tables}")

        if remaining_tables == 0:
            print("\n🎉 БАЗА ДАННЫХ ПОЛНОСТЬЮ ОЧИЩЕНА!")
            print("   Схема public теперь пуста.")
            print("   Для восстановления структуры запустите init_db.sql")
        else:
            print("\n⚠️  Остались некоторые таблицы. Возможно, системные.")

    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        if 'conn' in locals():
            conn.rollback()
            print("🔄 Изменения отменены")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


def clear_database():
    """Очищает все таблицы в БД"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        print("🔄 Подключение к БД...")
        print(f"   База данных: {DB_CONFIG['database']}")
        print(f"   Хост: {DB_CONFIG['host']}")

        # Получаем список всех OHLC таблиц
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name LIKE 'ohlc_%'
            ORDER BY table_name
        """)
        ohlc_tables = cursor.fetchall()

        print(f"\n📊 Найдено OHLC таблиц: {len(ohlc_tables)}")

        # Спрашиваем подтверждение
        print("\n⚠️  ВНИМАНИЕ! Это действие удалит ВСЕ данные из базы!")
        print("   Будут очищены:")
        print("   - Таблица cryptocurrencies")
        print(f"   - {len(ohlc_tables)} OHLC таблиц")

        confirmation = input("\n❓ Вы уверены? Введите 'YES' для подтверждения: ")

        if confirmation.upper() != 'YES':
            print("❌ Операция отменена")
            return

        print("\n🗑️  Начинаем очистку...")

        # Удаляем все OHLC таблицы
        deleted_tables = 0
        for table_name in ohlc_tables:
            try:
                cursor.execute(f"DROP TABLE IF EXISTS \"{table_name[0]}\" CASCADE")
                deleted_tables += 1
                if deleted_tables % 10 == 0:
                    print(f"   Удалено таблиц: {deleted_tables}/{len(ohlc_tables)}")
            except Exception as e:
                print(f"   ⚠️ Ошибка при удалении {table_name[0]}: {e}")

        print(f"✅ Удалено OHLC таблиц: {deleted_tables}")

        # Очищаем основную таблицу
        cursor.execute("TRUNCATE TABLE cryptocurrencies RESTART IDENTITY CASCADE")
        print("✅ Таблица cryptocurrencies очищена")

        # Сбрасываем последовательности
        cursor.execute("ALTER SEQUENCE cryptocurrencies_id_seq RESTART WITH 1")
        print("✅ Счетчики сброшены")

        # Применяем изменения
        conn.commit()

        # Проверяем результат
        cursor.execute("SELECT COUNT(*) FROM cryptocurrencies")
        count = cursor.fetchone()[0]

        print(f"\n📊 Итоговая статистика:")
        print(f"   Записей в cryptocurrencies: {count}")
        print(f"   OHLC таблиц: 0")

        print("\n✅ База данных успешно очищена!")

    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        if 'conn' in locals():
            conn.rollback()
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


def clear_only_data():
    """Очищает только данные, оставляя структуру таблиц"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        print("🔄 Подключение к БД...")

        # Получаем список всех OHLC таблиц
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name LIKE 'ohlc_%'
        """)
        ohlc_tables = cursor.fetchall()

        print(f"\n📊 Найдено OHLC таблиц: {len(ohlc_tables)}")

        # Спрашиваем подтверждение
        print("\n⚠️  Это действие удалит все данные, но сохранит структуру таблиц")
        confirmation = input("❓ Продолжить? (yes/no): ")

        if confirmation.lower() != 'yes':
            print("❌ Операция отменена")
            return

        print("\n🗑️  Очищаем данные...")

        # Очищаем OHLC таблицы
        cleared_tables = 0
        for table_name in ohlc_tables:
            try:
                cursor.execute(f"TRUNCATE TABLE \"{table_name[0]}\"")
                cleared_tables += 1
            except Exception as e:
                print(f"   ⚠️ Ошибка при очистке {table_name[0]}: {e}")

        print(f"✅ Очищено OHLC таблиц: {cleared_tables}")

        # Очищаем основную таблицу
        cursor.execute("TRUNCATE TABLE cryptocurrencies RESTART IDENTITY CASCADE")
        print("✅ Таблица cryptocurrencies очищена")

        conn.commit()
        print("\n✅ Данные успешно удалены!")

    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        if 'conn' in locals():
            conn.rollback()
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


def show_statistics():
    """Показывает статистику БД перед очисткой"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        print("📊 Статистика базы данных:")

        # Общее количество таблиц
        cursor.execute("""
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        total_tables = cursor.fetchone()[0]
        print(f"\n   Всего таблиц: {total_tables}")

        # Количество криптовалют (если таблица существует)
        try:
            cursor.execute("SELECT COUNT(*) FROM cryptocurrencies")
            crypto_count = cursor.fetchone()[0]
            print(f"   Криптовалют: {crypto_count}")
        except:
            print(f"   Криптовалют: таблица не существует")

        # Количество OHLC таблиц
        cursor.execute("""
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name LIKE 'ohlc_%'
        """)
        ohlc_tables_count = cursor.fetchone()[0]
        print(f"   OHLC таблиц: {ohlc_tables_count}")

        # Общее количество OHLC записей (пример для первых 5 таблиц)
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name LIKE 'ohlc_%'
            LIMIT 5
        """)
        ohlc_tables = cursor.fetchall()

        total_ohlc_records = 0
        for table_name in ohlc_tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM \"{table_name[0]}\"")
                count = cursor.fetchone()[0]
                total_ohlc_records += count
            except:
                pass

        if len(ohlc_tables) > 0:
            if ohlc_tables_count > 5:
                print(f"   OHLC записей: ~{total_ohlc_records} (в первых 5 таблицах)")
            else:
                print(f"   OHLC записей: {total_ohlc_records}")
        else:
            print(f"   OHLC записей: 0")

        # Размер БД
        cursor.execute("""
            SELECT pg_size_pretty(pg_database_size(%s))
        """, (DB_CONFIG['database'],))
        db_size = cursor.fetchone()[0]
        print(f"   Размер БД: {db_size}")

        # Список первых 10 таблиц
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name
            LIMIT 10
        """)
        tables_sample = cursor.fetchall()

        if tables_sample:
            print(f"\n📋 Примеры таблиц:")
            for i, table in enumerate(tables_sample, 1):
                print(f"   {i}. {table[0]}")
            if total_tables > 10:
                print(f"   ... и еще {total_tables - 10} таблиц")

    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


def restore_database():
    """Восстанавливает структуру базы данных из init_db.sql"""
    print("🔧 ВОССТАНОВЛЕНИЕ СТРУКТУРЫ БАЗЫ ДАННЫХ")
    print("   Это действие:")
    print("   1. Восстановит структуру из init_db.sql")
    print("   2. НЕ удаляет существующие данные")
    print("   3. Создаст недостающие таблицы, функции, триггеры")

    confirmation = input("\n❓ Продолжить восстановление? (yes/no): ")

    if confirmation.lower() != 'yes':
        print("❌ Операция отменена")
        return

    print("\n🔧 Восстановление структуры...")

    if not os.path.exists('init_db.sql'):
        print("❌ Файл init_db.sql не найден в текущей директории")
        print("💡 Убедитесь, что находитесь в директории проекта")
        print("💡 Или укажите путь к файлу init_db.sql")
        return

    try:
        # Сначала проверяем подключение к БД
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        print("✅ Подключение к БД установлено")

        # Проверяем количество таблиц до восстановления
        cursor.execute("""
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        tables_before = cursor.fetchone()[0]
        print(f"📊 Таблиц до восстановления: {tables_before}")

        cursor.close()
        conn.close()

        # Выполняем восстановление через Docker
        import subprocess
        result = subprocess.run([
            'docker', 'exec', '-i', 'crypto_db',
            'psql', '-U', DB_CONFIG['user'], '-d', DB_CONFIG['database']
        ], input=open('init_db.sql', 'r').read(), text=True, capture_output=True)

        if result.returncode == 0:
            print("✅ Структура базы данных восстановлена!")

            # Проверяем результат
            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor()

            # Количество таблиц после восстановления
            cursor.execute("""
                SELECT COUNT(*) 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            tables_after = cursor.fetchone()[0]

            # Проверяем основную таблицу
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'cryptocurrencies'
                )
            """)
            cryptocurrencies_exists = cursor.fetchone()[0]

            # Проверяем функции
            cursor.execute("""
                SELECT COUNT(*) 
                FROM information_schema.routines 
                WHERE routine_schema = 'public' 
                AND routine_type = 'FUNCTION'
            """)
            functions_count = cursor.fetchone()[0]

            # Проверяем триггеры
            cursor.execute("""
                SELECT COUNT(*) 
                FROM information_schema.triggers 
                WHERE trigger_schema = 'public'
            """)
            triggers_count = cursor.fetchone()[0]

            print(f"\n📊 Результат восстановления:")
            print(f"   📋 Таблиц: {tables_after} (было: {tables_before})")
            print(f"   📋 Таблица cryptocurrencies: {'✅ создана' if cryptocurrencies_exists else '❌ не найдена'}")
            print(f"   🔧 Функций: {functions_count}")
            print(f"   ⚡ Триггеров: {triggers_count}")

            if cryptocurrencies_exists:
                # Показываем структуру основной таблицы
                cursor.execute("""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_name = 'cryptocurrencies' 
                    ORDER BY ordinal_position
                """)
                columns = cursor.fetchall()

                print(f"\n📋 Структура таблицы cryptocurrencies ({len(columns)} колонок):")
                for col_name, col_type in columns[:8]:  # Показываем первые 8 колонок
                    print(f"   • {col_name} ({col_type})")
                if len(columns) > 8:
                    print(f"   ... и еще {len(columns) - 8} колонок")

            cursor.close()
            conn.close()

            print("\n🎉 Восстановление завершено успешно!")
            print("💡 Теперь можно запускать парсеры:")
            print("   python3 parser.py")

        else:
            print(f"❌ Ошибка восстановления:")
            print(result.stderr)
            print("\n💡 Попробуйте выполнить вручную:")
            print(f"   docker exec -i crypto_db psql -U {DB_CONFIG['user']} -d {DB_CONFIG['database']} < init_db.sql")

    except subprocess.FileNotFoundError:
        print("❌ Docker не найден или недоступен")
        print("💡 Убедитесь, что Docker запущен и доступен")
        print("💡 Или выполните восстановление вручную:")
        print(f"   docker exec -i crypto_db psql -U {DB_CONFIG['user']} -d {DB_CONFIG['database']} < init_db.sql")

    except Exception as e:
        print(f"❌ Ошибка восстановления: {e}")
        print("💡 Попробуйте выполнить восстановление вручную")


def reinitialize_database():
    """Переинициализирует базу данных (полная очистка + восстановление структуры)"""
    print("🔄 ПЕРЕИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ")
    print("   Это действие:")
    print("   1. Удалит ВСЕ таблицы")
    print("   2. Восстановит структуру из init_db.sql")

    confirmation = input("\n❓ Продолжить? Введите 'REINIT': ")

    if confirmation != 'REINIT':
        print("❌ Операция отменена")
        return

    # Сначала удаляем все таблицы
    print("\n🗑️  Этап 1: Удаление всех таблиц...")
    drop_all_tables()

    # Затем восстанавливаем структуру
    print("\n🔧 Этап 2: Восстановление структуры...")

    if os.path.exists('init_db.sql'):
        try:
            import subprocess
            result = subprocess.run([
                'docker', 'exec', '-i', 'crypto_db',
                'psql', '-U', DB_CONFIG['user'], '-d', DB_CONFIG['database']
            ], input=open('init_db.sql', 'r').read(), text=True, capture_output=True)

            if result.returncode == 0:
                print("✅ Структура базы данных восстановлена!")
            else:
                print(f"❌ Ошибка восстановления: {result.stderr}")
        except Exception as e:
            print(f"❌ Ошибка выполнения init_db.sql: {e}")
            print("💡 Выполните вручную:")
            print(f"   docker exec -i crypto_db psql -U {DB_CONFIG['user']} -d {DB_CONFIG['database']} < init_db.sql")
    else:
        print("⚠️  Файл init_db.sql не найден")
        print("💡 Восстановите структуру вручную")


def main():
    """Главное меню"""
    print("=" * 70)
    print("🗑️  УПРАВЛЕНИЕ БАЗОЙ ДАННЫХ КРИПТОВАЛЮТ")
    print("=" * 70)

    # Показываем статистику
    show_statistics()

    print("\n📋 Выберите действие:")
    print("1. Очистка данных (сохранить структуру таблиц)")
    print("2. Очистка OHLC таблиц (удалить все OHLC таблицы)")
    print("3. ⚠️  ПОЛНОЕ УДАЛЕНИЕ ВСЕХ ТАБЛИЦ")
    print("4. 🔧 ВОССТАНОВЛЕНИЕ СТРУКТУРЫ (из init_db.sql)")
    print("5. 🔄 ПЕРЕИНИЦИАЛИЗАЦИЯ (удаление + восстановление)")
    print("6. Показать статистику")
    print("0. Выход")

    choice = input("\nВаш выбор (0-6): ")

    if choice == '1':
        clear_only_data()
    elif choice == '2':
        clear_database()
    elif choice == '3':
        drop_all_tables()
    elif choice == '4':
        restore_database()
    elif choice == '5':
        reinitialize_database()
    elif choice == '6':
        show_statistics()
    elif choice == '0':
        print("👋 Выход")
    else:
        print("❌ Неверный выбор")


if __name__ == "__main__":
    main()
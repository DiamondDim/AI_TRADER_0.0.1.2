#!/usr/bin/env python3
"""
Точка входа для AI Trader - консольная версия
"""

import sys
import os
import time
import argparse

# Добавляем путь к src в PYTHONPATH
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from ai_trader import AITrader


def interactive_menu():
    """Интерактивное меню"""
    print("=" * 60)
    print("🎯 AI TRADER MT5 - КОНСОЛЬНАЯ ВЕРСИЯ")
    print("=" * 60)
    print("1 - 📊 Показать информацию о счете")
    print("2 - 🎯 Запустить торговую стратегию")
    print("3 - 🧪 Выполнить тестовую сделку")
    print("4 - 🚫 Закрыть все позиции")
    print("5 - 🔄 Обновить данные")
    print("6 - 🎓 Обучение и торговля")
    print("7 - 🔍 Анализ рынка и предсказания")
    print("0 - 🚪 Выход")
    print("=" * 60)


def select_symbol_interactive(trader):
    """Интерактивный выбор символа из списка"""
    try:
        symbols = trader.data_fetcher.get_symbols()
        if not symbols:
            print("❌ Не удалось получить список символов")
            return None

        print("\n📊 ДОСТУПНЫЕ СИМВОЛЫ:")
        print("=" * 40)

        # Показываем символы с группировкой
        forex_symbols = [s for s in symbols if
                         any(currency in s for currency in ['USD', 'EUR', 'GBP', 'JPY', 'AUD', 'CAD', 'CHF', 'NZD'])]
        other_symbols = [s for s in symbols if s not in forex_symbols]

        if forex_symbols:
            print("\n💱 ВАЛЮТНЫЕ ПАРЫ:")
            for i, symbol in enumerate(forex_symbols[:15]):  # Показываем первые 15
                print(f"  {i + 1}. {symbol}")

        if other_symbols:
            print("\n📈 ДРУГИЕ ИНСТРУМЕНТЫ:")
            for i, symbol in enumerate(other_symbols[:10]):  # Показываем первые 10
                print(f"  {len(forex_symbols) + i + 1}. {symbol}")

        print("\n" + "=" * 40)

        while True:
            choice = input("\n🎯 Выберите символ (номер или название): ").strip()

            if choice.isdigit():
                index = int(choice) - 1
                if 0 <= index < len(symbols):
                    selected = symbols[index]
                    print(f"✅ Выбран символ: {selected}")
                    return selected
                else:
                    print("❌ Неверный номер. Попробуйте снова.")
            else:
                # Ищем символ по названию
                if choice.upper() in symbols:
                    selected = choice.upper()
                    print(f"✅ Выбран символ: {selected}")
                    return selected
                else:
                    print("❌ Символ не найден. Попробуйте снова.")

    except Exception as e:
        print(f"❌ Ошибка выбора символа: {e}")
        return None


def select_timeframe_interactive():
    """Интерактивный выбор таймфрейма"""
    timeframes = {
        '1': ('M1', '1 минута'),
        '2': ('M5', '5 минут'),
        '3': ('M15', '15 минут'),
        '4': ('M30', '30 минут'),
        '5': ('H1', '1 час'),
        '6': ('H4', '4 часа'),
        '7': ('D1', '1 день'),
        '8': ('W1', '1 неделя'),
        '9': ('MN1', '1 месяц')
    }

    print("\n⏰ ДОСТУПНЫЕ ТАЙМФРЕЙМЫ:")
    print("=" * 40)
    for key, (tf, desc) in timeframes.items():
        print(f"  {key}. {tf} - {desc}")
    print("=" * 40)

    while True:
        choice = input("\n🎯 Выберите таймфрейм (1-9): ").strip()

        if choice in timeframes:
            selected_tf = timeframes[choice][0]
            print(f"✅ Выбран таймфрейм: {selected_tf}")
            return selected_tf
        else:
            print("❌ Неверный выбор. Введите число от 1 до 9.")


def main():
    """Главная функция"""
    parser = argparse.ArgumentParser(description='AI Trader for MT5 - Console Version')
    parser.add_argument('--auto', action='store_true', help='Автоматический режим')

    args = parser.parse_args()

    trader = AITrader()

    try:
        # Инициализация
        if not trader.initialize():
            print("❌ Не удалось инициализировать AI Trader")
            sys.exit(1)

        if args.auto:
            # Автоматический режим
            print("🤖 Автоматический режим запущен")
            while True:
                try:
                    trader.run_simple_strategy(
                        trader.settings.DEFAULT_SYMBOL,
                        trader.settings.DEFAULT_TIMEFRAME
                    )
                    time.sleep(60)  # Пауза 1 минута между проверками
                except KeyboardInterrupt:
                    break
        else:
            # Интерактивный режим
            while True:
                try:
                    interactive_menu()
                    choice = input("\n🎯 Выберите действие (0-7): ").strip()

                    if choice == "1":
                        trader.show_account_info()

                    elif choice == "2":
                        # Запуск стратегии с выбором символа и таймфрейма из списка
                        symbol = select_symbol_interactive(trader)
                        if not symbol:
                            continue

                        timeframe = select_timeframe_interactive()
                        if not timeframe:
                            continue

                        trader.run_simple_strategy(symbol, timeframe)

                    elif choice == "3":
                        # Тестовая сделка с выбором символа из списка
                        symbol = select_symbol_interactive(trader)
                        if symbol:
                            trader.run_test_trade(symbol)

                    elif choice == "4":
                        # Используем новый метод для закрытия позиций
                        trader.close_all_positions_interactive()

                    elif choice == "5":
                        # Обновление данных с выбором символа из списка
                        symbol = select_symbol_interactive(trader)
                        if symbol:
                            trader.show_recent_data(symbol)

                    elif choice == "6":
                        # Новый функционал: Обучение и торговля
                        trader.training_and_trading_flow()

                    elif choice == "7":
                        # Новый пункт: Анализ рынка и предсказания
                        trader.market_analysis_flow()

                    elif choice == "0":
                        print("👋 Завершение работы...")
                        break
                    else:
                        print("❌ Неизвестная команда. Выберите число от 0 до 7.")

                    input("\n📝 Нажмите Enter для продолжения...")

                except KeyboardInterrupt:
                    print("\n🛑 Получен сигнал прерывания")
                    break
                except Exception as e:
                    print(f"💥 Ошибка: {str(e)}")

    except KeyboardInterrupt:
        print("\n🛑 Получен сигнал прерывания")
    except Exception as e:
        print(f"💥 Критическая ошибка: {str(e)}")
    finally:
        trader.shutdown()
        print("👋 AI Trader завершил работу")


if __name__ == "__main__":
    main()

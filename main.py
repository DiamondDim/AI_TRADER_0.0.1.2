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
                    choice = input("\nВыберите действие (0-7): ").strip()

                    if choice == "1":
                        trader.show_account_info()

                    elif choice == "2":
                        symbol = input(f"Символ (по умолчанию {trader.settings.DEFAULT_SYMBOL}): ").strip()
                        if not symbol:
                            symbol = trader.settings.DEFAULT_SYMBOL

                        timeframe = input(f"Таймфрейм (по умолчанию {trader.settings.DEFAULT_TIMEFRAME}): ").strip()
                        if not timeframe:
                            timeframe = trader.settings.DEFAULT_TIMEFRAME

                        trader.run_simple_strategy(symbol, timeframe)

                    elif choice == "3":
                        symbol = input(f"Символ (по умолчанию {trader.settings.DEFAULT_SYMBOL}): ").strip()
                        if not symbol:
                            symbol = trader.settings.DEFAULT_SYMBOL

                        trader.run_test_trade(symbol)

                    elif choice == "4":
                        # Используем новый метод для закрытия позиций
                        trader.close_all_positions_interactive()

                    elif choice == "5":
                        symbol = input(f"Символ (по умолчанию {trader.settings.DEFAULT_SYMBOL}): ").strip()
                        if not symbol:
                            symbol = trader.settings.DEFAULT_SYMBOL

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

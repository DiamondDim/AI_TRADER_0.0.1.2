#!/usr/bin/env python3
"""
Главный модуль AI Trader - Точка входа в приложение
"""

import os
import sys
import argparse
import logging
from datetime import datetime
from dotenv import load_dotenv

# Добавляем путь к корневой директории проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_trader import AITrader
from src.core.logger import setup_logger  # Исправленный импорт


def parse_arguments():
    """Парсинг аргументов командной строки"""
    parser = argparse.ArgumentParser(description='AI Trader - Automated Trading System')
    parser.add_argument('--strategy', type=str, help='Торговая стратегия (simple_ma, rsi, macd, bollinger, advanced)')
    parser.add_argument('--symbol', type=str, help='Торговый символ (например: EURUSD)')
    parser.add_argument('--timeframe', type=str, default='H1', help='Таймфрейм (M1, M5, H1, H4, D1)')
    parser.add_argument('--test', action='store_true', help='Запуск в тестовом режиме')
    parser.add_argument('--demo', action='store_true', help='Использовать демо-счет')
    parser.add_argument('--risk', type=float, help='Уровень риска в процентах')

    return parser.parse_args()


def show_menu():
    """Отображение главного меню"""
    print("\n" + "=" * 60)
    print("🎯 AI TRADER - ГЛАВНОЕ МЕНЮ")
    print("=" * 60)
    print("1. 📊 Показать список символов")
    print("2. 🔍 Анализ символа")
    print("3. 📈 Технический анализ")
    print("4. 💰 Торговые операции")
    print("5. 📋 Мои позиции и ордера")
    print("6. ⚙️ Настройки рисков")
    print("7. 🧪 Тестовый режим")
    print("8. 🎯 Выбор стратегии торговли")
    print("9. 📡 Мониторинг рынка в реальном времени")
    print("0. ❌ Выход")
    print("=" * 60)


def show_strategy_menu():
    """Меню выбора стратегии"""
    print("\n" + "=" * 60)
    print("🎯 ВЫБОР СТРАТЕГИИ ТОРГОВЛИ")
    print("=" * 60)
    print("1. 📈 Улучшенная MA стратегия (Средний риск)")
    print("2. 📊 Улучшенная RSI стратегия (Низкий риск)")
    print("3. 🔄 Улучшенная MACD стратегия (Средний риск)")
    print("4. 📉 Улучшенная Bollinger Bands стратегия (Высокий риск)")
    print("5. 🚀 Продвинутая мульти-стратегия (Низкий риск)")
    print("6. 📋 Показать текущую стратегию")
    print("7. 🔙 Назад в главное меню")
    print("=" * 60)


def show_realtime_monitoring_info():
    """Информация о мониторинге в реальном времени"""
    print("\n" + "=" * 60)
    print("📡 МОНИТОРИНГ РЫНКА В РЕАЛЬНОМ ВРЕМЕНИ")
    print("=" * 60)
    print("💡 Управление мониторингом:")
    print("   • Введите 'stop' - остановить мониторинг")
    print("   • Введите 'status' - показать статус")
    print("   • Введите 'summary' - показать сводку рынка")
    print("   • Введите 'symbols' - показать отслеживаемые символы")
    print("   • Введите 'exit' - вернуться в меню")
    print("=" * 60)
    print("🔄 Мониторинг автоматически обновляет данные каждые 5 секунд")
    print("📊 Отслеживаются изменения цен, объемы и технические индикаторы")
    print("🎯 Система определяет общее состояние рынка (Бычье/Медвежье/Боковое)")
    print("=" * 60)


def main():
    """Главная функция приложения"""
    # Загрузка переменных окружения
    load_dotenv()

    # Настройка логирования
    setup_logger()
    logger = logging.getLogger('AITrader')

    # Парсинг аргументов командной строки
    args = parse_arguments()

    try:
        # Инициализация AI Trader
        logger.info("🚀 Инициализация AI Trader...")
        trader = AITrader()

        if not trader.initialize():
            logger.error("❌ Не удалось инициализировать AI Trader")
            return

        # Применение аргументов командной строки
        if args.strategy:
            if trader.set_strategy(args.strategy):
                logger.info(f"✅ Стратегия установлена: {args.strategy}")
            else:
                logger.error(f"❌ Не удалось установить стратегию: {args.strategy}")

        if args.risk:
            trader.update_risk_management(args.risk)
            logger.info(f"✅ Уровень риска установлен: {args.risk}%")

        # Запуск в тестовом режиме если указан аргумент
        if args.test:
            logger.info("🧪 Запуск в тестовом режиме...")
            if args.symbol:
                trader.run_simple_strategy(args.symbol, args.timeframe)
            else:
                trader.test_strategy_flow()
            return

        # Основной цикл меню
        while True:
            show_menu()
            choice = input("\n📝 Выберите пункт меню: ").strip()

            if choice == '0':
                print("\n👋 До свидания!")
                break

            elif choice == '1':
                # Показать список символов
                print("\n📊 ЗАГРУЗКА СПИСКА СИМВОЛОВ...")
                trader.show_available_symbols()

            elif choice == '2':
                # Анализ символа
                print("\n🔍 АНАЛИЗ СИМВОЛА")
                symbol = input("Введите символ для анализа (например: EURUSD): ").strip()
                if symbol:
                    trader.analyze_symbol(symbol)
                else:
                    print("❌ Не указан символ для анализа")

            elif choice == '3':
                # Технический анализ
                print("\n📈 ТЕХНИЧЕСКИЙ АНАЛИЗ")
                symbol = input("Введите символ для анализа: ").strip()
                if symbol:
                    timeframe = input("Введите таймфрейм (M1, M5, H1, H4, D1) [H1]: ").strip() or 'H1'
                    trader.technical_analysis_flow(symbol, timeframe)
                else:
                    print("❌ Не указан символ для анализа")

            elif choice == '4':
                # Торговые операции
                print("\n💰 ТОРГОВЫЕ ОПЕРАЦИИ")
                trader.trading_operations_flow()

            elif choice == '5':
                # Мои позиции и ордера
                print("\n📋 МОИ ПОЗИЦИИ И ОРДЕРА")
                trader.show_positions_and_orders()

            elif choice == '6':
                # Настройки рисков
                print("\n⚙️ НАСТРОЙКИ УПРАВЛЕНИЯ РИСКАМИ")
                try:
                    risk_percent = float(input("Введите уровень риска в % (например: 1.0): "))
                    trader.update_risk_management(risk_percent)
                    print(f"✅ Уровень риска установлен: {risk_percent}%")
                except ValueError:
                    print("❌ Неверное значение риска")

            elif choice == '7':
                # Тестовый режим
                print("\n🧪 ТЕСТОВЫЙ РЕЖИМ")
                trader.test_strategy_flow()

            elif choice == '8':
                # Выбор стратегии торговли
                strategy_menu_loop(trader)

            elif choice == '9':
                # Мониторинг рынка в реальном времени
                print("\n📡 ЗАПУСК МОНИТОРИНГА РЫНКА...")
                show_realtime_monitoring_info()
                trader.real_time_monitoring_flow()

            else:
                print("❌ Неверный выбор. Попробуйте снова.")

            input("\n↵ Нажмите Enter для продолжения...")

    except KeyboardInterrupt:
        print("\n\n⚠️ Приложение прервано пользователем")
        logger.info("Приложение прервано пользователем (Ctrl+C)")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка в приложении: {e}")
        print(f"\n❌ Произошла критическая ошибка: {e}")
    finally:
        # Гарантированное завершение
        try:
            if 'trader' in locals():
                trader.shutdown()
                logger.info("✅ AI Trader завершил работу")
        except Exception as e:
            logger.error(f"❌ Ошибка при завершении работы: {e}")


def strategy_menu_loop(trader):
    """Цикл меню выбора стратегии"""
    while True:
        show_strategy_menu()
        choice = input("\n📝 Выберите стратегию: ").strip()

        if choice == '1':
            if trader.set_strategy('simple_ma'):
                print("✅ Установлена Улучшенная MA стратегия")
            else:
                print("❌ Ошибка установки стратегии")

        elif choice == '2':
            if trader.set_strategy('rsi'):
                print("✅ Установлена Улучшенная RSI стратегия")
            else:
                print("❌ Ошибка установки стратегии")

        elif choice == '3':
            if trader.set_strategy('macd'):
                print("✅ Установлена Улучшенная MACD стратегия")
            else:
                print("❌ Ошибка установки стратегии")

        elif choice == '4':
            if trader.set_strategy('bollinger'):
                print("✅ Установлена Улучшенная Bollinger Bands стратегия")
            else:
                print("❌ Ошибка установки стратегии")

        elif choice == '5':
            if trader.set_strategy('advanced'):
                print("✅ Установлена Продвинутая мульти-стратегия")
            else:
                print("❌ Ошибка установки стратегии")

        elif choice == '6':
            # Показать текущую стратегию
            current_strategy = trader.get_current_strategy()
            if current_strategy:
                print(f"\n📋 ТЕКУЩАЯ СТРАТЕГИЯ: {current_strategy['name']}")
                print(f"📝 Описание: {current_strategy['description']}")
                print(f"⚡ Уровень риска: {current_strategy['risk_level']}")
            else:
                print("❌ Стратегия не установлена")

        elif choice == '7':
            break

        else:
            print("❌ Неверный выбор. Попробуйте снова.")

        input("\n↵ Нажмите Enter для продолжения...")


if __name__ == "__main__":
    print("🚀 AI TRADER - Automated Trading System")
    print("📅 Запуск:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("🔒 Версия: AI Trader 1.2.0")
    print("📊 Статус: PRODUCTION READY 🟢")
    print("\n" + "=" * 50)

    main()

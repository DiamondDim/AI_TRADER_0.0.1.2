#!/usr/bin/env python3
"""
Главный класс AI Trader для MT5
"""

import sys
import os
import time
import argparse
import logging
from datetime import datetime, timedelta
import MetaTrader5 as mt5
import pandas as pd
from typing import Tuple, Optional, List

# Добавляем путь к src в PYTHONPATH
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

try:
    # Пробуем импортировать из src.core
    from src.core import MT5, DataFetcher, Trader, setup_logger, Settings
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("💡 Проверьте структуру проекта:")
    print("   - Файл src/core/__init__.py должен существовать")
    print("   - Все модули в src/core/ должны быть доступны")
    sys.exit(1)


class AITrader:
    """Основной класс AI Trader"""

    def __init__(self):
        self.logger = setup_logger('AITrader')
        self.settings = Settings()
        self.mt5 = None
        self.data_fetcher = None
        self.trader = None
        self.running = False
        self.market_available = False

    def check_market_availability(self) -> Tuple[bool, str]:
        """
        Проверяет доступность рынка для торговли с учетом реальных символов

        Returns:
            Tuple[bool, str]: (Доступен ли рынок, Сообщение)
        """
        try:
            self.logger.info("🔍 Проверка доступности рынка...")

            # Проверяем соединение с MT5
            if not self.mt5.check_connection():
                return False, "Нет соединения с MT5"

            # Получаем реальные символы из терминала
            all_symbols = mt5.symbols_get()
            if not all_symbols:
                return False, "Не удалось получить список символов от MT5"

            # Берем первые 10 символов для проверки
            test_symbols = [symbol.name for symbol in all_symbols[:10]]
            active_symbols = []

            for symbol in test_symbols:
                try:
                    # Проверяем информацию о символе
                    symbol_info = mt5.symbol_info(symbol)
                    if symbol_info is None:
                        continue

                    # Проверяем, доступен ли символ для торговли
                    if symbol_info.visible and symbol_info.trade_mode in [mt5.SYMBOL_TRADE_MODE_FULL,
                                                                          mt5.SYMBOL_TRADE_MODE_CLOSEONLY]:
                        # Пробуем получить котировки разными способами
                        tick = mt5.symbol_info_tick(symbol)

                        if tick is not None:
                            # Проверяем время последнего обновления котировок
                            tick_time = datetime.fromtimestamp(tick.time)
                            time_diff = datetime.now() - tick_time

                            # Если котировки обновлялись не более 5 минут назад - рынок активен
                            if time_diff.total_seconds() <= 300:  # 5 минут
                                active_symbols.append(symbol)
                                self.logger.debug(
                                    f"✅ Символ {symbol} активен (обновлен {time_diff.total_seconds():.0f} сек назад)")
                            else:
                                self.logger.warning(
                                    f"⚠️ Символ {symbol} не обновлялся {time_diff.total_seconds():.0f} сек")
                        else:
                            # Пробуем другой метод получения данных
                            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 1)
                            if rates is not None and len(rates) > 0:
                                active_symbols.append(symbol)
                                self.logger.debug(f"✅ Символ {symbol} доступен через исторические данные")
                            else:
                                self.logger.warning(f"⚠️ Не удалось получить котировки для {symbol}")
                    else:
                        self.logger.warning(f"⚠️ Символ {symbol} недоступен для торговли")

                except Exception as e:
                    self.logger.warning(f"⚠️ Ошибка проверки символа {symbol}: {str(e)}")
                    continue

            # Если есть хотя бы один активный символ - рынок доступен
            if active_symbols:
                self.market_available = True
                message = f"✅ Рынок доступен для торговли. Активные символы: {', '.join(active_symbols[:3])}"
                self.logger.info(message)
                return True, message
            else:
                self.market_available = False
                message = "⚠️ Внимание: Не удалось получить актуальные котировки. Проверьте подключение к рынку."
                self.logger.warning(message)
                return False, message

        except Exception as e:
            error_msg = f"⚠️ Ошибка проверки рынка: {str(e)}"
            self.logger.warning(error_msg)
            # В случае ошибки предполагаем, что рынок доступен, но с ограничениями
            self.market_available = True
            return True, error_msg

    def initialize(self) -> bool:
        """Инициализация приложения"""
        try:
            self.logger.info("🚀 Инициализация AI Trader...")

            # Проверяем настройки
            try:
                self.settings.validate()
                self.logger.info("✅ Настройки проверены")
                self.logger.info(f"⚙️ Текущие настройки:\n{self.settings.print_settings()}")
            except ValueError as e:
                self.logger.error(f"❌ Ошибка настроек: {e}")
                self.logger.info("💡 Пожалуйста, настройте .env файл с правильными параметрами")
                return False

            # Инициализируем MT5
            self.mt5 = MT5()
            success, message = self.mt5.initialize(
                path=self.settings.MT5_PATH,
                login=self.settings.MT5_LOGIN,
                password=self.settings.MT5_PASSWORD,
                server=self.settings.MT5_SERVER
            )

            if not success:
                self.logger.error(f"❌ Ошибка инициализации MT5: {message}")
                return False

            # Проверяем доступность рынка (но не блокируем запуск при ошибках)
            market_ok, market_message = self.check_market_availability()
            if not market_ok:
                self.logger.warning(
                    "⚠️ Внимание: Проблемы с доступом к рынку. Некоторые функции могут быть ограничены.")
            else:
                self.logger.info("🎯 Рынок доступен. Торговля возможна.")

            # Инициализируем компоненты
            self.data_fetcher = DataFetcher(self.mt5)
            self.trader = Trader(self.mt5)

            self.logger.info("✅ AI Trader успешно инициализирован")
            return True

        except Exception as e:
            self.logger.error(f"💥 Критическая ошибка инициализации: {str(e)}")
            return False

    def select_symbol(self) -> Optional[str]:
        """Выбор символа из доступных"""
        try:
            symbols = self.data_fetcher.get_symbols()
            if not symbols:
                self.logger.error("❌ Не удалось получить список символов")
                return None

            print("\n📊 Доступные символы:")
            for i, symbol in enumerate(symbols[:20]):  # Показываем первые 20
                print(f"{i + 1}. {symbol}")

            while True:
                choice = input("\nВыберите символ (номер или название): ").strip()
                if choice.isdigit():
                    index = int(choice) - 1
                    if 0 <= index < len(symbols):
                        return symbols[index]
                    else:
                        print("❌ Неверный номер. Попробуйте снова.")
                else:
                    if choice in symbols:
                        return choice
                    else:
                        print("❌ Символ не найден. Попробуйте снова.")
        except Exception as e:
            self.logger.error(f"❌ Ошибка выбора символа: {e}")
            return None

    def select_timeframe(self) -> Optional[str]:
        """Выбор таймфрейма"""
        try:
            timeframes = ['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1', 'W1', 'MN1']
            print("\n⏰ Доступные таймфреймы:")
            for i, tf in enumerate(timeframes):
                print(f"{i + 1}. {tf}")

            while True:
                choice = input("\nВыберите таймфрейм (номер или название): ").strip()
                if choice.isdigit():
                    index = int(choice) - 1
                    if 0 <= index < len(timeframes):
                        return timeframes[index]
                    else:
                        print("❌ Неверный номер. Попробуйте снова.")
                else:
                    choice_upper = choice.upper()
                    if choice_upper in timeframes:
                        return choice_upper
                    else:
                        print("❌ Таймфрейм не найден. Попробуйте снова.")
        except Exception as e:
            self.logger.error(f"❌ Ошибка выбора таймфрейма: {e}")
            return None

    def run_training(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """Обучение на исторических данных за 5-6 недель"""
        try:
            self.logger.info(f"🎓 Начало обучения для {symbol} {timeframe}")

            # Проверяем доступность рынка для информационных целей
            if not self.market_available:
                self.logger.warning("⚠️ Рынок недоступен. Обучение может быть неточным.")

            # Рассчитываем дату 6 недель назад
            end_date = datetime.now()
            start_date = end_date - timedelta(weeks=6)

            # Получаем исторические данные
            data = self.data_fetcher.get_rates(symbol, timeframe, start_date=start_date, end_date=end_date)
            if data is None or data.empty:
                self.logger.error("❌ Не удалось получить данные для обучения")
                return None

            # Рассчитываем индикаторы
            data = self.data_fetcher.calculate_technical_indicators(data)

            # Анализируем данные
            analysis = self.analyze_training_data(data)

            self.logger.info(f"✅ Обучение завершено. Получено {len(data)} баров")
            self.logger.info(f"📈 Анализ: {analysis}")

            return data

        except Exception as e:
            self.logger.error(f"❌ Ошибка обучения: {e}")
            return None

    def analyze_training_data(self, data: pd.DataFrame) -> str:
        """Анализ обучающих данных"""
        try:
            # Базовая статистика
            if 'range' in data.columns:
                volatility = data['range'].mean()
            else:
                # Если колонки range нет, вычисляем волатильность как разницу High-Low
                data['range'] = data['high'] - data['low']
                volatility = data['range'].mean()

            avg_volume = data['tick_volume'].mean() if 'tick_volume' in data.columns else 0
            trend = "ВОСХОДЯЩИЙ" if data['close'].iloc[-1] > data['close'].iloc[0] else "НИСХОДЯЩИЙ"

            # Анализ индикаторов
            rsi_current = data['rsi'].iloc[-1] if 'rsi' in data.columns else 50
            rsi_signal = "ПЕРЕПРОДАН" if rsi_current < 30 else "ПЕРЕКУПЛЕН" if rsi_current > 70 else "НЕЙТРАЛЬНЫЙ"

            return f"Тренд: {trend}, Волатильность: {volatility:.5f}, RSI: {rsi_signal} ({rsi_current:.1f})"

        except Exception as e:
            return f"Анализ не удался: {str(e)}"

    def training_completion_menu(self, symbol: str, timeframe: str, model: pd.DataFrame):
        """Меню после завершения обучения"""
        while True:
            print("\n" + "=" * 50)
            print("🎓 ОБУЧЕНИЕ ЗАВЕРШЕНО")
            print("=" * 50)
            print("1 - 🧪 Начать тестовую торговлю")
            print("2 - 🎯 Начать реальную торговлю")
            print("3 - 🔙 Вернуться в главное меню")

            choice = input("\nВыберите действие: ").strip()

            if choice == "1":
                self.run_test_trading(symbol, timeframe, model)
            elif choice == "2":
                self.run_real_trading(symbol, timeframe, model)
            elif choice == "3":
                break
            else:
                print("❌ Неизвестная команда")

    def run_test_trading(self, symbol: str, timeframe: str, model: pd.DataFrame):
        """Тестовая торговля с сохранением логов"""
        try:
            self.logger.info(f"🧪 Начало тестовой торговли для {symbol} {timeframe}")

            # Создаем папку для логов тестов если ее нет
            log_dir = "Log_tests_sell"
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)

            # Создаем лог-файл с timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = os.path.join(log_dir, f"test_trading_{symbol}_{timestamp}.log")

            # Настраиваем логгер для тестовой торговли
            test_logger = logging.getLogger(f'TestTrading_{symbol}_{timestamp}')
            test_logger.setLevel(logging.INFO)
            test_logger.handlers = []  # Очищаем существующие обработчики

            # Файловый обработчик
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(formatter)
            test_logger.addHandler(file_handler)

            test_logger.info("=" * 60)
            test_logger.info(f"🧪 ТЕСТОВАЯ ТОРГОВЛЯ - {symbol} {timeframe}")
            test_logger.info("=" * 60)
            test_logger.info(f"Модель обучена на {len(model) if model is not None else 0} барах")
            test_logger.info(f"Начало: {datetime.now()}")

            # Проверяем доступность рынка для информационных целей
            if not self.market_available:
                test_logger.warning("⚠️ ВНИМАНИЕ: Рынок недоступен. Это тестовая симуляция.")

            # Симуляция торговли
            success = self.simulate_trading(symbol, timeframe, test_logger)

            test_logger.info(f"Завершение: {datetime.now()}")
            test_logger.info(f"Результат: {'УСПЕХ' if success else 'ОШИБКА'}")
            test_logger.info("=" * 60)

            # Удаляем обработчик, чтобы закрыть файл
            for handler in test_logger.handlers[:]:
                handler.close()
                test_logger.removeHandler(handler)

            self.logger.info(f"✅ Тестовая торговля завершена. Логи сохранены в {log_file}")

        except Exception as e:
            self.logger.error(f"❌ Ошибка тестовой торговли: {e}")

    def simulate_trading(self, symbol: str, timeframe: str, test_logger: logging.Logger) -> bool:
        """Симуляция торговли для тестов"""
        try:
            # Получаем текущие данные
            data = self.data_fetcher.get_rates(symbol, timeframe, count=50)
            if data is None or data.empty:
                test_logger.error("❌ Не удалось получить данные для тестирования")
                return False

            # Применяем стратегию - ИСПРАВЛЕНИЕ ОШИБКИ С DataFrame
            signal = self._simple_moving_average_strategy(data)

            # Логируем решение
            current_price = self.data_fetcher.get_current_price(symbol)
            if current_price and isinstance(current_price, dict):
                test_logger.info(
                    f"💰 Текущая цена: Bid={current_price.get('bid', 0):.5f}, Ask={current_price.get('ask', 0):.5f}")
            else:
                test_logger.warning("⚠️ Не удалось получить текущую цену")

            # Гарантируем, что signal - строка
            if not isinstance(signal, str):
                signal = "HOLD"
                test_logger.warning("⚠️ Сигнал не является строкой, установлен в HOLD")

            test_logger.info(f"🎯 Сигнал: {signal}")

            # Симуляция ордеров
            if signal == "BUY":
                test_logger.info("📈 СИМУЛЯЦИЯ: Открытие BUY ордера")
                test_logger.info("💡 Объем: 0.01 лота")
                test_logger.info("🛡️ Stop Loss: -50 пунктов")
                test_logger.info("🎯 Take Profit: +100 пунктов")

            elif signal == "SELL":
                test_logger.info("📉 СИМУЛЯЦИЯ: Открытие SELL ордера")
                test_logger.info("💡 Объем: 0.01 лота")
                test_logger.info("🛡️ Stop Loss: -50 пунктов")
                test_logger.info("🎯 Take Profit: +100 пунктов")

            else:
                test_logger.info("⚖️ СИМУЛЯЦИЯ: Удержание позиции")

            return True

        except Exception as e:
            test_logger.error(f"❌ Ошибка симуляции: {str(e)}")
            return False

    def run_real_trading(self, symbol: str, timeframe: str, model: pd.DataFrame):
        """Реальная торговля"""
        try:
            # Проверяем доступность рынка перед реальной торговлей
            if not self.market_available:
                self.logger.error("❌ Реальная торговля невозможна: рынок недоступен")
                return

            self.logger.info(f"🎯 Начало реальной торговли для {symbol} {timeframe}")

            # Запускаем стратегию в реальном режиме
            self.run_simple_strategy(symbol, timeframe)

        except Exception as e:
            self.logger.error(f"❌ Ошибка реальной торговли: {e}")

    def show_account_info(self):
        """Показывает информацию об аккаунте"""
        try:
            account_info = self.mt5.get_account_info()
            if account_info:
                self.logger.info("=" * 50)
                self.logger.info("📊 ИНФОРМАЦИЯ О СЧЕТЕ")
                self.logger.info("=" * 50)
                self.logger.info(f"👤 Логин: {account_info.get('login', 'N/A')}")
                self.logger.info(f"🏢 Брокер: {account_info.get('company', 'N/A')}")
                self.logger.info(f"💳 Баланс: {account_info.get('balance', 0):.2f} {account_info.get('currency', '')}")
                self.logger.info(f"📈 Эквити: {account_info.get('equity', 0):.2f} {account_info.get('currency', '')}")
                self.logger.info(
                    f"🆓 Свободная маржа: {account_info.get('free_margin', 0):.2f} {account_info.get('currency', '')}")
                self.logger.info(f"⚖️ Кредитное плечо: 1:{account_info.get('leverage', 0)}")
                self.logger.info(f"🌐 Сервер: {account_info.get('server', 'N/A')}")

            # Показываем открытые позиции
            positions = self.trader.get_open_positions()
            if positions:
                self.logger.info("=" * 50)
                self.logger.info(f"📋 ОТКРЫТЫЕ ПОЗИЦИИ ({len(positions)})")
                self.logger.info("=" * 50)
                total_profit = 0
                for pos in positions:
                    profit = pos.get('profit', 0) + pos.get('swap', 0)
                    total_profit += profit
                    status = "🟢" if profit >= 0 else "🔴"
                    self.logger.info(
                        f"{status} {pos.get('symbol', 'N/A')} {pos.get('type', 'N/A')} {pos.get('volume', 0)} лот(ов) | "
                        f"Цена: {pos.get('open_price', 0):.5f} | Прибыль: {profit:.2f}"
                    )
                self.logger.info(f"💰 Общая прибыль: {total_profit:.2f}")
            else:
                self.logger.info("📭 Нет открытых позиций")

        except Exception as e:
            self.logger.error(f"Ошибка получения информации об аккаунте: {str(e)}")

    def run_simple_strategy(self, symbol: str, timeframe: str):
        """Запускает простую торговую стратегию (пример)"""
        try:
            # Проверяем доступность рынка перед торговлей
            if not self.market_available:
                self.logger.error(f"❌ Торговля невозможна: рынок недоступен для {symbol}")
                return

            self.logger.info(f"🎯 Запуск стратегии для {symbol} {timeframe}")

            # Получаем исторические данные
            data = self.data_fetcher.get_rates(symbol, timeframe, count=100)
            if data is None or data.empty:
                self.logger.error("❌ Не удалось получить данные")
                return

            # Простая стратегия на основе скользящих средних
            signal = self._simple_moving_average_strategy(data)

            if signal == "BUY":
                self.logger.info(f"📈 Сигнал BUY для {symbol}")
                # Рассчитываем объем на основе риска
                volume = self.trader.calculate_position_size(
                    symbol,
                    risk_percent=self.settings.RISK_PERCENT,
                    stop_loss_pips=self.settings.STOPLOSS_PIPS
                )

                if volume:
                    # Отправляем ордер
                    sl = self.settings.STOPLOSS_PIPS if self.settings.ENABLE_STOPLOSS else 0.0
                    tp = self.settings.TAKEPROFIT_PIPS if self.settings.ENABLE_TAKEPROFIT else 0.0

                    success, message = self.trader.send_order(
                        symbol=symbol,
                        order_type='buy',
                        volume=volume,
                        stop_loss=sl,
                        take_profit=tp,
                        comment="AI Simple Strategy"
                    )
                    if success:
                        self.logger.info(f"✅ {message}")
                    else:
                        self.logger.error(f"❌ {message}")

            elif signal == "SELL":
                self.logger.info(f"📉 Сигнал SELL для {symbol}")
                # Рассчитываем объем на основе риска
                volume = self.trader.calculate_position_size(
                    symbol,
                    risk_percent=self.settings.RISK_PERCENT,
                    stop_loss_pips=self.settings.STOPLOSS_PIPS
                )

                if volume:
                    # Отправляем ордер
                    sl = self.settings.STOPLOSS_PIPS if self.settings.ENABLE_STOPLOSS else 0.0
                    tp = self.settings.TAKEPROFIT_PIPS if self.settings.ENABLE_TAKEPROFIT else 0.0

                    success, message = self.trader.send_order(
                        symbol=symbol,
                        order_type='sell',
                        volume=volume,
                        stop_loss=sl,
                        take_profit=tp,
                        comment="AI Simple Strategy"
                    )
                    if success:
                        self.logger.info(f"✅ {message}")
                    else:
                        self.logger.error(f"❌ {message}")
            else:
                self.logger.info(f"⚖️ Нет сигнала для {symbol}")

        except Exception as e:
            self.logger.error(f"💥 Ошибка в стратегии: {str(e)}")

    def _simple_moving_average_strategy(self, data: pd.DataFrame, short_window: int = 10, long_window: int = 30) -> str:
        """Простая стратегия на скользящих средних с исправлением ошибок"""
        try:
            # Проверяем, что данных достаточно
            if len(data) < long_window:
                return "HOLD"

            # Вычисляем скользящие средние
            data['sma_short'] = data['close'].rolling(window=short_window).mean()
            data['sma_long'] = data['close'].rolling(window=long_window).mean()

            # Проверяем, что у нас есть достаточно данных для сравнения
            if len(data) < 2 or data['sma_short'].isna().iloc[-1] or data['sma_long'].isna().iloc[-1]:
                return "HOLD"

            # Получаем последние значения
            current_short = data['sma_short'].iloc[-1]
            current_long = data['sma_long'].iloc[-1]
            previous_short = data['sma_short'].iloc[-2]
            previous_long = data['sma_long'].iloc[-2]

            # Сигнал на покупку: короткая MA пересекает длинную снизу вверх
            if previous_short <= previous_long and current_short > current_long:
                return "BUY"

            # Сигнал на продажу: короткая MA пересекает длинную сверху вниз
            if previous_short >= previous_long and current_short < current_long:
                return "SELL"

            return "HOLD"

        except Exception as e:
            self.logger.error(f"Ошибка в стратегии MA: {str(e)}")
            return "HOLD"

    def run_test_trade(self, symbol: str):
        """Выполняет тестовую сделку"""
        try:
            # Проверяем доступность рынка перед тестовой сделкой
            if not self.market_available:
                self.logger.error(f"❌ Тестовая сделка невозможна: рынок недоступен для {symbol}")
                return

            self.logger.info(f"🧪 Тестовая сделка для {symbol}")

            # Используем минимальный объем для теста
            symbol_info = self.data_fetcher.get_symbol_info(symbol)
            if symbol_info:
                volume = symbol_info.get('volume_min', 0.01)
            else:
                volume = 0.01

            success, message = self.trader.send_order(
                symbol=symbol,
                order_type='buy',
                volume=volume,
                comment="Test Order"
            )

            if success:
                self.logger.info(f"✅ Тестовая сделка успешна: {message}")

                # Закрываем тестовую сделку через 5 секунд
                time.sleep(5)
                positions = self.trader.get_open_positions(symbol)
                for position in positions:
                    if position.get('volume', 0) == volume:
                        self.trader.close_position(position.get('ticket'))
                        break
            else:
                self.logger.error(f"❌ Тестовая сделка не удалась: {message}")

        except Exception as e:
            self.logger.error(f"💥 Ошибка тестовой сделки: {str(e)}")

    def close_all_positions_interactive(self):
        """Закрывает все открытые позиции с интерактивным вводом"""
        try:
            symbol = input("Символ (оставьте пустым для всех): ").strip()
            if not symbol:
                symbol = ""

            # Получаем открытые позиции
            positions = self.trader.get_open_positions(symbol)
            if not positions:
                self.logger.info("📝 Нет открытых позиций для закрытия")
                return

            self.logger.info(f"📋 Найдено {len(positions)} позиций для закрытия")

            # Закрываем все позиции
            success, message = self.trader.close_all_positions(symbol)
            if success:
                self.logger.info(f"✅ {message}")
            else:
                self.logger.error(f"❌ {message}")

        except Exception as e:
            self.logger.error(f"❌ Ошибка при закрытии позиций: {e}")

    def show_recent_data(self, symbol: str):
        """Показывает последние данные по символу"""
        try:
            data = self.data_fetcher.get_rates(symbol, self.settings.DEFAULT_TIMEFRAME, count=10)
            if data is None or data.empty:
                self.logger.error("❌ Не удалось получить данные")
                return

            print(f"\n📈 Последние 10 баров для {symbol}:")
            print(data[['open', 'high', 'low', 'close']].tail(5))
        except Exception as e:
            self.logger.error(f"❌ Ошибка при получении данных: {e}")

    def training_and_trading_flow(self):
        """Полный цикл обучения и торговли"""
        try:
            symbol = self.select_symbol()
            if not symbol:
                return

            timeframe = self.select_timeframe()
            if not timeframe:
                return

            # Обучение
            model = self.run_training(symbol, timeframe)
            if model is not None:
                self.training_completion_menu(symbol, timeframe, model)
        except Exception as e:
            self.logger.error(f"❌ Ошибка в цикле обучения и торговли: {e}")

    def shutdown(self):
        """Корректное завершение работы"""
        self.logger.info("🛑 Завершение работы AI Trader...")
        if self.mt5:
            self.mt5.shutdown()
        self.logger.info("👋 AI Trader остановлен")


def main():
    """Главная функция"""
    parser = argparse.ArgumentParser(description='AI Trader for MT5')
    parser.add_argument('--symbol', type=str, default=None, help='Торговый символ')
    parser.add_argument('--timeframe', type=str, default='H1', help='Таймфрейм')
    parser.add_argument('--strategy', action='store_true', help='Запустить стратегию один раз')
    parser.add_argument('--test', action='store_true', help='Выполнить тестовую сделку')
    parser.add_argument('--info', action='store_true', help='Показать информацию о счете')

    args = parser.parse_args()

    trader = AITrader()

    try:
        # Инициализация
        if not trader.initialize():
            sys.exit(1)

        # Определяем символ по умолчанию если не указан
        symbol = args.symbol if args.symbol else trader.settings.DEFAULT_SYMBOL

        if args.info:
            # Показать информацию о счете
            trader.show_account_info()

        elif args.test:
            # Тестовая сделка
            trader.run_test_trade(symbol)

        elif args.strategy:
            # Запуск стратегии один раз
            trader.run_simple_strategy(symbol, args.timeframe)

        else:
            # Интерактивный режим
            print("🤖 Используйте 'python main.py' для интерактивного режима")
            print("📋 Доступные команды:")
            print("  python main.py --info")
            print("  python main.py --test --symbol EURUSD")
            print("  python main.py --strategy --symbol EURUSD --timeframe H1")

    except KeyboardInterrupt:
        trader.logger.info("🛑 Получен сигнал прерывания")
    except Exception as e:
        trader.logger.error(f"💥 Критическая ошибка: {str(e)}")
    finally:
        trader.shutdown()


if __name__ == "__main__":
    main()

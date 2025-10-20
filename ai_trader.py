#!/usr/bin/env python3
"""
Главный класс AI Trader для MT5
"""

import sys
import os
import time
import argparse
import logging
import numpy as np
from datetime import datetime, timedelta
import MetaTrader5 as mt5
import pandas as pd
from typing import Tuple, Optional, List, Dict

# Добавляем путь к src в PYTHONPATH
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

try:
    # Пробуем импортировать из src.core
    from src.core import (
        MT5, DataFetcher, Trader, setup_logger, Settings,
        get_available_strategies, create_strategy, TradingStrategy,
        RealTimeMonitor  # НОВЫЙ ИМПОРТ
    )
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
        self.realtime_monitor = None  # НОВЫЙ АТРИБУТ
        self.running = False
        self.market_available = False
        self.current_strategy = None
        self.available_strategies = get_available_strategies()
        self.monitoring_symbols = []  # НОВЫЙ АТРИБУТ

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

            # Инициализируем монитор реального времени
            self.realtime_monitor = RealTimeMonitor(self.data_fetcher)
            # Подписываемся на обновления рынка
            self.realtime_monitor.subscribe(self._on_market_update)

            # Устанавливаем стратегию по умолчанию
            self.set_strategy('simple_ma')

            self.logger.info("✅ AI Trader успешно инициализирован")
            return True

        except Exception as e:
            self.logger.error(f"💥 Критическая ошибка инициализации: {str(e)}")
            return False

    def _on_market_update(self, market_data: Dict[str, any]):
        """Обработчик обновлений рынка в реальном времени"""
        try:
            # Логируем важные изменения
            for symbol, data in market_data['symbols'].items():
                change = data.get('price_change', 0)
                if abs(change) > 0.5:  # Значительное изменение
                    self.logger.info(f"📊 {symbol}: изменение {change:.2f}%")

            # Автоматическая торговля на основе реальных данных (если включена)
            if getattr(self.settings, 'AUTO_TRADING_ENABLED', False):
                self._process_real_time_signals(market_data)

        except Exception as e:
            self.logger.error(f"❌ Ошибка обработки обновления рынка: {e}")

    def _process_real_time_signals(self, market_data: Dict[str, any]):
        """Обработка сигналов в реальном времени"""
        try:
            for symbol, data in market_data['symbols'].items():
                # Получаем данные для анализа
                historical_data = self.data_fetcher.get_rates(symbol, 'M5', count=100)
                if historical_data is None or historical_data.empty:
                    continue

                # Применяем текущую стратегию
                historical_data = self.calculate_advanced_indicators(historical_data)
                signal_info = self.current_strategy.generate_signal(historical_data)

                # Если сильный сигнал - выполняем сделку
                if signal_info.get('strength', 0) > 70:
                    signal = signal_info.get('signal', 'HOLD')
                    if signal in ['BUY', 'SELL']:
                        self.logger.info(f"🎯 Реальный сигнал {signal} для {symbol} (сила: {signal_info['strength']}%)")
                        self._execute_trade(symbol, signal.lower(), signal_info['strength'])

        except Exception as e:
            self.logger.error(f"❌ Ошибка обработки сигналов реального времени: {e}")

    def set_strategy(self, strategy_id: str) -> bool:
        """Установка торговой стратегии"""
        try:
            if strategy_id not in self.available_strategies:
                self.logger.error(f"❌ Стратегия '{strategy_id}' не найдена")
                return False

            self.current_strategy = create_strategy(strategy_id)
            self.logger.info(f"🎯 Установлена стратегия: {self.current_strategy.name}")
            self.logger.info(f"📝 Описание: {self.current_strategy.description}")
            return True

        except Exception as e:
            self.logger.error(f"❌ Ошибка установки стратегии: {e}")
            return False

    def select_strategy(self) -> Optional[str]:
        """Выбор стратегии из доступных"""
        try:
            strategies = self.available_strategies
            if not strategies:
                self.logger.error("❌ Не удалось получить список стратегий")
                return None

            print("\n🎯 ДОСТУПНЫЕ СТРАТЕГИИ:")
            print("=" * 50)
            for i, (strategy_id, strategy_name) in enumerate(strategies.items(), 1):
                print(f"{i}. {strategy_name} ({strategy_id})")

            print("=" * 50)

            while True:
                choice = input("\n🎯 Выберите стратегию (номер или идентификатор): ").strip()

                if choice.isdigit():
                    index = int(choice) - 1
                    strategy_ids = list(strategies.keys())
                    if 0 <= index < len(strategy_ids):
                        selected_id = strategy_ids[index]
                        print(f"✅ Выбрана стратегия: {strategies[selected_id]}")
                        return selected_id
                    else:
                        print("❌ Неверный номер. Попробуйте снова.")
                else:
                    if choice in strategies:
                        print(f"✅ Выбрана стратегия: {strategies[choice]}")
                        return choice
                    else:
                        print("❌ Стратегия не найдена. Попробуйте снова.")

        except Exception as e:
            self.logger.error(f"❌ Ошибка выбора стратегии: {e}")
            return None

    def calculate_advanced_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Расчет расширенных технических индикаторов с учетом выбранной стратегии
        """
        try:
            if self.current_strategy:
                # Используем индикаторы выбранной стратегии
                data = self.current_strategy.calculate_indicators(data)
                self.logger.info(f"✅ Индикаторы стратегии '{self.current_strategy.name}' рассчитаны")
            else:
                # Стандартный расчет индикаторов (для обратной совместимости)
                data = self._calculate_default_indicators(data)

            return data

        except Exception as e:
            self.logger.error(f"❌ Ошибка расчета индикаторов: {e}")
            return data

    def _calculate_default_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """Стандартный расчет индикаторов (для обратной совместимости)"""
        try:
            df = data.copy()

            # Базовые индикаторы
            if 'rsi' not in df.columns:
                df = self.data_fetcher.calculate_technical_indicators(df)

            # Дополнительные индикаторы
            exp1 = df['close'].ewm(span=12).mean()
            exp2 = df['close'].ewm(span=26).mean()
            df['macd'] = exp1 - exp2
            df['macd_signal'] = df['macd'].ewm(span=9).mean()
            df['macd_histogram'] = df['macd'] - df['macd_signal']

            df['bb_middle'] = df['close'].rolling(window=20).mean()
            bb_std = df['close'].rolling(window=20).std()
            df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
            df['bb_lower'] = df['bb_middle'] - (bb_std * 2)

            self.logger.info("✅ Стандартные индикаторы рассчитаны")
            return df

        except Exception as e:
            self.logger.error(f"❌ Ошибка расчета стандартных индикаторов: {e}")
            return data

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

            # Рассчитываем базовые индикаторы
            data = self.data_fetcher.calculate_technical_indicators(data)

            # Рассчитываем расширенные индикаторы
            data = self.calculate_advanced_indicators(data)

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

            # Анализ MACD
            macd_signal = "БЫЧИЙ" if data['macd'].iloc[-1] > data['macd_signal'].iloc[-1] else "МЕДВЕЖИЙ"

            # Анализ Stochastic
            stoch_signal = "ПЕРЕПРОДАН" if data['stoch_k'].iloc[-1] < 20 else "ПЕРЕКУПЛЕН" if data['stoch_k'].iloc[
                                                                                                  -1] > 80 else "НЕЙТРАЛЬНЫЙ"

            return (f"Тренд: {trend}, Волатильность: {volatility:.5f}, "
                    f"RSI: {rsi_signal} ({rsi_current:.1f}), "
                    f"MACD: {macd_signal}, Stochastic: {stoch_signal}")

        except Exception as e:
            return f"Анализ не удался: {str(e)}"

    def analyze_market(self, symbol: str, timeframe: str) -> Dict[str, any]:
        """
        Глубокий анализ рынка с предсказаниями
        """
        try:
            self.logger.info(f"🔍 Глубокий анализ рынка для {symbol} {timeframe}")

            # Получаем исторические данные
            data = self.data_fetcher.get_rates(symbol, timeframe, count=200)
            if data is None or data.empty:
                self.logger.error("❌ Не удалось получить данные для анализа")
                return {}

            # Рассчитываем индикаторы
            data = self.data_fetcher.calculate_technical_indicators(data)
            data = self.calculate_advanced_indicators(data)

            # Получаем последние значения
            latest = data.iloc[-1]
            previous = data.iloc[-2]

            # Формируем анализ
            analysis = {
                'symbol': symbol,
                'timeframe': timeframe,
                'current_price': latest['close'],
                'timestamp': datetime.now(),
                'indicators': {},
                'signals': {},
                'prediction': {},
                'recommendation': ''
            }

            # Анализ индикаторов
            analysis['indicators'] = self._analyze_indicators(latest, previous)

            # Генерация торговых сигналов
            analysis['signals'] = self._generate_signals(latest, previous)

            # Формирование предсказания
            analysis['prediction'] = self._generate_prediction(analysis['signals'])

            # Итоговая рекомендация
            analysis['recommendation'] = self._get_final_recommendation(analysis)

            return analysis

        except Exception as e:
            self.logger.error(f"❌ Ошибка анализа рынка: {e}")
            return {}

    def _analyze_indicators(self, latest: pd.Series, previous: pd.Series) -> Dict[str, any]:
        """Анализ значений индикаторов"""
        indicators = {}

        try:
            # RSI анализ
            rsi = latest.get('rsi', 50)
            if rsi < 30:
                indicators['rsi'] = {'value': rsi, 'signal': 'OVERSOLD', 'strength': 'STRONG'}
            elif rsi > 70:
                indicators['rsi'] = {'value': rsi, 'signal': 'OVERBOUGHT', 'strength': 'STRONG'}
            else:
                indicators['rsi'] = {'value': rsi, 'signal': 'NEUTRAL', 'strength': 'WEAK'}

            # MACD анализ
            macd = latest.get('macd', 0)
            macd_signal = latest.get('macd_signal', 0)
            if macd > macd_signal and previous.get('macd', 0) <= previous.get('macd_signal', 0):
                indicators['macd'] = {'value': macd, 'signal': 'BULLISH_CROSSOVER', 'strength': 'STRONG'}
            elif macd < macd_signal and previous.get('macd', 0) >= previous.get('macd_signal', 0):
                indicators['macd'] = {'value': macd, 'signal': 'BEARISH_CROSSOVER', 'strength': 'STRONG'}
            else:
                indicators['macd'] = {'value': macd, 'signal': 'NEUTRAL', 'strength': 'WEAK'}

            # Bollinger Bands анализ
            price = latest['close']
            bb_upper = latest.get('bb_upper', price)
            bb_lower = latest.get('bb_lower', price)
            if price <= bb_lower:
                indicators['bollinger'] = {'value': price, 'signal': 'OVERSOLD', 'strength': 'STRONG'}
            elif price >= bb_upper:
                indicators['bollinger'] = {'value': price, 'signal': 'OVERBOUGHT', 'strength': 'STRONG'}
            else:
                indicators['bollinger'] = {'value': price, 'signal': 'NEUTRAL', 'strength': 'WEAK'}

            # Stochastic анализ
            stoch_k = latest.get('stoch_k', 50)
            stoch_d = latest.get('stoch_d', 50)
            if stoch_k < 20 and stoch_d < 20:
                indicators['stochastic'] = {'value': stoch_k, 'signal': 'OVERSOLD', 'strength': 'STRONG'}
            elif stoch_k > 80 and stoch_d > 80:
                indicators['stochastic'] = {'value': stoch_k, 'signal': 'OVERBOUGHT', 'strength': 'STRONG'}
            else:
                indicators['stochastic'] = {'value': stoch_k, 'signal': 'NEUTRAL', 'strength': 'WEAK'}

            # Ichimoku анализ
            tenkan = latest.get('ichi_tenkan', price)
            kijun = latest.get('ichi_kijun', price)
            if price > tenkan and price > kijun:
                indicators['ichimoku'] = {'value': price, 'signal': 'BULLISH', 'strength': 'MEDIUM'}
            elif price < tenkan and price < kijun:
                indicators['ichimoku'] = {'value': price, 'signal': 'BEARISH', 'strength': 'MEDIUM'}
            else:
                indicators['ichimoku'] = {'value': price, 'signal': 'NEUTRAL', 'strength': 'WEAK'}

        except Exception as e:
            self.logger.error(f"❌ Ошибка анализа индикаторов: {e}")

        return indicators

    def _generate_signals(self, latest: pd.Series, previous: pd.Series) -> Dict[str, int]:
        """Генерация торговых сигналов"""
        signals = {'buy': 0, 'sell': 0, 'neutral': 0}

        try:
            # RSI сигналы
            rsi = latest.get('rsi', 50)
            if rsi < 30:
                signals['buy'] += 2
            elif rsi > 70:
                signals['sell'] += 2
            else:
                signals['neutral'] += 1

            # MACD сигналы
            macd = latest.get('macd', 0)
            macd_signal = latest.get('macd_signal', 0)
            prev_macd = previous.get('macd', 0)
            prev_signal = previous.get('macd_signal', 0)

            if macd > macd_signal and prev_macd <= prev_signal:
                signals['buy'] += 3  # Бычье пересечение
            elif macd < macd_signal and prev_macd >= prev_signal:
                signals['sell'] += 3  # Медвежье пересечение

            # Bollinger Bands сигналы
            price = latest['close']
            bb_lower = latest.get('bb_lower', price)
            bb_upper = latest.get('bb_upper', price)

            if price <= bb_lower:
                signals['buy'] += 2
            elif price >= bb_upper:
                signals['sell'] += 2

            # Stochastic сигналы
            stoch_k = latest.get('stoch_k', 50)
            stoch_d = latest.get('stoch_d', 50)

            if stoch_k < 20 and stoch_d < 20:
                signals['buy'] += 1
            elif stoch_k > 80 and stoch_d > 80:
                signals['sell'] += 1

            # Parabolic SAR сигналы
            psar_trend = latest.get('psar_trend', 0)
            if psar_trend == 1:
                signals['buy'] += 1
            elif psar_trend == -1:
                signals['sell'] += 1

        except Exception as e:
            self.logger.error(f"❌ Ошибка генерации сигналов: {e}")

        return signals

    def _generate_prediction(self, signals: Dict[str, int]) -> Dict[str, any]:
        """Генерация предсказания с учетом выбранной стратегии"""
        prediction = {}

        try:
            if self.current_strategy:
                # Используем параметры стратегии для предсказания
                strategy_params = self.current_strategy.get_prediction_parameters()
                confidence_threshold = strategy_params.get('confidence_threshold', 60)
                default_timeframe = strategy_params.get('timeframe', 'MEDIUM')
                risk_level = strategy_params.get('risk_level', 'MEDIUM')
            else:
                # Параметры по умолчанию
                confidence_threshold = 60
                default_timeframe = 'MEDIUM'
                risk_level = 'MEDIUM'

            buy_signals = signals.get('buy', 0)
            sell_signals = signals.get('sell', 0)
            neutral_signals = signals.get('neutral', 0)

            total_signals = buy_signals + sell_signals + neutral_signals
            if total_signals == 0:
                return {
                    'direction': 'NEUTRAL',
                    'confidence': 0,
                    'timeframe': default_timeframe,
                    'risk_level': risk_level
                }

            buy_ratio = buy_signals / total_signals * 100
            sell_ratio = sell_signals / total_signals * 100

            if buy_ratio > confidence_threshold:
                prediction['direction'] = 'BULLISH'
                prediction['confidence'] = min(int(buy_ratio), 95)
            elif sell_ratio > confidence_threshold:
                prediction['direction'] = 'BEARISH'
                prediction['confidence'] = min(int(sell_ratio), 95)
            else:
                prediction['direction'] = 'NEUTRAL'
                prediction['confidence'] = max(neutral_signals * 10, 50)

            # Временной горизонт предсказания
            if prediction['confidence'] > 80:
                prediction['timeframe'] = 'LONG'
            elif prediction['confidence'] > 60:
                prediction['timeframe'] = 'MEDIUM'
            else:
                prediction['timeframe'] = 'SHORT'

            prediction['risk_level'] = risk_level
            prediction['strategy'] = self.current_strategy.name if self.current_strategy else 'Standard'

        except Exception as e:
            self.logger.error(f"❌ Ошибка генерации предсказания: {e}")
            prediction = {
                'direction': 'NEUTRAL',
                'confidence': 0,
                'timeframe': 'SHORT',
                'risk_level': 'MEDIUM',
                'strategy': 'Standard'
            }

        return prediction

    def _get_final_recommendation(self, analysis: Dict[str, any]) -> str:
        """Формирование итоговой рекомендации"""
        try:
            prediction = analysis.get('prediction', {})
            direction = prediction.get('direction', 'NEUTRAL')
            confidence = prediction.get('confidence', 0)

            if direction == 'BULLISH' and confidence > 70:
                return "🟢 СИЛЬНАЯ ПОКУПКА"
            elif direction == 'BULLISH' and confidence > 50:
                return "🟡 УМЕРЕННАЯ ПОКУПКА"
            elif direction == 'BEARISH' and confidence > 70:
                return "🔴 СИЛЬНАЯ ПРОДАЖА"
            elif direction == 'BEARISH' and confidence > 50:
                return "🟠 УМЕРЕННАЯ ПРОДАЖА"
            else:
                return "⚪️ УДЕРЖАНИЕ"

        except Exception as e:
            self.logger.error(f"❌ Ошибка формирования рекомендации: {e}")
            return "⚪️ НЕОПРЕДЕЛЕННО"

    def display_market_analysis(self, analysis: Dict[str, any]):
        """Отображение анализа рынка с информацией о стратегии"""
        if not analysis:
            self.logger.error("❌ Нет данных для отображения")
            return

        try:
            print("\n" + "=" * 70)
            print("🎯 ГЛУБОКИЙ АНАЛИЗ РЫНКА")
            print("=" * 70)
            print(f"📊 Символ: {analysis.get('symbol', 'N/A')}")
            print(f"⏰ Таймфрейм: {analysis.get('timeframe', 'N/A')}")
            print(f"🎯 Стратегия: {self.current_strategy.name if self.current_strategy else 'Standard'}")
            print(f"💰 Текущая цена: {analysis.get('current_price', 0):.5f}")
            print(f"🕐 Время анализа: {analysis.get('timestamp', 'N/A')}")

            print("\n📈 АНАЛИЗ ИНДИКАТОРОВ:")
            indicators = analysis.get('indicators', {})
            for indicator, data in indicators.items():
                signal = data.get('signal', 'NEUTRAL')
                value = data.get('value', 0)
                strength = data.get('strength', 'WEAK')
                print(f"   {indicator.upper():<12}: {value:>8.2f} | {signal:<15} | {strength}")

            print("\n🎯 ТОРГОВЫЕ СИГНАЛЫ:")
            signals = analysis.get('signals', {})
            print(f"   📈 Покупка: {signals.get('buy', 0)} сигналов")
            print(f"   📉 Продажа: {signals.get('sell', 0)} сигналов")
            print(f"   ⚖️ Нейтрально: {signals.get('neutral', 0)} сигналов")

            print("\n🔮 ПРЕДСКАЗАНИЕ:")
            prediction = analysis.get('prediction', {})
            direction_emoji = "🟢" if prediction.get('direction') == 'BULLISH' else "🔴" if prediction.get(
                'direction') == 'BEARISH' else "⚪️"
            print(f"   Направление: {direction_emoji} {prediction.get('direction', 'NEUTRAL')}")
            print(f"   Уверенность: {prediction.get('confidence', 0)}%")
            print(f"   Временной горизонт: {prediction.get('timeframe', 'SHORT')}")
            print(f"   Уровень риска: {prediction.get('risk_level', 'MEDIUM')}")

            print("\n💡 РЕКОМЕНДАЦИЯ:")
            recommendation = analysis.get('recommendation', 'N/A')
            print(f"   {recommendation}")
            print("=" * 70)

        except Exception as e:
            self.logger.error(f"❌ Ошибка отображения анализа: {e}")

    def training_completion_menu(self, symbol: str, timeframe: str, model: pd.DataFrame):
        """Меню после завершения обучения"""
        while True:
            print("\n" + "=" * 50)
            print("🎓 ОБУЧЕНИЕ ЗАВЕРШЕНО")
            print("=" * 50)
            print("1 - 🧪 Начать тестовую торговлю")
            print("2 - 🎯 Начать реальную торговлю")
            print("3 - 🔍 Проанализировать рынок")
            print("4 - 🔙 Вернуться в главное меню")
            print("=" * 50)

            choice = input("\n🎯 Выберите действие (1-4): ").strip()

            if choice == "1":
                self.run_test_trading(symbol, timeframe, model)
            elif choice == "2":
                self.run_real_trading(symbol, timeframe, model)
            elif choice == "3":
                analysis = self.analyze_market(symbol, timeframe)
                self.display_market_analysis(analysis)
            elif choice == "4":
                break
            else:
                print("❌ Неизвестная команда. Выберите от 1 до 4.")

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

            # Применяем стратегию
            if self.current_strategy:
                # Используем выбранную стратегию
                data = self.current_strategy.calculate_indicators(data)
                signal_info = self.current_strategy.generate_signal(data)
                signal = signal_info.get('signal', 'HOLD')
                description = signal_info.get('description', '')
                test_logger.info(f"📊 Стратегия: {self.current_strategy.name}")
                test_logger.info(f"📝 {description}")
            else:
                # Стандартная стратегия (для обратной совместимости)
                signal = self._simple_moving_average_strategy(data)
                test_logger.info("📊 Стратегия: Стандартная (MA)")

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
        """Запускает торговую стратегию с учетом выбранного стиля"""
        try:
            # Проверяем доступность рынка перед торговлей
            if not self.market_available:
                self.logger.error(f"❌ Торговля невозможна: рынок недоступен для {symbol}")
                return

            if not self.current_strategy:
                self.logger.warning("⚠️ Стратегия не установлена, используем стандартную")
                self.set_strategy('simple_ma')

            self.logger.info(f"🎯 Запуск стратегии '{self.current_strategy.name}' для {symbol} {timeframe}")

            # Получаем исторические данные
            data = self.data_fetcher.get_rates(symbol, timeframe, count=100)
            if data is None or data.empty:
                self.logger.error("❌ Не удалось получить данные")
                return

            # Рассчитываем индикаторы для выбранной стратегии
            data = self.calculate_advanced_indicators(data)

            # Генерируем сигнал с использованием выбранной стратегии
            signal_info = self.current_strategy.generate_signal(data)
            signal = signal_info.get('signal', 'HOLD')
            strength = signal_info.get('strength', 0)
            description = signal_info.get('description', '')

            self.logger.info(f"📊 Сигнал стратегии: {signal} (сила: {strength:.1f}%)")
            self.logger.info(f"📝 {description}")

            if signal == "BUY":
                self.logger.info(f"📈 Сигнал BUY для {symbol}")
                self._execute_trade(symbol, 'buy', strength)

            elif signal == "SELL":
                self.logger.info(f"📉 Сигнал SELL для {symbol}")
                self._execute_trade(symbol, 'sell', strength)
            else:
                self.logger.info(f"⚖️ Нет сигнала для {symbol}")

        except Exception as e:
            self.logger.error(f"💥 Ошибка в стратегии: {str(e)}")

    def _execute_trade(self, symbol: str, order_type: str, signal_strength: float):
        """Выполнение торговой операции с учетом силы сигнала"""
        try:
            # Рассчитываем объем на основе риска и силы сигнала
            base_risk = self.settings.RISK_PERCENT
            adjusted_risk = base_risk * (signal_strength / 100.0) if signal_strength > 0 else base_risk

            volume = self.trader.calculate_position_size(
                symbol,
                risk_percent=adjusted_risk,
                stop_loss_pips=self.settings.STOPLOSS_PIPS
            )

            if volume:
                # Корректируем стоп-лосс и тейк-профит на основе силы сигнала
                sl = self.settings.STOPLOSS_PIPS if self.settings.ENABLE_STOPLOSS else 0.0
                tp = self.settings.TAKEPROFIT_PIPS if self.settings.ENABLE_TAKEPROFIT else 0.0

                # Увеличиваем тейк-профит для сильных сигналов
                if signal_strength > 70:
                    tp = tp * 1.5  # +50% для сильных сигналов
                elif signal_strength < 30:
                    sl = sl * 1.2  # +20% стоп-лосс для слабых сигналов

                success, message = self.trader.send_order(
                    symbol=symbol,
                    order_type=order_type,
                    volume=volume,
                    stop_loss_pips=sl,
                    take_profit_pips=tp,
                    comment=f"{self.current_strategy.name} (сила: {signal_strength:.1f}%)"
                )
                if success:
                    self.logger.info(f"✅ {message}")
                else:
                    self.logger.error(f"❌ {message}")
            else:
                self.logger.error("❌ Не удалось рассчитать объем позиции")

        except Exception as e:
            self.logger.error(f"💥 Ошибка выполнения торговой операции: {str(e)}")

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

            # Показываем информацию о позициях перед закрытием
            total_profit = sum(pos.get('profit', 0) + pos.get('swap', 0) for pos in positions)
            self.logger.info(f"💰 Общий P&L перед закрытием: {total_profit:.2f}")

            # Запрашиваем подтверждение
            confirm = input("Вы уверены, что хотите закрыть все позиции? (y/N): ").strip().lower()
            if confirm not in ['y', 'yes', 'да']:
                self.logger.info("❌ Закрытие позиций отменено")
                return

            # Закрываем все позиции
            success, message = self.trader.close_all_positions(symbol)
            if success:
                # Разделяем сообщение на строки для лучшего форматирования
                if " | " in message:
                    lines = message.split(" | ")
                    self.logger.info("=" * 50)
                    for line in lines:
                        if line.strip():
                            self.logger.info(line)
                    self.logger.info("=" * 50)
                else:
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
        """Полный цикл обучения и торговли с выбором стратегии"""
        try:
            # Выбор стратегии
            print("\n🎯 НАСТРОЙКА СТРАТЕГИИ ДЛЯ ОБУЧЕНИЯ")
            strategy_id = self.select_strategy()
            if not strategy_id:
                return

            if not self.set_strategy(strategy_id):
                return

            symbol = self.select_symbol()
            if not symbol:
                return

            timeframe = self.select_timeframe()
            if not timeframe:
                return

            print(f"🎓 Обучение для {symbol} {timeframe} с стратегией '{self.current_strategy.name}'...")
            model = self.run_training(symbol, timeframe)

            if model is not None:
                self.training_completion_menu(symbol, timeframe, model)
            else:
                print("❌ Обучение не удалось")
        except Exception as e:
            self.logger.error(f"❌ Ошибка в цикле обучения и торговли: {e}")

    def market_analysis_flow(self):
        """Поток анализа рынка"""
        try:
            symbol = self.select_symbol()
            if not symbol:
                print("❌ Неверный символ")
                return

            timeframe = self.select_timeframe()
            if not timeframe:
                print("❌ Неверный таймфрейм")
                return

            print(f"🔍 Анализ рынка для {symbol} {timeframe}...")
            analysis = self.analyze_market(symbol, timeframe)
            self.display_market_analysis(analysis)

        except Exception as e:
            self.logger.error(f"❌ Ошибка в анализе рынка: {e}")

    def strategy_selection_flow(self):
        """Поток выбора и настройки стратегии"""
        try:
            print("\n🎯 ВЫБОР СТРАТЕГИИ ТОРГОВЛИ")
            print("=" * 50)

            # Показываем текущую стратегию
            if self.current_strategy:
                print(f"📊 Текущая стратегия: {self.current_strategy.name}")
                print(f"📝 {self.current_strategy.description}")
            else:
                print("⚠️ Стратегия не установлена")

            print("\n1 - 🔄 Выбрать другую стратегию")
            print("2 - 📊 Протестировать стратегию")
            print("3 - 🔙 Вернуться в главное меню")
            print("=" * 50)

            choice = input("\n🎯 Выберите действие (1-3): ").strip()

            if choice == "1":
                strategy_id = self.select_strategy()
                if strategy_id:
                    if self.set_strategy(strategy_id):
                        print(f"✅ Стратегия успешно установлена: {self.current_strategy.name}")
                    else:
                        print("❌ Не удалось установить стратегию")

            elif choice == "2":
                self.test_strategy_flow()

            elif choice == "3":
                return

            else:
                print("❌ Неизвестная команда")

        except Exception as e:
            self.logger.error(f"❌ Ошибка в выборе стратегии: {e}")

    def test_strategy_flow(self):
        """Тестирование выбранной стратегии"""
        try:
            if not self.current_strategy:
                print("❌ Сначала выберите стратегию")
                return

            symbol = self.select_symbol()
            if not symbol:
                return

            timeframe = self.select_timeframe()
            if not timeframe:
                return

            print(f"🧪 Тестирование стратегии '{self.current_strategy.name}' на {symbol} {timeframe}...")

            # Получаем исторические данные
            data = self.data_fetcher.get_rates(symbol, timeframe, count=100)
            if data is None or data.empty:
                print("❌ Не удалось получить данные для тестирования")
                return

            # Рассчитываем индикаторы
            data = self.calculate_advanced_indicators(data)

            # Генерируем сигналы
            signal_info = self.current_strategy.generate_signal(data)

            print(f"\n📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ:")
            print("=" * 40)
            print(f"🎯 Стратегия: {self.current_strategy.name}")
            print(f"📈 Символ: {symbol}")
            print(f"⏰ Таймфрейм: {timeframe}")
            print(f"📡 Сигнал: {signal_info.get('signal', 'N/A')}")
            print(f"💪 Сила сигнала: {signal_info.get('strength', 0):.1f}%")
            print(f"📝 Описание: {signal_info.get('description', 'N/A')}")
            print("=" * 40)

            # Показываем последние значения индикаторов
            if not data.empty:
                print(f"\n📊 Последние значения индикаторов:")
                for indicator in self.current_strategy.required_indicators:
                    if indicator in data.columns:
                        value = data[indicator].iloc[-1]
                        print(f"   {indicator}: {value:.4f}")

        except Exception as e:
            self.logger.error(f"❌ Ошибка тестирования стратегии: {e}")

    def start_real_time_monitoring(self, symbols: List[str], update_interval: int = 5):
        """Запуск мониторинга в реальном времени"""
        try:
            self.monitoring_symbols = symbols
            success = self.realtime_monitor.start_monitoring(symbols, update_interval)

            if success:
                self.logger.info(f"🚀 Запущен мониторинг в реальном времени для {len(symbols)} символов")
                return True
            else:
                self.logger.error("❌ Не удалось запустить мониторинг в реальном времени")
                return False

        except Exception as e:
            self.logger.error(f"❌ Ошибка запуска мониторинга: {e}")
            return False

    def stop_real_time_monitoring(self):
        """Остановка мониторинга в реальном времени"""
        try:
            self.realtime_monitor.stop_monitoring()
            self.logger.info("🛑 Мониторинг в реальном времени остановлен")
        except Exception as e:
            self.logger.error(f"❌ Ошибка остановки мониторинга: {e}")

    def get_market_summary(self) -> Dict[str, any]:
        """Получение сводки по рынку"""
        try:
            if self.realtime_monitor:
                return self.realtime_monitor.get_market_summary()
            else:
                return {}
        except Exception as e:
            self.logger.error(f"❌ Ошибка получения сводки рынка: {e}")
            return {}

    def real_time_monitoring_flow(self):
        """Поток мониторинга в реальном времени"""
        try:
            print("\n🎯 МОНИТОРИНГ РЫНКА В РЕАЛЬНОМ ВРЕМЕНИ")
            print("=" * 50)

            # Выбор символов для мониторинга
            symbols = []
            print("\n📊 Выбор символов для мониторинга:")
            print("1 - Основные валютные пары")
            print("2 - Золото и нефть")
            print("3 - Индексы")
            print("4 - Выбрать вручную")

            choice = input("\n🎯 Выберите опцию (1-4): ").strip()

            if choice == "1":
                symbols = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD']
            elif choice == "2":
                symbols = ['XAUUSD', 'XAGUSD', 'XTIUSD', 'XBRUSD']
            elif choice == "3":
                symbols = ['US500', 'US30', 'USTEC', 'DE30']
            elif choice == "4":
                symbols = self._select_multiple_symbols()
            else:
                print("❌ Неверный выбор")
                return

            if not symbols:
                print("❌ Не выбраны символы для мониторинга")
                return

            # Запуск мониторинга
            print(f"\n🚀 Запуск мониторинга для {len(symbols)} символов...")
            if self.start_real_time_monitoring(symbols, update_interval=10):
                self._display_real_time_dashboard()
            else:
                print("❌ Не удалось запустить мониторинг")

        except Exception as e:
            self.logger.error(f"❌ Ошибка в потоке мониторинга: {e}")

    def _select_multiple_symbols(self) -> List[str]:
        """Выбор нескольких символов"""
        try:
            all_symbols = self.data_fetcher.get_symbols()
            if not all_symbols:
                return []

            selected_symbols = []

            while True:
                print(f"\n📊 Доступно символов: {len(all_symbols)}")
                print("Введите символы через запятую или 'done' для завершения:")
                print("Пример: EURUSD, GBPUSD, XAUUSD")

                input_str = input("Символы: ").strip().upper()

                if input_str == 'DONE':
                    break

                symbols_to_add = [s.strip() for s in input_str.split(',')]
                valid_symbols = []

                for symbol in symbols_to_add:
                    if symbol in all_symbols:
                        valid_symbols.append(symbol)
                    else:
                        print(f"⚠️ Символ {symbol} не найден")

                selected_symbols.extend(valid_symbols)
                print(f"✅ Добавлено символов: {len(valid_symbols)}")
                print(f"📋 Всего выбрано: {len(selected_symbols)}")

            return list(set(selected_symbols))  # Убираем дубликаты

        except Exception as e:
            self.logger.error(f"❌ Ошибка выбора символов: {e}")
            return []

    def _display_real_time_dashboard(self):
        """Отображение дашборда реального времени"""
        try:
            import os

            while True:
                os.system('cls' if os.name == 'nt' else 'clear')

                summary = self.get_market_summary()
                if not summary:
                    print("❌ Нет данных для отображения")
                    time.sleep(5)
                    continue

                print("=" * 80)
                print("🎯 ДАШБОРД РЕАЛЬНОГО ВРЕМЕНИ - AI TRADER")
                print("=" * 80)
                print(f"🕐 Последнее обновление: {summary.get('timestamp', 'N/A')}")
                print(f"📊 Состояние рынка: {summary.get('market_state', 'UNKNOWN')}")
                print(f"📈 Бычьих символов: {summary.get('bullish_count', 0)}")
                print(f"📉 Медвежьих символов: {summary.get('bearish_count', 0)}")
                print(f"⚖️ Боковых символов: {summary.get('sideways_count', 0)}")

                print("\n🚀 ТОП ДВИЖУЩИХСЯ СИМВОЛОВ:")
                print("-" * 50)
                for mover in summary.get('top_movers', [])[:5]:
                    change = mover.get('change', 0)
                    emoji = "🟢" if change > 0 else "🔴" if change < 0 else "⚪️"
                    print(f"{emoji} {mover['symbol']:8} | {change:>+7.2f}% | {mover['current_price']:.5f}")

                print("\n" + "=" * 80)
                print("⏹️ Нажмите Ctrl+C для остановки мониторинга")

                time.sleep(10)  # Обновление каждые 10 секунд

        except KeyboardInterrupt:
            print("\n🛑 Остановка мониторинга...")
            self.stop_real_time_monitoring()
        except Exception as e:
            self.logger.error(f"❌ Ошибка отображения дашборда: {e}")
            self.stop_real_time_monitoring()

    def select_symbol(self) -> Optional[str]:
        """Выбор символа из доступных"""
        try:
            symbols = self.data_fetcher.get_symbols()
            if not symbols:
                self.logger.error("❌ Не удалось получить список символов")
                return None

            print("\n📊 ДОСТУПНЫЕ СИМВОЛЫ:")
            print("=" * 40)

            # Показываем символы с группировкой
            forex_symbols = [s for s in symbols if any(
                currency in s for currency in ['USD', 'EUR', 'GBP', 'JPY', 'AUD', 'CAD', 'CHF', 'NZD'])]
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
            self.logger.error(f"❌ Ошибка выбора символа: {e}")
            return None

    def select_timeframe(self) -> Optional[str]:
        """Выбор таймфрейма"""
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

    def shutdown(self):
        """Корректное завершение работы"""
        self.logger.info("🛑 Завершение работы AI Trader...")
        if self.realtime_monitor:
            self.stop_real_time_monitoring()
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
    parser.add_argument('--analyze', action='store_true', help='Провести анализ рынка')

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

        elif args.analyze:
            # Анализ рынка
            trader.market_analysis_flow()

        else:
            # Интерактивный режим
            print("🤖 Используйте 'python main.py' для интерактивного режима")
            print("📋 Доступные команды:")
            print("  python main.py --info")
            print("  python main.py --test --symbol EURUSD")
            print("  python main.py --strategy --symbol EURUSD --timeframe H1")
            print("  python main.py --analyze --symbol EURUSD --timeframe H1")

    except KeyboardInterrupt:
        trader.logger.info("🛑 Получен сигнал прерывания")
    except Exception as e:
        trader.logger.error(f"💥 Критическая ошибка: {str(e)}")
    finally:
        trader.shutdown()


if __name__ == "__main__":
    main()

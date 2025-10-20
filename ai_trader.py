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

    def calculate_advanced_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Расчет расширенных технических индикаторов
        """
        try:
            # Копируем данные чтобы избежать предупреждений
            df = data.copy()

            # 1. RSI (Relative Strength Index) - уже есть в базовых индикаторах
            if 'rsi' not in df.columns:
                df = self.data_fetcher.calculate_technical_indicators(df)

            # 2. MACD (Moving Average Convergence Divergence)
            exp1 = df['close'].ewm(span=12).mean()
            exp2 = df['close'].ewm(span=26).mean()
            df['macd'] = exp1 - exp2
            df['macd_signal'] = df['macd'].ewm(span=9).mean()
            df['macd_histogram'] = df['macd'] - df['macd_signal']

            # 3. Bollinger Bands
            df['bb_middle'] = df['close'].rolling(window=20).mean()
            bb_std = df['close'].rolling(window=20).std()
            df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
            df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
            df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']

            # 4. Stochastic Oscillator
            low_14 = df['low'].rolling(window=14).min()
            high_14 = df['high'].rolling(window=14).max()
            df['stoch_k'] = 100 * ((df['close'] - low_14) / (high_14 - low_14))
            df['stoch_d'] = df['stoch_k'].rolling(window=3).mean()

            # 5. Average True Range (ATR)
            high_low = df['high'] - df['low']
            high_close_prev = abs(df['high'] - df['close'].shift())
            low_close_prev = abs(df['low'] - df['close'].shift())
            true_range = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
            df['atr'] = true_range.rolling(window=14).mean()

            # 6. Ichimoku Cloud
            df['ichi_tenkan'] = (df['high'].rolling(window=9).max() + df['low'].rolling(window=9).min()) / 2
            df['ichi_kijun'] = (df['high'].rolling(window=26).max() + df['low'].rolling(window=26).min()) / 2
            df['ichi_senkou_a'] = ((df['ichi_tenkan'] + df['ichi_kijun']) / 2).shift(26)
            df['ichi_senkou_b'] = (
                    (df['high'].rolling(window=52).max() + df['low'].rolling(window=52).min()) / 2).shift(26)
            df['ichi_chikou'] = df['close'].shift(-26)

            # 7. Volume Weighted Average Price (VWAP)
            if 'tick_volume' in df.columns:
                df['vwap'] = (df['close'] * df['tick_volume']).cumsum() / df['tick_volume'].cumsum()

            # 8. Parabolic SAR
            df = self._calculate_parabolic_sar(df)

            # 9. Commodity Channel Index (CCI)
            typical_price = (df['high'] + df['low'] + df['close']) / 3
            sma_typical = typical_price.rolling(window=20).mean()
            mad = typical_price.rolling(window=20).apply(lambda x: np.abs(x - x.mean()).mean())
            df['cci'] = (typical_price - sma_typical) / (0.015 * mad)

            # 10. Williams %R
            df['williams_r'] = (df['high'].rolling(window=14).max() - df['close']) / (
                    df['high'].rolling(window=14).max() - df['low'].rolling(window=14).min()) * -100

            self.logger.info("✅ Расширенные индикаторы успешно рассчитаны")
            return df

        except Exception as e:
            self.logger.error(f"❌ Ошибка расчета расширенных индикаторов: {e}")
            return data

    def _calculate_parabolic_sar(self, df: pd.DataFrame, af_start: float = 0.02, af_increment: float = 0.02,
                                 af_max: float = 0.2) -> pd.DataFrame:
        """Расчет Parabolic SAR"""
        try:
            high = df['high'].values
            low = df['low'].values
            close = df['close'].values

            psar = np.zeros(len(close))
            trend = np.zeros(len(close))
            ep = np.zeros(len(close))
            af = np.zeros(len(close))

            # Инициализация
            psar[0] = close[0]
            trend[0] = 1  # 1 = восходящий тренд, -1 = нисходящий
            ep[0] = high[0] if trend[0] == 1 else low[0]
            af[0] = af_start

            for i in range(1, len(close)):
                # Обновление PSAR
                psar[i] = psar[i - 1] + af[i - 1] * (ep[i - 1] - psar[i - 1])

                # Проверка смены тренда
                if trend[i - 1] == 1:
                    if low[i] < psar[i]:
                        trend[i] = -1
                        psar[i] = max(high[i - 1], high[i])
                        ep[i] = low[i]
                        af[i] = af_start
                    else:
                        trend[i] = 1
                        if high[i] > ep[i - 1]:
                            ep[i] = high[i]
                            af[i] = min(af[i - 1] + af_increment, af_max)
                        else:
                            ep[i] = ep[i - 1]
                            af[i] = af[i - 1]
                else:
                    if high[i] > psar[i]:
                        trend[i] = 1
                        psar[i] = min(low[i - 1], low[i])
                        ep[i] = high[i]
                        af[i] = af_start
                    else:
                        trend[i] = -1
                        if low[i] < ep[i - 1]:
                            ep[i] = low[i]
                            af[i] = min(af[i - 1] + af_increment, af_max)
                        else:
                            ep[i] = ep[i - 1]
                            af[i] = af[i - 1]

            df['psar'] = psar
            df['psar_trend'] = trend
            return df

        except Exception as e:
            self.logger.error(f"❌ Ошибка расчета Parabolic SAR: {e}")
            return df

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
        """Генерация предсказания на основе сигналов"""
        prediction = {}

        try:
            buy_signals = signals.get('buy', 0)
            sell_signals = signals.get('sell', 0)
            neutral_signals = signals.get('neutral', 0)

            total_signals = buy_signals + sell_signals + neutral_signals
            if total_signals == 0:
                return {'direction': 'NEUTRAL', 'confidence': 0, 'timeframe': 'SHORT'}

            buy_ratio = buy_signals / total_signals
            sell_ratio = sell_signals / total_signals

            if buy_ratio > 0.6:
                prediction['direction'] = 'BULLISH'
                prediction['confidence'] = min(int(buy_ratio * 100), 95)
            elif sell_ratio > 0.6:
                prediction['direction'] = 'BEARISH'
                prediction['confidence'] = min(int(sell_ratio * 100), 95)
            else:
                prediction['direction'] = 'NEUTRAL'
                prediction['confidence'] = max(neutral_signals * 10, 50)

            # Определение временного горизонта предсказания
            if prediction['confidence'] > 80:
                prediction['timeframe'] = 'MEDIUM'
            else:
                prediction['timeframe'] = 'SHORT'

        except Exception as e:
            self.logger.error(f"❌ Ошибка генерации предсказания: {e}")
            prediction = {'direction': 'NEUTRAL', 'confidence': 0, 'timeframe': 'SHORT'}

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
        """Отображение анализа рынка"""
        if not analysis:
            self.logger.error("❌ Нет данных для отображения")
            return

        try:
            print("\n" + "=" * 70)
            print("🎯 ГЛУБОКИЙ АНАЛИЗ РЫНКА")
            print("=" * 70)
            print(f"📊 Символ: {analysis.get('symbol', 'N/A')}")
            print(f"⏰ Таймфрейм: {analysis.get('timeframe', 'N/A')}")
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
                        stop_loss_pips=sl,  # ИСПРАВЛЕНО: используем правильное имя параметра
                        take_profit_pips=tp,  # ИСПРАВЛЕНО: используем правильное имя параметра
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
                        stop_loss_pips=sl,  # ИСПРАВЛЕНО: используем правильное имя параметра
                        take_profit_pips=tp,  # ИСПРАВЛЕНО: используем правильное имя параметра
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
        """Полный цикл обучения и торговли"""
        try:
            symbol = self.select_symbol()
            if not symbol:
                print("❌ Неверный символ")
                return

            timeframe = self.select_timeframe()
            if not timeframe:
                print("❌ Неверный таймфрейм")
                return

            print(f"🎓 Обучение для {symbol} {timeframe}...")
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

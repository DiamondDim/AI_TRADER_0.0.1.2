#!/usr/bin/env python3
"""
Модуль для отслеживания рынка в реальном времени
"""

import time
import threading
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
import logging
from .data import DataFetcher
from .mt5 import MT5


class RealTimeMonitor:
    """Монитор рынка в реальном времени"""

    def __init__(self, data_fetcher: DataFetcher):
        self.data_fetcher = data_fetcher
        self.logger = logging.getLogger('RealTimeMonitor')
        self.running = False
        self.thread = None
        self.subscribers = []
        self.symbols = []
        self.symbol_mapping = {}  # Сопоставление базовых символов с полными именами
        self.update_interval = 5  # секунды

    def start_monitoring(self, symbols: List[str], update_interval: int = 5):
        """Запуск мониторинга символов"""
        try:
            self.symbols = symbols
            self.update_interval = update_interval
            self.running = True

            # Инициализируем сопоставление символов
            self._initialize_symbol_mapping(symbols)

            self.thread = threading.Thread(target=self._monitoring_loop, daemon=True)
            self.thread.start()

            self.logger.info(f"🚀 Запущен мониторинг в реальном времени для {len(symbols)} символов")
            return True

        except Exception as e:
            self.logger.error(f"❌ Ошибка запуска мониторинга: {e}")
            return False

    def _initialize_symbol_mapping(self, symbols: List[str]):
        """Инициализация сопоставления символов с правильными именами"""
        self.symbol_mapping = {}

        for symbol in symbols:
            correct_symbol = self._find_correct_symbol(symbol)
            if correct_symbol:
                self.symbol_mapping[symbol] = correct_symbol
                self.logger.info(f"✅ Символ {symbol} -> {correct_symbol}")
            else:
                self.logger.warning(f"⚠️ Не удалось найти правильный символ для {symbol}")

    def _find_correct_symbol(self, base_symbol: str) -> Optional[str]:
        """
        Поиск правильного имени символа с учетом суффиксов брокера
        """
        possible_suffixes = ['', 'rfd', 'm', 'f', 'q', 'a', 'b', 'c', 'd', 'e']

        for suffix in possible_suffixes:
            test_symbol = base_symbol + suffix
            if self._check_symbol_exists(test_symbol):
                return test_symbol

        # Если не нашли с суффиксами, попробуем найти похожие символы
        all_symbols = self.data_fetcher.get_all_symbols()
        if all_symbols:
            for symbol in all_symbols:
                if base_symbol in symbol:
                    self.logger.info(f"🔍 Найден похожий символ: {symbol} для базового {base_symbol}")
                    if self._check_symbol_exists(symbol):
                        return symbol

        return None

    def _check_symbol_exists(self, symbol: str) -> bool:
        """Проверка существования символа"""
        try:
            # Пробуем получить информацию о символе
            symbol_info = self.data_fetcher.get_symbol_info(symbol)
            if symbol_info:
                # Пробуем получить текущую цену
                price = self.data_fetcher.get_current_price(symbol)
                return price is not None and price.get('bid', 0) > 0
            return False
        except Exception as e:
            self.logger.debug(f"Символ {symbol} не доступен: {e}")
            return False

    def stop_monitoring(self):
        """Остановка мониторинга"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        self.logger.info("🛑 Мониторинг остановлен")

    def subscribe(self, callback: Callable):
        """Подписка на обновления рынка"""
        self.subscribers.append(callback)
        self.logger.info(f"✅ Добавлен подписчик на обновления рынка")

    def unsubscribe(self, callback: Callable):
        """Отписка от обновлений"""
        if callback in self.subscribers:
            self.subscribers.remove(callback)
            self.logger.info(f"✅ Удален подписчик обновлений рынка")

    def _monitoring_loop(self):
        """Основной цикл мониторинга"""
        while self.running:
            try:
                market_data = self._get_real_time_data()

                # Уведомляем подписчиков
                for callback in self.subscribers:
                    try:
                        callback(market_data)
                    except Exception as e:
                        self.logger.error(f"❌ Ошибка в callback подписчика: {e}")

                time.sleep(self.update_interval)

            except Exception as e:
                self.logger.error(f"❌ Ошибка в цикле мониторинга: {e}")
                time.sleep(self.update_interval)

    def _get_real_time_data(self) -> Dict[str, any]:
        """Получение данных в реальном времени"""
        market_data = {
            'timestamp': datetime.now(),
            'symbols': {},
            'market_state': 'UNKNOWN'
        }

        try:
            price_changes = []
            volumes = []
            successful_symbols = 0

            for base_symbol in self.symbols:
                symbol = self.symbol_mapping.get(base_symbol, base_symbol)

                try:
                    # Получаем текущие цены
                    current_price = self.data_fetcher.get_current_price(symbol)
                    if not current_price or current_price.get('bid', 0) == 0:
                        # Пробуем переинициализировать символ
                        correct_symbol = self._find_correct_symbol(base_symbol)
                        if correct_symbol:
                            self.symbol_mapping[base_symbol] = correct_symbol
                            symbol = correct_symbol
                            current_price = self.data_fetcher.get_current_price(symbol)

                        if not current_price or current_price.get('bid', 0) == 0:
                            self.logger.warning(f"⚠️ Не удалось получить цену для {symbol} (базовый: {base_symbol})")
                            continue

                    # Получаем исторические данные для анализа
                    data = self.data_fetcher.get_rates(symbol, 'M1', count=50)
                    if data is None or data.empty:
                        self.logger.warning(f"⚠️ Нет исторических данных для {symbol}")
                        continue

                    # Рассчитываем изменение цены
                    price_change = self._calculate_price_change(data)
                    volume = data['tick_volume'].mean() if 'tick_volume' in data.columns else 0

                    symbol_data = {
                        'symbol': symbol,
                        'base_symbol': base_symbol,
                        'bid': current_price.get('bid', 0),
                        'ask': current_price.get('ask', 0),
                        'spread': current_price.get('spread', 0),
                        'price_change': price_change,
                        'volume': volume,
                        'timestamp': datetime.now(),
                        'indicators': self._calculate_realtime_indicators(data)
                    }

                    market_data['symbols'][base_symbol] = symbol_data
                    price_changes.append(price_change)
                    volumes.append(volume)
                    successful_symbols += 1

                except Exception as e:
                    self.logger.warning(f"⚠️ Ошибка получения данных для {symbol} (базовый: {base_symbol}): {e}")
                    continue

            # Определяем общее состояние рынка
            if price_changes and successful_symbols > 0:
                avg_change = sum(price_changes) / len(price_changes)
                if avg_change > 0.1:
                    market_data['market_state'] = 'BULLISH'
                elif avg_change < -0.1:
                    market_data['market_state'] = 'BEARISH'
                else:
                    market_data['market_state'] = 'SIDEWAYS'

                market_data['successful_symbols'] = successful_symbols
                market_data['total_symbols'] = len(self.symbols)

        except Exception as e:
            self.logger.error(f"❌ Ошибка получения данных рынка: {e}")

        return market_data

    def _calculate_price_change(self, data: pd.DataFrame) -> float:
        """Расчет изменения цены в процентах"""
        try:
            if len(data) < 2:
                return 0.0

            current_close = data['close'].iloc[-1]
            previous_close = data['close'].iloc[-2]

            change = ((current_close - previous_close) / previous_close) * 100
            return round(change, 4)

        except Exception as e:
            self.logger.error(f"❌ Ошибка расчета изменения цены: {e}")
            return 0.0

    def _calculate_realtime_indicators(self, data: pd.DataFrame) -> Dict[str, float]:
        """Расчет индикаторов в реальном времени"""
        indicators = {}

        try:
            if len(data) < 20:
                return indicators

            # RSI
            delta = data['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            indicators['rsi'] = 100 - (100 / (1 + rs)).iloc[-1]

            # Простая скользящая средняя
            indicators['sma_20'] = data['close'].rolling(window=20).mean().iloc[-1]

            # Волатильность (ATR)
            high_low = data['high'] - data['low']
            high_close = abs(data['high'] - data['close'].shift())
            low_close = abs(data['low'] - data['close'].shift())
            true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            indicators['atr'] = true_range.rolling(window=14).mean().iloc[-1]

            # Объем
            if 'tick_volume' in data.columns:
                indicators['volume_ma'] = data['tick_volume'].rolling(window=20).mean().iloc[-1]
                indicators['current_volume'] = data['tick_volume'].iloc[-1]

        except Exception as e:
            self.logger.error(f"❌ Ошибка расчета индикаторов реального времени: {e}")

        return indicators

    def get_market_summary(self) -> Dict[str, any]:
        """Получение сводки по рынку"""
        market_data = self._get_real_time_data()

        summary = {
            'timestamp': market_data['timestamp'],
            'market_state': market_data['market_state'],
            'total_symbols': len(self.symbols),
            'successful_symbols': market_data.get('successful_symbols', 0),
            'bullish_count': 0,
            'bearish_count': 0,
            'sideways_count': 0,
            'top_movers': []
        }

        for base_symbol, data in market_data['symbols'].items():
            change = data.get('price_change', 0)
            if change > 0.2:
                summary['bullish_count'] += 1
            elif change < -0.2:
                summary['bearish_count'] += 1
            else:
                summary['sideways_count'] += 1

            # Добавляем в топ движущихся
            summary['top_movers'].append({
                'symbol': base_symbol,
                'actual_symbol': data.get('symbol', ''),
                'change': change,
                'current_price': data.get('bid', 0)
            })

        # Сортируем по абсолютному изменению
        summary['top_movers'].sort(key=lambda x: abs(x['change']), reverse=True)
        summary['top_movers'] = summary['top_movers'][:5]  # Топ 5

        return summary

    def get_symbol_mapping(self) -> Dict[str, str]:
        """Получение текущего сопоставления символов"""
        return self.symbol_mapping.copy()

    def add_symbol(self, base_symbol: str) -> bool:
        """Добавление нового символа для мониторинга"""
        if base_symbol not in self.symbols:
            self.symbols.append(base_symbol)
            correct_symbol = self._find_correct_symbol(base_symbol)
            if correct_symbol:
                self.symbol_mapping[base_symbol] = correct_symbol
                self.logger.info(f"✅ Добавлен символ {base_symbol} -> {correct_symbol}")
                return True
            else:
                self.logger.warning(f"⚠️ Не удалось найти символ для {base_symbol}")
                return False
        return True

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Union

logger = logging.getLogger('DataFetcher')


class DataFetcher:
    def __init__(self, mt5_connection):
        self.mt5 = mt5_connection
        self.logger = logger

        # Словарь для преобразования таймфреймов
        self.timeframes = {
            'M1': mt5.TIMEFRAME_M1,
            'M5': mt5.TIMEFRAME_M5,
            'M15': mt5.TIMEFRAME_M15,
            'M30': mt5.TIMEFRAME_M30,
            'H1': mt5.TIMEFRAME_H1,
            'H4': mt5.TIMEFRAME_H4,
            'D1': mt5.TIMEFRAME_D1,
            'W1': mt5.TIMEFRAME_W1,
            'MN1': mt5.TIMEFRAME_MN1
        }

    def get_all_symbols(self) -> List[str]:
        """Получение списка всех доступных символов"""
        try:
            symbols = mt5.symbols_get()
            if symbols:
                return [symbol.name for symbol in symbols]
            return []
        except Exception as e:
            self.logger.error(f"❌ Ошибка получения списка символов: {e}")
            return []

    def get_symbol_info(self, symbol: str) -> Optional[any]:
        """Получение информации о символе"""
        try:
            return mt5.symbol_info(symbol)
        except Exception as e:
            self.logger.error(f"❌ Ошибка получения информации о символе {symbol}: {e}")
            return None

    def get_symbols(self, filter_symbol: str = "") -> List[str]:
        """Получает список доступных символов"""
        try:
            symbols = mt5.symbols_get()
            if not symbols:
                self.logger.warning("Не удалось получить список символов")
                return []

            symbol_names = [s.name for s in symbols]

            # Фильтрация если указан фильтр
            if filter_symbol:
                symbol_names = [s for s in symbol_names if filter_symbol.upper() in s.upper()]

            self.logger.info(f"📋 Получено {len(symbol_names)} символов")
            return symbol_names

        except Exception as e:
            self.logger.error(f"Ошибка получения списка символов: {str(e)}")
            return []

    def get_symbol_info_full(self, symbol: str) -> Optional[Dict]:
        """Получает подробную информацию о символе"""
        try:
            info = mt5.symbol_info(symbol)
            if not info:
                self.logger.error(f"Символ {symbol} не найден")
                return None

            return {
                'name': info.name,
                'description': info.description,
                'currency_base': info.currency_base,
                'currency_profit': info.currency_profit,
                'currency_margin': info.currency_margin,
                'digits': info.digits,
                'trade_mode': info.trade_mode,
                'trade_exemode': info.trade_exemode,
                'swap_mode': info.swap_mode,
                'volume_min': info.volume_min,
                'volume_max': info.volume_max,
                'volume_step': info.volume_step,
                'spread': info.spread,
                'spread_float': info.spread_float
            }
        except Exception as e:
            self.logger.error(f"Ошибка получения информации о символе: {str(e)}")
            return None

    def prepare_symbol(self, symbol: str) -> bool:
        """Подготавливает символ для торговли"""
        try:
            # Проверяем существует ли символ
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                self.logger.error(f"Символ {symbol} не найден")
                return False

            # Если символ не выбран в Market Watch, выбираем его
            if not symbol_info.visible:
                self.logger.info(f"🔍 Выбираем символ {symbol} в Market Watch")
                if not mt5.symbol_select(symbol, True):
                    self.logger.error(f"Не удалось выбрать символ {symbol}")
                    return False

            return True

        except Exception as e:
            self.logger.error(f"Ошибка подготовки символа {symbol}: {str(e)}")
            return False

    def find_correct_symbol(self, base_symbol: str) -> Optional[str]:
        """
        Поиск правильного имени символа с учетом суффиксов брокера
        """
        possible_suffixes = ['', 'rfd', 'm', 'f', 'q', 'a', 'b', 'c', 'd', 'e']

        for suffix in possible_suffixes:
            test_symbol = base_symbol + suffix
            if self._check_symbol_exists(test_symbol):
                return test_symbol

        # Если не нашли с суффиксами, попробуем найти похожие символы
        all_symbols = self.get_all_symbols()
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
            symbol_info = self.get_symbol_info(symbol)
            if symbol_info:
                # Пробуем получить текущую цену
                price = self.get_current_price(symbol)
                return price is not None and price.get('bid', 0) > 0
            return False
        except Exception as e:
            self.logger.debug(f"Символ {symbol} не доступен: {e}")
            return False

    def get_rates(self, symbol: str, timeframe: str, count: int = 1000,
                  start_date: Optional[datetime] = None,
                  end_date: Optional[datetime] = None) -> Optional[pd.DataFrame]:
        """
        Получает исторические данные

        Args:
            symbol: торговый символ
            timeframe: таймфрейм ('M1', 'H1', 'D1' и т.д.)
            count: количество баров
            start_date: начальная дата
            end_date: конечная дата

        Returns:
            DataFrame с данными или None в случае ошибки
        """
        try:
            if not self.mt5.check_connection():
                self.logger.error("Нет соединения с MT5")
                return None

            # Преобразуем таймфрейм
            tf = self.timeframes.get(timeframe.upper())
            if tf is None:
                self.logger.error(f"Неизвестный таймфрейм: {timeframe}")
                return None

            # Подготавливаем символ
            if not self.prepare_symbol(symbol):
                # Пробуем найти правильный символ
                correct_symbol = self.find_correct_symbol(symbol)
                if correct_symbol:
                    self.logger.info(f"🔄 Авто-исправление символа: {symbol} -> {correct_symbol}")
                    symbol = correct_symbol
                    if not self.prepare_symbol(symbol):
                        return None
                else:
                    return None

            # Получаем данные в зависимости от параметров
            if start_date and end_date:
                rates = mt5.copy_rates_range(symbol, tf, start_date, end_date)
            elif start_date:
                rates = mt5.copy_rates_from(symbol, tf, start_date, count)
            else:
                rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)

            if rates is None:
                error_code = mt5.last_error()
                self.logger.error(f"Ошибка получения данных для {symbol}: {error_code}")
                return None

            if len(rates) == 0:
                self.logger.warning(f"Нет данных для {symbol} {timeframe}")
                return None

            # Преобразуем в DataFrame
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('time', inplace=True)

            # Переименовываем колонки для удобства
            df.columns = ['open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']

            # Добавляем вычисляемые колонки
            df['price_change'] = df['close'].pct_change()
            df['price_change_abs'] = df['close'].diff()
            df['range'] = df['high'] - df['low']
            df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3

            self.logger.info(f"📊 Получено {len(df)} баров для {symbol} {timeframe}")
            return df

        except Exception as e:
            self.logger.error(f"Ошибка в get_rates для {symbol}: {str(e)}")
            return None

    def get_current_price(self, symbol: str) -> Optional[Dict]:
        """Получает текущую цену символа"""
        try:
            if not self.prepare_symbol(symbol):
                # Пробуем найти правильный символ
                correct_symbol = self.find_correct_symbol(symbol)
                if correct_symbol:
                    self.logger.info(f"🔄 Авто-исправление символа: {symbol} -> {correct_symbol}")
                    symbol = correct_symbol
                    if not self.prepare_symbol(symbol):
                        return None
                else:
                    return None

            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                self.logger.error(f"Не удалось получить тик для {symbol}")
                return None

            return {
                'bid': tick.bid,
                'ask': tick.ask,
                'last': tick.last,
                'volume': tick.volume,
                'time': pd.to_datetime(tick.time, unit='s'),
                'flags': tick.flags
            }
        except Exception as e:
            self.logger.error(f"Ошибка получения текущей цены для {symbol}: {str(e)}")
            return None

    def calculate_technical_indicators(self, df: pd.DataFrame, trading_style: str = 'positional') -> pd.DataFrame:
        """
        Расширенный расчет технических индикаторов в зависимости от стиля торговли

        Args:
            df: DataFrame с данными
            trading_style: стиль торговли ('positional', 'swing', 'scalping')

        Returns:
            DataFrame с рассчитанными индикаторами
        """
        try:
            self.logger.info(f"🎯 Расчет индикаторов для стиля: {trading_style}")

            if trading_style == 'positional':
                return self._calculate_positional_indicators(df)
            elif trading_style == 'swing':
                return self._calculate_swing_indicators(df)
            elif trading_style == 'scalping':
                return self._calculate_scalping_indicators(df)
            else:
                self.logger.warning(f"Неизвестный стиль торговли: {trading_style}. Используются базовые индикаторы.")
                return self._calculate_basic_indicators(df)

        except Exception as e:
            self.logger.error(f"Ошибка расчета индикаторов: {str(e)}")
            return df

    def _calculate_basic_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Базовые индикаторы для всех стилей"""
        try:
            # Скользящие средние (базовые)
            df['sma_20'] = df['close'].rolling(window=20).mean()
            df['sma_50'] = df['close'].rolling(window=50).mean()

            # RSI
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['rsi'] = 100 - (100 / (1 + rs))

            # ATR (Average True Range)
            high_low = df['high'] - df['low']
            high_close = np.abs(df['high'] - df['close'].shift())
            low_close = np.abs(df['low'] - df['close'].shift())
            true_range = np.maximum(np.maximum(high_low, high_close), low_close)
            df['atr'] = true_range.rolling(window=14).mean()

            # Волатильность
            df['volatility'] = df['range'].rolling(window=20).mean()

            return df

        except Exception as e:
            self.logger.error(f"Ошибка расчета базовых индикаторов: {str(e)}")
            return df

    def _calculate_positional_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Индикаторы для позиционной торговли (долгосрочной)"""
        try:
            # Базовые индикаторы
            df = self._calculate_basic_indicators(df)

            # Долгосрочные скользящие средние
            df['sma_100'] = df['close'].rolling(window=100).mean()
            df['sma_200'] = df['close'].rolling(window=200).mean()
            df['ema_50'] = df['close'].ewm(span=50).mean()
            df['ema_100'] = df['close'].ewm(span=100).mean()

            # MACD для долгосрочных трендов
            df['ema_12'] = df['close'].ewm(span=12).mean()
            df['ema_26'] = df['close'].ewm(span=26).mean()
            df['macd'] = df['ema_12'] - df['ema_26']
            df['macd_signal'] = df['macd'].ewm(span=9).mean()
            df['macd_histogram'] = df['macd'] - df['macd_signal']

            # Bollinger Bands для волатильности
            df['bb_middle'] = df['close'].rolling(window=20).mean()
            bb_std = df['close'].rolling(window=20).std()
            df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
            df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
            df['bb_width'] = df['bb_upper'] - df['bb_lower']
            df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])

            # Parabolic SAR для тренда
            df['psar'] = self._calculate_psar(df)

            # ADX для силы тренда
            df['adx'] = self._calculate_adx(df)

            # Volume-based indicators
            df['volume_sma'] = df['tick_volume'].rolling(window=20).mean()
            df['volume_ratio'] = df['tick_volume'] / df['volume_sma']

            self.logger.debug("✅ Позиционные индикаторы рассчитаны")
            return df

        except Exception as e:
            self.logger.error(f"Ошибка расчета позиционных индикаторов: {str(e)}")
            return df

    def _calculate_swing_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Индикаторы для свинг-трейдинга (среднесрочной)"""
        try:
            # Базовые индикаторы
            df = self._calculate_basic_indicators(df)

            # Среднесрочные скользящие средние
            df['sma_20'] = df['close'].rolling(window=20).mean()
            df['sma_50'] = df['close'].rolling(window=50).mean()
            df['ema_21'] = df['close'].ewm(span=21).mean()
            df['ema_34'] = df['close'].ewm(span=34).mean()
            df['ema_55'] = df['close'].ewm(span=55).mean()

            # MACD
            df['ema_12'] = df['close'].ewm(span=12).mean()
            df['ema_26'] = df['close'].ewm(span=26).mean()
            df['macd'] = df['ema_12'] - df['ema_26']
            df['macd_signal'] = df['macd'].ewm(span=9).mean()
            df['macd_histogram'] = df['macd'] - df['macd_signal']

            # Stochastic Oscillator
            df['stoch_k'], df['stoch_d'] = self._calculate_stochastic(df)

            # Williams %R
            df['williams_r'] = self._calculate_williams_r(df)

            # CCI (Commodity Channel Index)
            df['cci'] = self._calculate_cci(df)

            # Bollinger Bands
            df['bb_middle'] = df['close'].rolling(window=20).mean()
            bb_std = df['close'].rolling(window=20).std()
            df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
            df['bb_lower'] = df['bb_middle'] - (bb_std * 2)

            # Momentum
            df['momentum'] = df['close'] - df['close'].shift(10)

            # Rate of Change
            df['roc'] = ((df['close'] - df['close'].shift(10)) / df['close'].shift(10)) * 100

            self.logger.debug("✅ Свинг-индикаторы рассчитаны")
            return df

        except Exception as e:
            self.logger.error(f"Ошибка расчета свинг-индикаторов: {str(e)}")
            return df

    def _calculate_scalping_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Индикаторы для скальпинга (краткосрочной)"""
        try:
            # Базовые индикаторы
            df = self._calculate_basic_indicators(df)

            # Краткосрочные скользящие средние
            df['sma_5'] = df['close'].rolling(window=5).mean()
            df['sma_10'] = df['close'].rolling(window=10).mean()
            df['sma_20'] = df['close'].rolling(window=20).mean()
            df['ema_8'] = df['close'].ewm(span=8).mean()
            df['ema_13'] = df['close'].ewm(span=13).mean()
            df['ema_21'] = df['close'].ewm(span=21).mean()

            # Bollinger Bands для скальпинга
            df['bb_middle'] = df['close'].rolling(window=20).mean()
            bb_std = df['close'].rolling(window=20).std()
            df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
            df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
            df['bb_squeeze'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']

            # Stochastic RSI
            df['stoch_rsi'] = self._calculate_stoch_rsi(df)

            # VWAP (Volume Weighted Average Price)
            df['vwap'] = (df['typical_price'] * df['tick_volume']).cumsum() / df['tick_volume'].cumsum()

            # Momentum indicators
            df['momentum_5'] = df['close'] - df['close'].shift(5)
            df['momentum_10'] = df['close'] - df['close'].shift(10)

            # Price acceleration
            df['acceleration'] = df['momentum_5'] - df['momentum_5'].shift(1)

            # Ichimoku Cloud (упрощенная версия)
            df = self._calculate_ichimoku(df)

            # Volume-based indicators
            df['volume_ema'] = df['tick_volume'].ewm(span=20).mean()
            df['volume_ratio'] = df['tick_volume'] / df['volume_ema']

            # Spread analysis
            df['spread_ratio'] = df['spread'] / df['atr']

            self.logger.debug("✅ Скальпинг-индикаторы рассчитаны")
            return df

        except Exception as e:
            self.logger.error(f"Ошибка расчета скальпинг-индикаторов: {str(e)}")
            return df

    def _calculate_psar(self, df: pd.DataFrame, af_start: float = 0.02, af_increment: float = 0.02,
                        af_max: float = 0.2) -> pd.Series:
        """Расчет Parabolic SAR"""
        try:
            high = df['high'].values
            low = df['low'].values
            close = df['close'].values

            psar = np.zeros(len(df))
            trend = np.zeros(len(df))
            af = af_start
            ep = low[0] if close[0] > close[1] else high[0]
            sar = high[0] if close[0] > close[1] else low[0]

            for i in range(2, len(df)):
                reverse = False

                if trend[i - 1] == 1:  # uptrend
                    sar = sar + af * (ep - sar)
                    if low[i] < sar:
                        trend[i] = -1
                        sar = ep
                        af = af_start
                        ep = low[i]
                        reverse = True
                    else:
                        trend[i] = 1
                        if high[i] > ep:
                            ep = high[i]
                            af = min(af + af_increment, af_max)
                else:  # downtrend
                    sar = sar - af * (sar - ep)
                    if high[i] > sar:
                        trend[i] = 1
                        sar = ep
                        af = af_start
                        ep = high[i]
                        reverse = True
                    else:
                        trend[i] = -1
                        if low[i] < ep:
                            ep = low[i]
                            af = min(af + af_increment, af_max)

                if not reverse:
                    if trend[i] == 1:
                        sar = min(sar, low[i - 1], low[i - 2])
                    else:
                        sar = max(sar, high[i - 1], high[i - 2])

                psar[i] = sar

            return pd.Series(psar, index=df.index)

        except Exception as e:
            self.logger.error(f"Ошибка расчета PSAR: {str(e)}")
            return pd.Series(np.nan, index=df.index)

    def _calculate_adx(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Расчет ADX (Average Directional Index)"""
        try:
            high = df['high']
            low = df['low']
            close = df['close']

            # Calculate +DM and -DM
            up_move = high - high.shift(1)
            down_move = low.shift(1) - low

            plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
            minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

            # Calculate True Range
            tr1 = high - low
            tr2 = abs(high - close.shift(1))
            tr3 = abs(low - close.shift(1))
            tr = np.maximum(np.maximum(tr1, tr2), tr3)

            # Smooth the values
            plus_di = 100 * (pd.Series(plus_dm).rolling(window=period).mean() /
                             pd.Series(tr).rolling(window=period).mean())
            minus_di = 100 * (pd.Series(minus_dm).rolling(window=period).mean() /
                              pd.Series(tr).rolling(window=period).mean())

            # Calculate DX and ADX
            dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
            adx = dx.rolling(window=period).mean()

            return adx

        except Exception as e:
            self.logger.error(f"Ошибка расчета ADX: {str(e)}")
            return pd.Series(np.nan, index=df.index)

    def _calculate_stochastic(self, df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> tuple:
        """Расчет Stochastic Oscillator"""
        try:
            low_min = df['low'].rolling(window=k_period).min()
            high_max = df['high'].rolling(window=k_period).max()

            stoch_k = 100 * ((df['close'] - low_min) / (high_max - low_min))
            stoch_d = stoch_k.rolling(window=d_period).mean()

            return stoch_k, stoch_d

        except Exception as e:
            self.logger.error(f"Ошибка расчета Stochastic: {str(e)}")
            return pd.Series(np.nan, index=df.index), pd.Series(np.nan, index=df.index)

    def _calculate_williams_r(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Расчет Williams %R"""
        try:
            highest_high = df['high'].rolling(window=period).max()
            lowest_low = df['low'].rolling(window=period).min()

            williams_r = -100 * ((highest_high - df['close']) / (highest_high - lowest_low))
            return williams_r

        except Exception as e:
            self.logger.error(f"Ошибка расчета Williams %R: {str(e)}")
            return pd.Series(np.nan, index=df.index)

    def _calculate_cci(self, df: pd.DataFrame, period: int = 20) -> pd.Series:
        """Расчет CCI (Commodity Channel Index)"""
        try:
            typical_price = (df['high'] + df['low'] + df['close']) / 3
            sma = typical_price.rolling(window=period).mean()
            mad = typical_price.rolling(window=period).apply(
                lambda x: np.abs(x - x.mean()).mean(), raw=False
            )

            cci = (typical_price - sma) / (0.015 * mad)
            return cci

        except Exception as e:
            self.logger.error(f"Ошибка расчета CCI: {str(e)}")
            return pd.Series(np.nan, index=df.index)

    def _calculate_stoch_rsi(self, df: pd.DataFrame, rsi_period: int = 14, stoch_period: int = 14) -> pd.Series:
        """Расчет Stochastic RSI"""
        try:
            # Calculate RSI first
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))

            # Calculate Stochastic RSI
            rsi_min = rsi.rolling(window=stoch_period).min()
            rsi_max = rsi.rolling(window=stoch_period).max()

            stoch_rsi = (rsi - rsi_min) / (rsi_max - rsi_min)
            return stoch_rsi

        except Exception as e:
            self.logger.error(f"Ошибка расчета Stochastic RSI: {str(e)}")
            return pd.Series(np.nan, index=df.index)

    def _calculate_ichimoku(self, df: pd.DataFrame) -> pd.DataFrame:
        """Расчет упрощенного Ichimoku Cloud"""
        try:
            # Tenkan-sen (Conversion Line)
            nine_period_high = df['high'].rolling(window=9).max()
            nine_period_low = df['low'].rolling(window=9).min()
            df['tenkan_sen'] = (nine_period_high + nine_period_low) / 2

            # Kijun-sen (Base Line)
            twenty_six_period_high = df['high'].rolling(window=26).max()
            twenty_six_period_low = df['low'].rolling(window=26).min()
            df['kijun_sen'] = (twenty_six_period_high + twenty_six_period_low) / 2

            # Senkou Span A (Leading Span A)
            df['senkou_span_a'] = ((df['tenkan_sen'] + df['kijun_sen']) / 2).shift(26)

            # Simple cloud signals
            df['ichimoku_signal'] = np.where(
                df['close'] > df['senkou_span_a'], 1,
                np.where(df['close'] < df['senkou_span_a'], -1, 0)
            )

            return df

        except Exception as e:
            self.logger.error(f"Ошибка расчета Ichimoku: {str(e)}")
            return df

#!/usr/bin/env python3
"""
Модуль торговых стратегий с улучшенными индикаторами
"""

import pandas as pd
import numpy as np
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
import logging
from dataclasses import dataclass


@dataclass
class StrategyConfig:
    """Конфигурация стратегии"""
    name: str
    description: str
    risk_level: str  # LOW, MEDIUM, HIGH
    required_indicators: List[str]
    parameters: Dict[str, Any]
    confidence_threshold: float = 60.0
    timeframe: str = 'MEDIUM'


class TradingStrategy(ABC):
    """Абстрактный базовый класс для торговых стратегий"""

    def __init__(self):
        self.config = self.get_config()
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def get_config(self) -> StrategyConfig:
        """Возвращает конфигурацию стратегии"""
        pass

    @property
    def name(self):
        return self.config.name

    @property
    def description(self):
        return self.config.description

    @property
    def required_indicators(self):
        return self.config.required_indicators

    @property
    def risk_level(self):
        return self.config.risk_level

    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """Расчет всех необходимых индикаторов для стратегии"""
        try:
            df = data.copy()

            # Базовые индикаторы (RSI, SMA, EMA)
            df = self._calculate_basic_indicators(df)

            # Расширенные индикаторы
            df = self._calculate_advanced_indicators(df)

            # Стратег-специфичные индикаторы
            df = self._calculate_strategy_indicators(df)

            return df

        except Exception as e:
            self.logger.error(f"❌ Ошибка расчета индикаторов: {e}")
            return data

    def _calculate_basic_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """Расчет базовых индикаторов"""
        df = data.copy()

        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # SMA
        df['sma_20'] = df['close'].rolling(window=20).mean()
        df['sma_50'] = df['close'].rolling(window=50).mean()

        # EMA
        df['ema_12'] = df['close'].ewm(span=12).mean()
        df['ema_26'] = df['close'].ewm(span=26).mean()

        # Volatility (ATR)
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = true_range.rolling(window=14).mean()

        # Volume indicators
        if 'tick_volume' in df.columns:
            df['volume_sma'] = df['tick_volume'].rolling(window=20).mean()
            df['volume_ratio'] = df['tick_volume'] / df['volume_sma']

        return df

    def _calculate_advanced_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """Расчет расширенных индикаторов"""
        df = data.copy()

        # MACD
        exp1 = df['close'].ewm(span=12).mean()
        exp2 = df['close'].ewm(span=26).mean()
        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        df['macd_histogram'] = df['macd'] - df['macd_signal']

        # Bollinger Bands
        df['bb_middle'] = df['close'].rolling(window=20).mean()
        bb_std = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
        df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
        df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])

        # Stochastic
        low_14 = df['low'].rolling(window=14).min()
        high_14 = df['high'].rolling(window=14).max()
        df['stoch_k'] = 100 * ((df['close'] - low_14) / (high_14 - low_14))
        df['stoch_d'] = df['stoch_k'].rolling(window=3).mean()

        # Ichimoku Cloud
        df['ichi_tenkan'] = (df['high'].rolling(window=9).max() + df['low'].rolling(window=9).min()) / 2
        df['ichi_kijun'] = (df['high'].rolling(window=26).max() + df['low'].rolling(window=26).min()) / 2
        df['ichi_senkou_a'] = ((df['ichi_tenkan'] + df['ichi_kijun']) / 2).shift(26)
        df['ichi_senkou_b'] = ((df['high'].rolling(window=52).max() + df['low'].rolling(window=52).min()) / 2).shift(26)

        # Williams %R
        df['williams_r'] = (df['high'].rolling(window=14).max() - df['close']) / (
                    df['high'].rolling(window=14).max() - df['low'].rolling(window=14).min()) * -100

        # CCI (Commodity Channel Index)
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        sma_typical = typical_price.rolling(window=20).mean()
        mad = typical_price.rolling(window=20).apply(lambda x: np.abs(x - x.mean()).mean())
        df['cci'] = (typical_price - sma_typical) / (0.015 * mad)

        # ADX (Average Directional Index)
        df['adx'] = self._calculate_adx(df)

        # Parabolic SAR
        df = self._calculate_parabolic_sar(df)

        return df

    def _calculate_adx(self, data: pd.DataFrame, period: int = 14) -> pd.Series:
        """Расчет ADX"""
        try:
            high = data['high']
            low = data['low']
            close = data['close']

            # +DM и -DM
            up_move = high.diff()
            down_move = low.diff().abs() * -1

            plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
            minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

            # True Range
            tr1 = high - low
            tr2 = abs(high - close.shift())
            tr3 = abs(low - close.shift())
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

            # Сглаженные значения
            plus_di = 100 * (pd.Series(plus_dm).ewm(alpha=1 / period).mean() / tr.ewm(alpha=1 / period).mean())
            minus_di = 100 * (pd.Series(minus_dm).ewm(alpha=1 / period).mean() / tr.ewm(alpha=1 / period).mean())

            # DX и ADX
            dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
            adx = dx.ewm(alpha=1 / period).mean()

            return adx

        except Exception as e:
            self.logger.error(f"❌ Ошибка расчета ADX: {e}")
            return pd.Series([50] * len(data), index=data.index)

    def _calculate_parabolic_sar(self, df: pd.DataFrame, af_start: float = 0.02,
                                 af_increment: float = 0.02, af_max: float = 0.2) -> pd.DataFrame:
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

    @abstractmethod
    def _calculate_strategy_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """Расчет специфичных для стратегии индикаторов"""
        pass

    @abstractmethod
    def generate_signal(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Генерация торгового сигнала"""
        pass

    def get_prediction_parameters(self) -> Dict[str, Any]:
        """Возвращает параметры для предсказаний"""
        return {
            'confidence_threshold': self.config.confidence_threshold,
            'timeframe': self.config.timeframe,
            'risk_level': self.config.risk_level
        }


class SimpleMAStrategy(TradingStrategy):
    """Улучшенная стратегия на скользящих средних"""

    def get_config(self) -> StrategyConfig:
        return StrategyConfig(
            name="Улучшенная MA стратегия",
            description="Стратегия на скользящих средних с RSI, MACD и Volume фильтрами",
            risk_level="MEDIUM",
            required_indicators=['sma_20', 'sma_50', 'rsi', 'macd', 'volume_ratio', 'atr', 'adx'],
            parameters={
                'sma_short_period': 20,
                'sma_long_period': 50,
                'rsi_period': 14,
                'rsi_overbought': 70,
                'rsi_oversold': 30,
                'volume_threshold': 1.2
            },
            confidence_threshold=65.0,
            timeframe='MEDIUM'
        )

    def _calculate_strategy_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """Расчет специфичных индикаторов для MA стратегии"""
        df = data.copy()

        # Разность между MA
        df['ma_diff'] = df['sma_20'] - df['sma_50']
        df['ma_diff_pct'] = (df['ma_diff'] / df['sma_50']) * 100

        # Momentum индикатор
        df['momentum'] = df['close'] - df['close'].shift(5)

        # Price Channel
        df['price_channel_high'] = df['high'].rolling(window=20).max()
        df['price_channel_low'] = df['low'].rolling(window=20).min()
        df['price_channel_middle'] = (df['price_channel_high'] + df['price_channel_low']) / 2

        return df

    def generate_signal(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Генерация сигнала с улучшенной логикой"""
        try:
            if len(data) < 50:
                return {'signal': 'HOLD', 'strength': 0, 'description': 'Недостаточно данных'}

            latest = data.iloc[-1]
            previous = data.iloc[-2]

            # Базовые условия MA
            ma_bullish = (latest['sma_20'] > latest['sma_50'] and
                          previous['sma_20'] <= previous['sma_50'])
            ma_bearish = (latest['sma_20'] < latest['sma_50'] and
                          previous['sma_20'] >= previous['sma_50'])

            # Дополнительные фильтры
            rsi_ok = 30 < latest['rsi'] < 70
            macd_bullish = latest['macd'] > latest['macd_signal']
            volume_ok = latest.get('volume_ratio', 1) > 1.0
            adx_strong = latest.get('adx', 0) > 25  # Сильный тренд
            atr_ratio = latest.get('atr', 0) / latest['close'] < 0.02  # Нормальная волатильность

            # Расчет силы сигнала
            strength = 0
            signal_factors = []

            if ma_bullish and rsi_ok and macd_bullish:
                strength += 40
                signal_factors.append("Бычье пересечение MA")

            if volume_ok:
                strength += 20
                signal_factors.append("Высокий объем")

            if adx_strong:
                strength += 20
                signal_factors.append("Сильный тренд")

            if atr_ratio:
                strength += 10
                signal_factors.append("Нормальная волатильность")

            # Дополнительные бычьи факторы
            if latest['close'] > latest['price_channel_middle']:
                strength += 10
                signal_factors.append("Цена выше канала")

            # Генерация сигнала
            if ma_bullish and strength >= 60:
                return {
                    'signal': 'BUY',
                    'strength': min(strength, 95),
                    'description': f"BUY: {', '.join(signal_factors)}"
                }
            elif ma_bearish and strength >= 50:
                return {
                    'signal': 'SELL',
                    'strength': min(strength, 95),
                    'description': f"SELL: Медвежье пересечение MA"
                }
            else:
                return {
                    'signal': 'HOLD',
                    'strength': 0,
                    'description': 'Нет четкого сигнала'
                }

        except Exception as e:
            self.logger.error(f"❌ Ошибка генерации сигнала MA: {e}")
            return {'signal': 'HOLD', 'strength': 0, 'description': f'Ошибка: {str(e)}'}


class RSIStrategy(TradingStrategy):
    """Улучшенная стратегия на RSI"""

    def get_config(self) -> StrategyConfig:
        return StrategyConfig(
            name="Улучшенная RSI стратегия",
            description="RSI стратегия с фильтрами Bollinger Bands, MACD и Stochastic",
            risk_level="LOW",
            required_indicators=['rsi', 'bb_upper', 'bb_lower', 'macd', 'stoch_k', 'stoch_d', 'atr', 'volume_ratio'],
            parameters={
                'rsi_period': 14,
                'rsi_overbought': 70,
                'rsi_oversold': 30,
                'stoch_overbought': 80,
                'stoch_oversold': 20
            },
            confidence_threshold=70.0,
            timeframe='SHORT'
        )

    def _calculate_strategy_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """Расчет специфичных индикаторов для RSI стратегии"""
        df = data.copy()

        # RSI производные
        df['rsi_sma'] = df['rsi'].rolling(window=10).mean()
        df['rsi_trend'] = df['rsi'] - df['rsi_sma']

        # Множественные RSI периоды
        for period in [7, 21]:
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            rs = gain / loss
            df[f'rsi_{period}'] = 100 - (100 / (1 + rs))

        # RSI дивергенция (упрощенная)
        df['price_high_5'] = df['high'].rolling(window=5).max()
        df['rsi_high_5'] = df['rsi'].rolling(window=5).max()

        return df

    def generate_signal(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Генерация сигнала с улучшенной RSI логикой"""
        try:
            if len(data) < 30:
                return {'signal': 'HOLD', 'strength': 0, 'description': 'Недостаточно данных'}

            latest = data.iloc[-1]
            previous = data.iloc[-2]

            # Базовые RSI условия
            rsi_oversold = latest['rsi'] < 30
            rsi_overbought = latest['rsi'] > 70
            rsi_neutral = 40 < latest['rsi'] < 60

            # Дополнительные фильтры
            bb_position = latest.get('bb_position', 0.5)
            macd_bullish = latest['macd'] > latest['macd_signal']
            stoch_oversold = latest['stoch_k'] < 20 and latest['stoch_d'] < 20
            stoch_overbought = latest['stoch_k'] > 80 and latest['stoch_d'] > 80
            volume_ok = latest.get('volume_ratio', 1) > 0.8

            # Множественные RSI согласование
            rsi_7 = latest.get('rsi_7', 50)
            rsi_21 = latest.get('rsi_21', 50)
            rsi_aligned = (rsi_7 < 30 and rsi_21 < 40) or (rsi_7 > 70 and rsi_21 > 60)

            # Расчет силы сигнала
            strength = 0
            signal_factors = []

            # BUY сигналы
            if rsi_oversold:
                strength += 25
                signal_factors.append("RSI перепродан")

            if stoch_oversold:
                strength += 15
                signal_factors.append("Stochastic перепродан")

            if bb_position < 0.2:  # Возле нижней полосы Боллинджера
                strength += 20
                signal_factors.append("У нижней полосы Боллинджера")

            if macd_bullish:
                strength += 15
                signal_factors.append("MACD бычий")

            if rsi_aligned:
                strength += 15
                signal_factors.append("Множественные RSI согласованы")

            if volume_ok:
                strength += 10
                signal_factors.append("Объем подтверждает")

            # SELL сигналы (обратная логика)
            sell_strength = 0
            sell_factors = []

            if rsi_overbought:
                sell_strength += 25
                sell_factors.append("RSI перекуплен")

            if stoch_overbought:
                sell_strength += 15
                sell_factors.append("Stochastic перекуплен")

            if bb_position > 0.8:  # Возле верхней полосы Боллинджера
                sell_strength += 20
                sell_factors.append("У верхней полосы Боллинджера")

            if not macd_bullish:
                sell_strength += 15
                sell_factors.append("MACD медвежий")

            # Генерация финального сигнала
            if strength >= 60 and strength > sell_strength:
                return {
                    'signal': 'BUY',
                    'strength': min(strength, 90),
                    'description': f"BUY: {', '.join(signal_factors)}"
                }
            elif sell_strength >= 60 and sell_strength > strength:
                return {
                    'signal': 'SELL',
                    'strength': min(sell_strength, 90),
                    'description': f"SELL: {', '.join(sell_factors)}"
                }
            else:
                return {
                    'signal': 'HOLD',
                    'strength': 0,
                    'description': 'RSI в нейтральной зоне'
                }

        except Exception as e:
            self.logger.error(f"❌ Ошибка генерации сигнала RSI: {e}")
            return {'signal': 'HOLD', 'strength': 0, 'description': f'Ошибка: {str(e)}'}


class MACDStrategy(TradingStrategy):
    """Улучшенная стратегия на MACD"""

    def get_config(self) -> StrategyConfig:
        return StrategyConfig(
            name="Улучшенная MACD стратегия",
            description="MACD стратегия с RSI, Stochastic и Volume подтверждением",
            risk_level="MEDIUM",
            required_indicators=['macd', 'macd_signal', 'macd_histogram', 'rsi', 'stoch_k', 'stoch_d', 'volume_ratio',
                                 'atr'],
            parameters={
                'macd_fast': 12,
                'macd_slow': 26,
                'macd_signal': 9,
                'histogram_threshold': 0.001
            },
            confidence_threshold=65.0,
            timeframe='MEDIUM'
        )

    def _calculate_strategy_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """Расчет специфичных индикаторов для MACD стратегии"""
        df = data.copy()

        # Производные MACD
        df['macd_trend'] = df['macd'] - df['macd_signal']
        df['macd_momentum'] = df['macd_trend'].diff()
        df['macd_histogram_sma'] = df['macd_histogram'].rolling(window=5).mean()

        # Множественные MACD
        for fast, slow in [(6, 13), (5, 35)]:
            exp1 = df['close'].ewm(span=fast).mean()
            exp2 = df['close'].ewm(span=slow).mean()
            df[f'macd_{fast}_{slow}'] = exp1 - exp2
            df[f'macd_signal_{fast}_{slow}'] = df[f'macd_{fast}_{slow}'].ewm(span=9).mean()

        # MACD дивергенция (упрощенная)
        df['price_extremes'] = df['close'].rolling(window=10).apply(
            lambda x: 1 if x.iloc[-1] == x.max() else (-1 if x.iloc[-1] == x.min() else 0)
        )
        df['macd_extremes'] = df['macd'].rolling(window=10).apply(
            lambda x: 1 if x.iloc[-1] == x.max() else (-1 if x.iloc[-1] == x.min() else 0)
        )

        return df

    def generate_signal(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Генерация сигнала с улучшенной MACD логикой"""
        try:
            if len(data) < 35:
                return {'signal': 'HOLD', 'strength': 0, 'description': 'Недостаточно данных'}

            latest = data.iloc[-1]
            previous = data.iloc[-2]
            second_previous = data.iloc[-3] if len(data) > 2 else previous

            # Базовые MACD условия
            macd_bullish_cross = (previous['macd'] <= previous['macd_signal'] and
                                  latest['macd'] > latest['macd_signal'])
            macd_bearish_cross = (previous['macd'] >= previous['macd_signal'] and
                                  latest['macd'] < latest['macd_signal'])

            macd_histogram_rising = latest['macd_histogram'] > previous['macd_histogram']
            macd_above_zero = latest['macd'] > 0

            # Дополнительные фильтры
            rsi_ok = 40 < latest['rsi'] < 70
            stoch_ok = 20 < latest['stoch_k'] < 80
            volume_ok = latest.get('volume_ratio', 1) > 0.9
            atr_normal = latest.get('atr', 0) / latest['close'] < 0.025

            # Множественные MACD согласование
            macd_6_13 = latest.get('macd_6_13', 0)
            macd_signal_6_13 = latest.get('macd_signal_6_13', 0)
            macd_aligned = (macd_6_13 > macd_signal_6_13) == (latest['macd'] > latest['macd_signal'])

            # Расчет силы сигнала
            strength = 0
            signal_factors = []

            # BUY сигналы
            if macd_bullish_cross:
                strength += 30
                signal_factors.append("Бычье пересечение MACD")

            if macd_histogram_rising:
                strength += 15
                signal_factors.append("Гистограмма растет")

            if macd_above_zero:
                strength += 10
                signal_factors.append("MACD выше нуля")

            if rsi_ok:
                strength += 15
                signal_factors.append("RSI подтверждает")

            if stoch_ok:
                strength += 10
                signal_factors.append("Stochastic в норме")

            if volume_ok:
                strength += 10
                signal_factors.append("Объем подтверждает")

            if macd_aligned:
                strength += 10
                signal_factors.append("Множественные MACD согласованы")

            # SELL сигналы
            sell_strength = 0
            sell_factors = []

            if macd_bearish_cross:
                sell_strength += 30
                sell_factors.append("Медвежье пересечение MACD")

            if not macd_histogram_rising:
                sell_strength += 15
                sell_factors.append("Гистограмма падает")

            if not macd_above_zero:
                sell_strength += 10
                sell_factors.append("MACD ниже нуля")

            # Генерация финального сигнала
            if strength >= 60 and strength > sell_strength:
                return {
                    'signal': 'BUY',
                    'strength': min(strength, 95),
                    'description': f"BUY: {', '.join(signal_factors)}"
                }
            elif sell_strength >= 60 and sell_strength > strength:
                return {
                    'signal': 'SELL',
                    'strength': min(sell_strength, 95),
                    'description': f"SELL: {', '.join(sell_factors)}"
                }
            else:
                return {
                    'signal': 'HOLD',
                    'strength': 0,
                    'description': 'MACD не показывает четкого сигнала'
                }

        except Exception as e:
            self.logger.error(f"❌ Ошибка генерации сигнала MACD: {e}")
            return {'signal': 'HOLD', 'strength': 0, 'description': f'Ошибка: {str(e)}'}


class BollingerBandsStrategy(TradingStrategy):
    """Улучшенная стратегия на полосах Боллинджера"""

    def get_config(self) -> StrategyConfig:
        return StrategyConfig(
            name="Улучшенная Bollinger Bands стратегия",
            description="Стратегия на полосах Боллинджера с RSI, MACD и Volume",
            risk_level="HIGH",
            required_indicators=['bb_upper', 'bb_lower', 'bb_middle', 'bb_width', 'rsi', 'macd', 'volume_ratio', 'atr'],
            parameters={
                'bb_period': 20,
                'bb_std': 2,
                'squeeze_threshold': 0.05
            },
            confidence_threshold=60.0,
            timeframe='SHORT'
        )

    def _calculate_strategy_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """Расчет специфичных индикаторов для Bollinger Bands стратегии"""
        df = data.copy()

        # Percent B индикатор (ИСПРАВЛЕННАЯ СТРОКА - убран символ % в начале)
        df['percent_b'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])

        # Ширина полос (нормализованная)
        df['bb_width_pct'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle'] * 100

        # Squeeze индикатор
        df['squeeze'] = df['bb_width_pct'] < 0.5  # Узкие полосы

        # Полосы для разных периодов
        for period in [10, 50]:
            middle = df['close'].rolling(window=period).mean()
            std = df['close'].rolling(window=period).std()
            df[f'bb_upper_{period}'] = middle + (std * 2)
            df[f'bb_lower_{period}'] = middle - (std * 2)

        return df

    def generate_signal(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Генерация сигнала с улучшенной логикой Bollinger Bands"""
        try:
            if len(data) < 50:
                return {'signal': 'HOLD', 'strength': 0, 'description': 'Недостаточно данных'}

            latest = data.iloc[-1]
            previous = data.iloc[-2]

            # Базовые условия BB
            below_lower_band = latest['close'] < latest['bb_lower']
            above_upper_band = latest['close'] > latest['bb_upper']
            in_middle = latest['bb_lower'] < latest['close'] < latest['bb_upper']

            # Дополнительные фильтры
            rsi_oversold = latest['rsi'] < 35
            rsi_overbought = latest['rsi'] > 65
            macd_bullish = latest['macd'] > latest['macd_signal']
            volume_ok = latest.get('volume_ratio', 1) > 1.0
            squeeze = latest.get('squeeze', False)
            bb_width = latest.get('bb_width_pct', 1)

            # Расчет силы сигнала
            strength = 0
            signal_factors = []

            # BUY сигналы (отскок от нижней полосы)
            if below_lower_band or (in_middle and latest['percent_b'] < 0.2):
                strength += 30
                signal_factors.append("У нижней полосы Боллинджера")

            if rsi_oversold:
                strength += 20
                signal_factors.append("RSI перепродан")

            if macd_bullish:
                strength += 15
                signal_factors.append("MACD бычий")

            if volume_ok:
                strength += 15
                signal_factors.append("Объем подтверждает")

            if not squeeze and bb_width > 0.8:  # Расширяющиеся полосы
                strength += 10
                signal_factors.append("Полосы расширяются")

            # SELL сигналы (отскок от верхней полосы)
            sell_strength = 0
            sell_factors = []

            if above_upper_band or (in_middle and latest['percent_b'] > 0.8):
                sell_strength += 30
                sell_factors.append("У верхней полосы Боллинджера")

            if rsi_overbought:
                sell_strength += 20
                sell_factors.append("RSI перекуплен")

            if not macd_bullish:
                sell_strength += 15
                sell_factors.append("MACD медвежий")

            # Генерация финального сигнала
            if strength >= 60 and strength > sell_strength:
                return {
                    'signal': 'BUY',
                    'strength': min(strength, 90),
                    'description': f"BUY: {', '.join(signal_factors)}"
                }
            elif sell_strength >= 60 and sell_strength > strength:
                return {
                    'signal': 'SELL',
                    'strength': min(sell_strength, 90),
                    'description': f"SELL: {', '.join(sell_factors)}"
                }
            else:
                return {
                    'signal': 'HOLD',
                    'strength': 0,
                    'description': 'Цена в середине полос Боллинджера'
                }

        except Exception as e:
            self.logger.error(f"❌ Ошибка генерации сигнала Bollinger Bands: {e}")
            return {'signal': 'HOLD', 'strength': 0, 'description': f'Ошибка: {str(e)}'}


class AdvancedMultiStrategy(TradingStrategy):
    """Комплексная мульти-стратегия с улучшенными индикаторами"""

    def get_config(self) -> StrategyConfig:
        return StrategyConfig(
            name="Продвинутая мульти-стратегия",
            description="Комплексная стратегия с множеством индикаторов и машинным обучением",
            risk_level="LOW",
            required_indicators=['rsi', 'macd', 'bb_upper', 'bb_lower', 'stoch_k', 'stoch_d',
                                 'atr', 'adx', 'cci', 'williams_r', 'psar', 'volume_ratio'],
            parameters={
                'weight_rsi': 0.15,
                'weight_macd': 0.20,
                'weight_bb': 0.15,
                'weight_stoch': 0.10,
                'weight_trend': 0.20,
                'weight_volume': 0.10,
                'weight_volatility': 0.10
            },
            confidence_threshold=75.0,
            timeframe='LONG'
        )

    def _calculate_strategy_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """Расчет расширенных индикаторов для комплексной стратегии"""
        df = data.copy()

        # Композитный индикатор тренда
        df['trend_composite'] = (
                (df['close'] > df['sma_20']).astype(int) +
                (df['sma_20'] > df['sma_50']).astype(int) +
                (df['macd'] > df['macd_signal']).astype(int) +
                (df['adx'] > 25).astype(int)
        )

        # Индикатор волатильности
        df['volatility_index'] = df['atr'] / df['close'] * 100

        # Индикатор момента
        df['momentum_oscillator'] = (
                                            (df['rsi'] - 50) / 50 +
                                            (df['stoch_k'] - 50) / 50 +
                                            (df['cci'] / 100) +
                                            (df['williams_r'] / -100)
                                    ) / 4

        # Volume-based indicators
        if 'tick_volume' in df.columns:
            df['volume_momentum'] = df['tick_volume'] / df['volume_sma']
            df['volume_adi'] = self._calculate_adi(df)

        # Support/Resistance levels
        df['resistance'] = df['high'].rolling(window=20).max()
        df['support'] = df['low'].rolling(window=20).min()

        return df

    def _calculate_adi(self, data: pd.DataFrame) -> pd.Series:
        """Расчет Accumulation/Distribution Index"""
        try:
            clv = ((data['close'] - data['low']) - (data['high'] - data['close'])) / (data['high'] - data['low'])
            clv = clv.fillna(0)
            adi = (clv * data['tick_volume']).cumsum()
            return adi
        except:
            return pd.Series([0] * len(data), index=data.index)

    def generate_signal(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Генерация сигнала на основе множества индикаторов"""
        try:
            if len(data) < 50:
                return {'signal': 'HOLD', 'strength': 0, 'description': 'Недостаточно данных'}

            latest = data.iloc[-1]
            previous = data.iloc[-2]

            # Веса индикаторов из конфигурации
            weights = self.config.parameters

            # Оценка каждого компонента (от -1 до +1)
            components = {}

            # 1. RSI компонент
            rsi_score = 0
            if latest['rsi'] < 30:
                rsi_score = 1.0  # Сильный бычий
            elif latest['rsi'] > 70:
                rsi_score = -1.0  # Сильный медвежий
            elif 40 < latest['rsi'] < 60:
                rsi_score = 0.5 if latest['rsi'] > 50 else -0.5  # Слабый сигнал
            components['rsi'] = rsi_score

            # 2. MACD компонент
            macd_score = 0
            if latest['macd'] > latest['macd_signal'] and previous['macd'] <= previous['macd_signal']:
                macd_score = 1.0  # Бычье пересечение
            elif latest['macd'] < latest['macd_signal'] and previous['macd'] >= previous['macd_signal']:
                macd_score = -1.0  # Медвежье пересечение
            elif latest['macd'] > latest['macd_signal']:
                macd_score = 0.5  # Бычий тренд
            else:
                macd_score = -0.5  # Медвежий тренд
            components['macd'] = macd_score

            # 3. Bollinger Bands компонент
            bb_score = 0
            if latest['close'] < latest['bb_lower']:
                bb_score = 1.0  # Сильный бычий (отскок ожидается)
            elif latest['close'] > latest['bb_upper']:
                bb_score = -1.0  # Сильный медвежий (отскок ожидается)
            elif latest['bb_position'] < 0.3:
                bb_score = 0.5  # Близко к нижней полосе
            elif latest['bb_position'] > 0.7:
                bb_score = -0.5  # Близко к верхней полосе
            components['bb'] = bb_score

            # 4. Stochastic компонент
            stoch_score = 0
            if latest['stoch_k'] < 20 and latest['stoch_d'] < 20:
                stoch_score = 1.0
            elif latest['stoch_k'] > 80 and latest['stoch_d'] > 80:
                stoch_score = -1.0
            elif latest['stoch_k'] > latest['stoch_d']:
                stoch_score = 0.3
            else:
                stoch_score = -0.3
            components['stoch'] = stoch_score

            # 5. Трендовый компонент
            trend_score = 0
            if latest['trend_composite'] >= 3:
                trend_score = 1.0
            elif latest['trend_composite'] <= 1:
                trend_score = -1.0
            elif latest['adx'] > 25:
                trend_score = 0.5 if latest['psar_trend'] > 0 else -0.5
            components['trend'] = trend_score

            # 6. Volume компонент
            volume_score = 0
            volume_ratio = latest.get('volume_ratio', 1)
            if volume_ratio > 1.5:
                volume_score = 1.0 if components['trend'] > 0 else -1.0
            elif volume_ratio > 1.2:
                volume_score = 0.5 if components['trend'] > 0 else -0.5
            components['volume'] = volume_score

            # 7. Волатильность компонент
            volatility_score = 0
            volatility = latest.get('volatility_index', 1)
            if volatility < 0.5:
                volatility_score = 0.3  # Низкая волатильность - осторожный сигнал
            elif volatility > 2.0:
                volatility_score = -0.5  # Высокая волатильность - риск
            components['volatility'] = volatility_score

            # Расчет общего скора
            total_score = 0
            for component, weight in weights.items():
                if component.startswith('weight_') and component[7:] in components:
                    indicator_name = component[7:]
                    total_score += components[indicator_name] * weight

            # Конвертация скора в сигнал
            if total_score > 0.3:
                signal = 'BUY'
                strength = min(int((total_score - 0.3) / 0.7 * 100), 95)
                description = "Сильный бычий консенсус индикаторов"
            elif total_score < -0.3:
                signal = 'SELL'
                strength = min(int((abs(total_score) - 0.3) / 0.7 * 100), 95)
                description = "Сильный медвежий консенсус индикаторов"
            else:
                signal = 'HOLD'
                strength = 0
                description = "Индикаторы не показывают четкого направления"

            # Детализация факторов
            strong_factors = []
            for indicator, score in components.items():
                if abs(score) > 0.7:
                    direction = "бычий" if score > 0 else "медвежий"
                    strong_factors.append(f"{indicator.upper()} ({direction})")

            if strong_factors:
                description += f". Ключевые факторы: {', '.join(strong_factors)}"

            return {
                'signal': signal,
                'strength': strength,
                'description': description
            }

        except Exception as e:
            self.logger.error(f"❌ Ошибка генерации сигнала Advanced: {e}")
            return {'signal': 'HOLD', 'strength': 0, 'description': f'Ошибка: {str(e)}'}


# Реестр стратегий
STRATEGIES_REGISTRY = {
    'simple_ma': SimpleMAStrategy,
    'rsi': RSIStrategy,
    'macd': MACDStrategy,
    'bollinger': BollingerBandsStrategy,
    'advanced': AdvancedMultiStrategy
}


def get_available_strategies():
    """Возвращает список доступных стратегий"""
    return {
        'simple_ma': 'Улучшенная MA стратегия',
        'rsi': 'Улучшенная RSI стратегия',
        'macd': 'Улучшенная MACD стратегия',
        'bollinger': 'Улучшенная Bollinger Bands стратегия',
        'advanced': 'Продвинутая мульти-стратегия'
    }


def create_strategy(strategy_id: str) -> TradingStrategy:
    """Создает экземпляр стратегии по ID"""
    if strategy_id not in STRATEGIES_REGISTRY:
        raise ValueError(f"Стратегия '{strategy_id}' не найдена")

    return STRATEGIES_REGISTRY[strategy_id]()

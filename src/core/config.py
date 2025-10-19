import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Настройки приложения из переменных окружения"""

    # MT5 настройки
    MT5_PATH: str = os.getenv('MT5_PATH', 'C:\\Program Files\\MetaTrader 5\\terminal64.exe')
    MT5_LOGIN: int = int(os.getenv('MT5_LOGIN', '0'))
    MT5_PASSWORD: str = os.getenv('MT5_PASSWORD', '')
    MT5_SERVER: str = os.getenv('MT5_SERVER', '')

    # Стиль торговли
    TRADING_STYLE: str = os.getenv('TRADING_STYLE', 'positional')  # positional, swing, scalping

    # Торговые настройки
    RISK_PERCENT: float = float(os.getenv('RISK_PERCENT', '1.0'))
    DEFAULT_SYMBOL: str = os.getenv('DEFAULT_SYMBOL', 'EURUSD')
    DEFAULT_TIMEFRAME: str = os.getenv('DEFAULT_TIMEFRAME', 'H1')
    DEFAULT_VOLUME: float = float(os.getenv('DEFAULT_VOLUME', '0.01'))

    # Настройки стратегии
    ENABLE_STOPLOSS: bool = os.getenv('ENABLE_STOPLOSS', 'true').lower() == 'true'
    STOPLOSS_PIPS: float = float(os.getenv('STOPLOSS_PIPS', '50.0'))
    ENABLE_TAKEPROFIT: bool = os.getenv('ENABLE_TAKEPROFIT', 'true').lower() == 'true'
    TAKEPROFIT_PIPS: float = float(os.getenv('TAKEPROFIT_PIPS', '100.0'))

    # Настройки логирования
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')

    @classmethod
    def validate(cls):
        """Проверка обязательных настроек"""
        required_vars = ['MT5_LOGIN', 'MT5_PASSWORD', 'MT5_SERVER']
        missing = []

        for var in required_vars:
            value = getattr(cls, var)
            if not value:
                missing.append(var)

        if missing:
            raise ValueError(f"Отсутствуют обязательные настройки: {missing}")

        if cls.MT5_LOGIN == 0:
            raise ValueError("MT5_LOGIN не может быть 0")

        # Проверка стиля торговли
        valid_styles = ['positional', 'swing', 'scalping']
        if cls.TRADING_STYLE not in valid_styles:
            raise ValueError(f"Неверный стиль торговли. Допустимые значения: {valid_styles}")

    @classmethod
    def print_settings(cls):
        """Выводит текущие настройки (без пароля)"""
        style_descriptions = {
            'positional': 'Позиционная торговля (долгосрочная)',
            'swing': 'Свинг-трейдинг (среднесрочная)',
            'scalping': 'Скальпинг (краткосрочная)'
        }

        settings = {
            'MT5_PATH': cls.MT5_PATH,
            'MT5_LOGIN': cls.MT5_LOGIN,
            'MT5_SERVER': cls.MT5_SERVER,
            'TRADING_STYLE': f"{cls.TRADING_STYLE} ({style_descriptions.get(cls.TRADING_STYLE, 'неизвестно')})",
            'RISK_PERCENT': cls.RISK_PERCENT,
            'DEFAULT_SYMBOL': cls.DEFAULT_SYMBOL,
            'DEFAULT_TIMEFRAME': cls.DEFAULT_TIMEFRAME,
            'ENABLE_STOPLOSS': cls.ENABLE_STOPLOSS,
            'STOPLOSS_PIPS': cls.STOPLOSS_PIPS,
            'ENABLE_TAKEPROFIT': cls.ENABLE_TAKEPROFIT,
            'TAKEPROFIT_PIPS': cls.TAKEPROFIT_PIPS,
            'LOG_LEVEL': cls.LOG_LEVEL
        }

        return "\n".join([f"{k}: {v}" for k, v in settings.items()])

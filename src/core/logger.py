import logging
import sys
import os
from logging.handlers import RotatingFileHandler
from colorlog import ColoredFormatter


def setup_logger(name: str = 'AITrader', log_level: str = 'INFO', trading_style: str = 'positional') -> logging.Logger:
    """
    Настройка логгера для проекта

    Args:
        name: имя логгера
        log_level: уровень логирования
        trading_style: стиль торговли (positional, swing, scalping)

    Returns:
        Объект логгера
    """
    # Создаем папку для логов если ее нет
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Преобразуем строковый уровень в числовой
    level = getattr(logging, log_level.upper(), logging.INFO)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Проверяем, нет ли уже обработчиков
    if logger.handlers:
        return logger

    # Форматтер для файла
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Цветной форматтер для консоли
    console_formatter = ColoredFormatter(
        '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        }
    )

    # Консольный обработчик
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(console_formatter)

    # Стили торговли для имен файлов
    style_files = {
        'positional': '1_positional',
        'swing': '2_swing',
        'scalping': '3_scalping'
    }

    file_prefix = style_files.get(trading_style, 'general')

    # Файловый обработчик для полных логов (с ротацией)
    full_log_handler = RotatingFileHandler(
        f'{log_dir}/Ai_Trader_{file_prefix}_full.log',
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding='utf-8'
    )
    full_log_handler.setLevel(logging.DEBUG)  # Все уровни для полного лога
    full_log_handler.setFormatter(file_formatter)

    # Стандартный файловый обработчик
    file_handler = RotatingFileHandler(
        f'{log_dir}/ai_trader_{file_prefix}.log',
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(file_formatter)

    # Добавляем обработчики к логгеру
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.addHandler(full_log_handler)

    # Предотвращаем распространение на корневой логгер
    logger.propagate = False

    return logger


def setup_training_logger(symbol: str, timestamp: str, trading_style: str = 'positional') -> logging.Logger:
    """
    Настройка логгера для тренировочной торговли

    Args:
        symbol: торговый символ
        timestamp: временная метка
        trading_style: стиль торговли

    Returns:
        Объект логгера для тренировки
    """
    # Создаем папку для логов тестов если ее нет
    log_dir = 'Log_tests_sell'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Префикс для стиля торговли
    style_prefix = {
        'positional': '1_pos',
        'swing': '2_swing',
        'scalping': '3_scalp'
    }.get(trading_style, 'general')

    log_file = os.path.join(log_dir, f"{style_prefix}_test_{symbol}_{timestamp}.log")

    logger = logging.getLogger(f'TestTrading_{symbol}_{timestamp}')
    logger.setLevel(logging.INFO)

    # Форматтер для файла
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Файловый обработчик для тестовой торговли
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    # Добавляем обработчик
    logger.addHandler(file_handler)
    logger.propagate = False

    return logger, log_file

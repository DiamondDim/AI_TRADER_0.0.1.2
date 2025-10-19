import MetaTrader5 as mt5
import logging
from typing import Optional, Tuple

logger = logging.getLogger('MT5')


class MT5:
    def __init__(self):
        self.connected = False
        self.logger = logger

    def initialize(self, path: str = "", login: int = 0, password: str = "", server: str = "") -> Tuple[bool, str]:
        """
        Инициализирует соединение с MT5

        Args:
            path: путь к терминалу MT5
            login: номер счета
            password: пароль
            server: название сервера

        Returns:
            Tuple[bool, str]: (Успешность подключения, Сообщение об ошибке)
        """
        try:
            # Закрываем предыдущее соединение если было
            if mt5.initialize():
                mt5.shutdown()

            # Пытаемся инициализировать MT5
            if not mt5.initialize(path=path, login=login, password=password, server=server):
                error_code = mt5.last_error()
                error_msg = f"Ошибка инициализации MT5: {self._get_error_description(error_code)}"
                self.logger.error(error_msg)
                return False, error_msg

            self.connected = True
            self.logger.info("✅ Успешное подключение к MT5")

            # Выводим информацию о подключении
            account_info = mt5.account_info()
            if account_info:
                self.logger.info(f"📊 Подключен к счету: {account_info.login}, Сервер: {account_info.server}")
                self.logger.info(f"💳 Баланс: {account_info.balance:.2f} {account_info.currency}")

            return True, "Успешное подключение"

        except Exception as e:
            error_msg = f"Исключение при инициализации MT5: {str(e)}"
            self.logger.error(error_msg)
            return False, error_msg

    def _get_error_description(self, error_code: int) -> str:
        """Возвращает описание ошибки MT5"""
        error_descriptions = {
            1: "Ошибка инициализации",
            2: "Терминал не запущен",
            3: "Неверная версия терминала",
            6: "Нет соединения с сервером",
            7: "Недостаточно памяти",
            8: "Ошибка функции",
            9: "Неверные параметры",
            64: "Ошибка учетной записи",
            65: "Ошибка торговли",
            128: "Таймаут соединения",
            129: "Ошибка шифрования",
            130: "Неверный сервер",
            131: "Неверный логин",
            132: "Неверный пароль",
            133: "Пользователь не авторизован",
            134: "Слишком частые запросы",
        }
        return error_descriptions.get(error_code, f"Неизвестная ошибка: {error_code}")

    def check_connection(self) -> bool:
        """Проверяет активное соединение с MT5"""
        try:
            if not self.connected:
                return False

            # Пытаемся получить информацию об аккаунте для проверки соединения
            account_info = mt5.account_info()
            if account_info is None:
                self.connected = False
                self.logger.warning("❌ Соединение с MT5 потеряно")
                return False

            self.connected = True
            return True

        except Exception as e:
            self.logger.error(f"Ошибка проверки соединения: {str(e)}")
            self.connected = False
            return False

    def shutdown(self):
        """Закрывает соединение с MT5"""
        try:
            if self.connected:
                mt5.shutdown()
                self.connected = False
                self.logger.info("🔌 Соединение с MT5 закрыто")
        except Exception as e:
            self.logger.error(f"Ошибка при закрытии соединения: {str(e)}")

    def get_account_info(self) -> Optional[dict]:
        """Получает информацию об аккаунте"""
        try:
            if not self.check_connection():
                return None

            account_info = mt5.account_info()
            if account_info:
                return {
                    'login': account_info.login,
                    'balance': account_info.balance,
                    'equity': account_info.equity,
                    'margin': account_info.margin,
                    'free_margin': account_info.margin_free,
                    'leverage': account_info.leverage,
                    'currency': account_info.currency,
                    'server': account_info.server,
                    'name': account_info.name,
                    'company': account_info.company
                }
            return None
        except Exception as e:
            self.logger.error(f"Ошибка получения информации об аккаунте: {str(e)}")
            return None

    def __del__(self):
        """Деструктор для автоматического закрытия соединения"""
        self.shutdown()

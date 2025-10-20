import MetaTrader5 as mt5
import logging
import time
from typing import Optional, Dict, Tuple, List
from datetime import datetime

logger = logging.getLogger('Trader')


class Trader:
    def __init__(self, mt5_connection):
        self.mt5 = mt5_connection
        self.logger = logger
        self.max_retries = 3
        self.retry_delay = 1

    def _retry_operation(self, operation, *args, **kwargs):
        """Повторяет операцию в случае ошибки"""
        for attempt in range(self.max_retries):
            try:
                result = operation(*args, **kwargs)
                if result[0]:  # Если операция успешна
                    return result
                self.logger.warning(f"🔄 Попытка {attempt + 1} не удалась: {result[1]}")
            except Exception as e:
                self.logger.warning(f"🔄 Попытка {attempt + 1} вызвала исключение: {str(e)}")

            if attempt < self.max_retries - 1:
                time.sleep(self.retry_delay)

        return False, "Все попытки выполнить операцию не удались"

    def calculate_stop_levels(self, symbol: str, price: float, order_type: str,
                              stop_loss_pips: float, take_profit_pips: float) -> Tuple[float, float]:
        """
        Рассчитывает уровни стоп-лосса и тейк-профита с учетом минимальных расстояний

        Args:
            symbol: торговый символ
            price: цена входа
            order_type: тип ордера ('buy' или 'sell')
            stop_loss_pips: стоп-лосс в пунктах
            take_profit_pips: тейк-профит в пунктах

        Returns:
            Tuple[float, float]: (стоп-лосс, тейк-профит)
        """
        try:
            symbol_info = mt5.symbol_info(symbol)
            if not symbol_info:
                return 0.0, 0.0

            point = symbol_info.point
            digits = symbol_info.digits

            # Минимальные расстояния
            min_stop_level = symbol_info.trade_stops_level * point if symbol_info.trade_stops_level > 0 else 10 * point
            min_stop_distance = max(min_stop_level, 10 * point)  # Минимум 10 пунктов

            # Рассчитываем уровни в пунктах
            if order_type.lower() == 'buy':
                if stop_loss_pips > 0:
                    stop_loss = price - stop_loss_pips * point
                    # Проверяем минимальное расстояние
                    if (price - stop_loss) < min_stop_distance:
                        stop_loss = price - min_stop_distance
                        self.logger.warning(
                            f"⚠️ Стоп-лосс скорректирован до минимального расстояния: {min_stop_distance / point:.1f} пунктов")
                else:
                    stop_loss = 0.0

                if take_profit_pips > 0:
                    take_profit = price + take_profit_pips * point
                    # Проверяем минимальное расстояние
                    if (take_profit - price) < min_stop_distance:
                        take_profit = price + min_stop_distance
                        self.logger.warning(
                            f"⚠️ Тейк-профит скорректирован до минимального расстояния: {min_stop_distance / point:.1f} пунктов")
                else:
                    take_profit = 0.0

            else:  # sell
                if stop_loss_pips > 0:
                    stop_loss = price + stop_loss_pips * point
                    # Проверяем минимальное расстояние
                    if (stop_loss - price) < min_stop_distance:
                        stop_loss = price + min_stop_distance
                        self.logger.warning(
                            f"⚠️ Стоп-лосс скорректирован до минимального расстояния: {min_stop_distance / point:.1f} пунктов")
                else:
                    stop_loss = 0.0

                if take_profit_pips > 0:
                    take_profit = price - take_profit_pips * point
                    # Проверяем минимальное расстояние
                    if (price - take_profit) < min_stop_distance:
                        take_profit = price - min_stop_distance
                        self.logger.warning(
                            f"⚠️ Тейк-профит скорректирован до минимального расстояния: {min_stop_distance / point:.1f} пунктов")
                else:
                    take_profit = 0.0

            # Округляем до нужного количества знаков
            if stop_loss > 0:
                stop_loss = round(stop_loss, digits)
            if take_profit > 0:
                take_profit = round(take_profit, digits)

            self.logger.debug(f"🎯 Уровни для {symbol}: Цена={price:.5f}, SL={stop_loss:.5f}, TP={take_profit:.5f}")

            return stop_loss, take_profit

        except Exception as e:
            self.logger.error(f"❌ Ошибка расчета уровней стоп-лосса/тейк-профита: {str(e)}")
            return 0.0, 0.0

    def check_market_conditions(self, symbol: str) -> Tuple[bool, str]:
        """Проверяет условия рынка для торговли"""
        try:
            symbol_info = mt5.symbol_info(symbol)
            if not symbol_info:
                return False, f"Символ {symbol} не найден"

            # Проверяем режим торговли
            if symbol_info.trade_mode != mt5.SYMBOL_TRADE_MODE_FULL:
                return False, f"Торговля для {symbol} ограничена"

            # Проверяем доступность символа
            if not symbol_info.visible:
                return False, f"Символ {symbol} не доступен в Market Watch"

            # Проверяем спред
            tick = mt5.symbol_info_tick(symbol)
            if tick:
                spread = tick.ask - tick.bid
                point = symbol_info.point
                spread_pips = spread / point

                if spread_pips > 50:  # Если спред слишком высокий
                    return False, f"Спред слишком высокий: {spread_pips:.1f} пунктов"

            return True, "Рынок готов для торговли"

        except Exception as e:
            return False, f"Ошибка проверки условий рынка: {str(e)}"

    def calculate_position_size(self, symbol: str, risk_percent: float = 1.0,
                                stop_loss_pips: float = 0.0) -> Optional[float]:
        """Рассчитывает размер позиции на основе риска"""
        try:
            account_info = mt5.account_info()
            if not account_info:
                self.logger.error("Не удалось получить информацию об аккаунте")
                return None

            symbol_info = mt5.symbol_info(symbol)
            if not symbol_info:
                self.logger.error(f"Не удалось получить информацию о символе {symbol}")
                return None

            # Расчет доступного капитала для риска
            balance = account_info.balance
            risk_amount = balance * (risk_percent / 100.0)

            # Расчет размера лота
            if stop_loss_pips > 0:
                # Более точный расчет с учетом стоп-лосса
                point = symbol_info.point
                tick_value = symbol_info.trade_tick_value
                tick_size = symbol_info.trade_tick_size

                if tick_value > 0 and tick_size > 0:
                    risk_per_pip = risk_amount / stop_loss_pips
                    lot_size = risk_per_pip / tick_value
                else:
                    # Упрощенный расчет
                    lot_size = risk_amount / (stop_loss_pips * 10)
            else:
                # Упрощенный расчет если нет стоп-лосса
                lot_size = risk_amount / 1000.0

            # Ограничиваем размер лота минимальными и максимальными значениями
            min_lot = symbol_info.volume_min
            max_lot = symbol_info.volume_max
            step_lot = symbol_info.volume_step

            # Округляем до шага
            if step_lot > 0:
                lot_size = round(lot_size / step_lot) * step_lot

            lot_size = max(min_lot, min(lot_size, max_lot))
            lot_size = round(lot_size, 2)

            self.logger.info(f"📏 Рассчитан лот {lot_size} для {symbol} с риском {risk_percent}%")
            return lot_size

        except Exception as e:
            self.logger.error(f"Ошибка расчета размера позиции: {str(e)}")
            return None

    def send_order(self, symbol: str, order_type: str, volume: float,
                   stop_loss_pips: float = 0.0, take_profit_pips: float = 0.0,
                   deviation: int = 20, comment: str = "AI Trader") -> Tuple[bool, str]:
        """
        Отправляет ордер на рынок

        Args:
            symbol: торговый символ
            order_type: тип ордера ('buy' или 'sell')
            volume: объем в лотах
            stop_loss_pips: уровень стоп-лосса в пунктах
            take_profit_pips: уровень тейк-профита в пунктах
            deviation: максимальное отклонение цены
            comment: комментарий к ордеру

        Returns:
            Tuple[bool, str]: (Успешность, Сообщение)
        """
        return self._retry_operation(self._send_order_impl, symbol, order_type, volume,
                                     stop_loss_pips, take_profit_pips, deviation, comment)

    def _send_order_impl(self, symbol: str, order_type: str, volume: float,
                         stop_loss_pips: float = 0.0, take_profit_pips: float = 0.0,
                         deviation: int = 20, comment: str = "AI Trader") -> Tuple[bool, str]:
        """Реализация отправки ордера"""
        try:
            if not self.mt5.check_connection():
                return False, "Нет соединения с MT5"

            # Проверяем условия рынка
            market_ok, market_msg = self.check_market_conditions(symbol)
            if not market_ok:
                return False, market_msg

            # Получаем текущую цену
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return False, f"Не удалось получить цену для {symbol}"

            # Определяем параметры ордера
            symbol_info = mt5.symbol_info(symbol)
            if not symbol_info:
                return False, f"Не удалось получить информацию о символе {symbol}"

            if order_type.lower() == 'buy':
                order_type_mt5 = mt5.ORDER_TYPE_BUY
                price = tick.ask
            elif order_type.lower() == 'sell':
                order_type_mt5 = mt5.ORDER_TYPE_SELL
                price = tick.bid
            else:
                return False, f"Неизвестный тип ордера: {order_type}"

            # Рассчитываем стоп-лосс и тейк-профит
            stop_loss, take_profit = self.calculate_stop_levels(
                symbol, price, order_type, stop_loss_pips, take_profit_pips
            )

            # Проверяем, что стоп-лосс и тейк-профит не равны цене
            if stop_loss > 0 and abs(stop_loss - price) < symbol_info.point:
                return False, "Стоп-лосс слишком близко к цене открытия"

            if take_profit > 0 and abs(take_profit - price) < symbol_info.point:
                return False, "Тейк-профит слишком близко к цене открытия"

            # Подготавливаем запрос
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": order_type_mt5,
                "price": price,
                "sl": stop_loss,
                "tp": take_profit,
                "deviation": deviation,
                "magic": 202400,
                "comment": comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_FOK,
            }

            # Отправляем ордер
            result = mt5.order_send(request)

            if result.retcode != mt5.TRADE_RETCODE_DONE:
                error_msg = f"Ошибка ордера {result.retcode}: {self._get_trade_error_description(result.retcode)}"
                self.logger.error(error_msg)
                return False, error_msg

            success_msg = f"✅ Ордер выполнен: {order_type.upper()} {volume} {symbol} по цене {price:.5f}"
            if stop_loss_pips > 0:
                success_msg += f", SL: {stop_loss:.5f} ({stop_loss_pips} п.)"
            if take_profit_pips > 0:
                success_msg += f", TP: {take_profit:.5f} ({take_profit_pips} п.)"

            self.logger.info(success_msg)
            return True, success_msg

        except Exception as e:
            error_msg = f"Исключение при отправке ордера: {str(e)}"
            self.logger.error(error_msg)
            return False, error_msg

    def _get_trade_error_description(self, error_code: int) -> str:
        """Возвращает описание торговой ошибки MT5"""
        error_descriptions = {
            mt5.TRADE_RETCODE_REQUOTE: "Требуется перекотировка",
            mt5.TRADE_RETCODE_REJECT: "Ордер отклонен",
            mt5.TRADE_RETCODE_CANCEL: "Ордер отменен",
            mt5.TRADE_RETCODE_PLACED: "Ордер размещен",
            mt5.TRADE_RETCODE_DONE: "Ордер выполнен",
            mt5.TRADE_RETCODE_DONE_PARTIAL: "Ордер выполнен частично",
            mt5.TRADE_RETCODE_ERROR: "Ошибка выполнения ордера",
            mt5.TRADE_RETCODE_TIMEOUT: "Таймаут запроса",
            mt5.TRADE_RETCODE_INVALID: "Неверный запрос",
            mt5.TRADE_RETCODE_INVALID_VOLUME: "Неверный объем",
            mt5.TRADE_RETCODE_INVALID_PRICE: "Неверная цена",
            mt5.TRADE_RETCODE_INVALID_STOPS: "Неверные стоп-уровни",
            mt5.TRADE_RETCODE_TRADE_DISABLED: "Торговля запрещена",
            mt5.TRADE_RETCODE_MARKET_CLOSED: "Рынок закрыт",
            mt5.TRADE_RETCODE_NO_MONEY: "Недостаточно средств",
            mt5.TRADE_RETCODE_PRICE_CHANGED: "Цена изменилась",
            mt5.TRADE_RETCODE_PRICE_OFF: "Нет котировок",
            mt5.TRADE_RETCODE_INVALID_EXPIRATION: "Неверная дата экспирации",
            mt5.TRADE_RETCODE_ORDER_CHANGED: "Ордер изменен",
            mt5.TRADE_RETCODE_TOO_MANY_REQUESTS: "Слишком много запросов",
            mt5.TRADE_RETCODE_NO_CHANGES: "Нет изменений",
            mt5.TRADE_RETCODE_SERVER_DISABLES_AT: "Автотрейдинг запрещен",
            mt5.TRADE_RETCODE_CLIENT_DISABLES_AT: "Автотрейдинг отключен клиентом",
            mt5.TRADE_RETCODE_LOCKED: "Ордер заблокирован",
            mt5.TRADE_RETCODE_FROZEN: "Ордер заморожен",
            mt5.TRADE_RETCODE_INVALID_FILL: "Неверный тип исполнения",
            mt5.TRADE_RETCODE_CONNECTION: "Нет соединения",
            mt5.TRADE_RETCODE_ONLY_REAL: "Только реальные счета",
            mt5.TRADE_RETCODE_LIMIT_ORDERS: "Достигнут лимит ордеров",
            mt5.TRADE_RETCODE_LIMIT_VOLUME: "Достигнут лимит объема",
            mt5.TRADE_RETCODE_INVALID_ORDER: "Неверный ордер",
            mt5.TRADE_RETCODE_POSITION_CLOSED: "Позиция уже закрыта",
        }

        return error_descriptions.get(error_code, f"Неизвестная ошибка: {error_code}")

    def get_open_positions(self, symbol: str = "") -> List[Dict]:
        """Получает список открытых позиций с улучшенной обработкой ошибок"""
        try:
            positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
            if positions is None:
                return []

            if not positions:
                return []

            result = []
            for position in positions:
                try:
                    pos_data = {
                        'ticket': position.ticket,
                        'symbol': position.symbol,
                        'type': 'BUY' if position.type == mt5.ORDER_TYPE_BUY else 'SELL',
                        'volume': position.volume,
                        'open_price': position.price_open,
                        'current_price': position.price_current,
                        'sl': position.sl,
                        'tp': position.tp,
                        'profit': position.profit,
                        'swap': position.swap,
                        'time': datetime.fromtimestamp(position.time)
                    }
                    result.append(pos_data)
                except AttributeError as e:
                    self.logger.warning(f"⚠️ Ошибка получения атрибута позиции: {e}")
                    continue
                except Exception as e:
                    self.logger.warning(f"⚠️ Ошибка обработки позиции: {e}")
                    continue

            return result

        except Exception as e:
            self.logger.error(f"❌ Ошибка получения позиций: {str(e)}")
            return []

    def close_position(self, ticket: int, deviation: int = 20) -> Tuple[bool, str]:
        """Закрывает позицию по ticket"""
        return self._retry_operation(self._close_position_impl, ticket, deviation)

    def _close_position_impl(self, ticket: int, deviation: int = 20) -> Tuple[bool, str]:
        """Реализация закрытия позиции"""
        try:
            positions = mt5.positions_get(ticket=ticket)
            if not positions:
                return False, f"Позиция с ticket {ticket} не найдена"

            position = positions[0]
            symbol = position.symbol
            volume = position.volume
            order_type = position.type

            # Определяем тип закрывающей сделки
            if order_type == mt5.ORDER_TYPE_BUY:
                close_type = mt5.ORDER_TYPE_SELL
                price = mt5.symbol_info_tick(symbol).bid
            else:
                close_type = mt5.ORDER_TYPE_BUY
                price = mt5.symbol_info_tick(symbol).ask

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "position": ticket,
                "symbol": symbol,
                "volume": volume,
                "type": close_type,
                "price": price,
                "deviation": deviation,
                "magic": 202400,
                "comment": "Closed by AI Trader",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_FOK,
            }

            result = mt5.order_send(request)

            if result.retcode != mt5.TRADE_RETCODE_DONE:
                error_msg = f"Ошибка закрытия позиции: {self._get_trade_error_description(result.retcode)}"
                return False, error_msg

            return True, f"✅ Позиция {ticket} закрыта по цене {price:.5f}"

        except Exception as e:
            error_msg = f"Исключение при закрытии позиции: {str(e)}"
            self.logger.error(error_msg)
            return False, error_msg

    def close_all_positions(self, symbol: str = "") -> Tuple[bool, str]:
        """Закрывает все открытые позиции"""
        try:
            positions = self.get_open_positions(symbol)
            if not positions:
                return True, "Нет открытых позиций для закрытия"

            results = []
            for position in positions:
                success, message = self.close_position(position['ticket'])
                results.append(f"Position {position['ticket']}: {message}")
                time.sleep(0.1)  # Небольшая задержка между запросами

            return True, " | ".join(results)

        except Exception as e:
            error_msg = f"Ошибка при закрытии всех позиций: {str(e)}"
            self.logger.error(error_msg)
            return False, error_msg

    def get_account_summary(self) -> Dict:
        """Получает сводку по аккаунту"""
        try:
            account_info = self.mt5.get_account_info()
            positions = self.get_open_positions()

            total_profit = sum(pos['profit'] + pos['swap'] for pos in positions)
            total_volume = sum(pos['volume'] for pos in positions)

            return {
                'account_info': account_info,
                'open_positions': len(positions),
                'total_profit': total_profit,
                'total_volume': total_volume,
                'positions_by_symbol': {pos['symbol']: pos['volume'] for pos in positions}
            }
        except Exception as e:
            self.logger.error(f"Ошибка получения сводки: {str(e)}")
            return {}

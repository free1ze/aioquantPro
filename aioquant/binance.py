# -*- coding:utf-8 -*-

"""
Binance Trade module.
https://github.com/binance-exchange/binance-official-api-docs/blob/master/rest-api.md

Author: HuangTao
Date:   2018/08/09
Email:  huangtao@ifclover.com
"""

import json
import copy
import hmac
import hashlib
from urllib.parse import urljoin

from aioquant.error import Error
from aioquant.utils import tools
from aioquant.utils import logger
from aioquant.order import Order
from aioquant.tasks import SingleTask, LoopRunTask
from aioquant.utils.decorator import async_method_locker
from aioquant.order import ORDER_ACTION_SELL, ORDER_ACTION_BUY, ORDER_TYPE_LIMIT, ORDER_TYPE_MARKET
from aioquant.order import ORDER_STATUS_SUBMITTED, ORDER_STATUS_PARTIAL_FILLED, ORDER_STATUS_FILLED, \
    ORDER_STATUS_CANCELED, ORDER_STATUS_FAILED

from aioquant.event import *
from aioquant.market import *

from binance.websocket.spot.websocket_stream import SpotWebsocketStreamClient
from binance.spot import Spot

class Binance:
    """Binance Trade module. You can initialize trade object with some attributes in kwargs.

    Attributes:
        account: Account name for this trade exchange.
        strategy: What's name would you want to created for your strategy.
        symbol: Symbol name for your trade.
        host: HTTP request host. (default "https://api.binance.com")
        wss: Websocket address. (default "wss://stream.binance.com:9443")
        access_key: Account's ACCESS KEY.
        secret_key Account's SECRET KEY.
        order_update_callback: You can use this param to specify a async callback function when you initializing Trade
            module. `order_update_callback` is like `async def on_order_update_callback(order: Order): pass` and this
            callback function will be executed asynchronous when some order state updated.
        init_callback: You can use this param to specify a async callback function when you initializing Trade
            module. `init_callback` is like `async def on_init_callback(success: bool, **kwargs): pass`
            and this callback function will be executed asynchronous after Trade module object initialized done.
        error_callback: You can use this param to specify a async callback function when you initializing Trade
            module. `error_callback` is like `async def on_error_callback(error: Error, **kwargs): pass`
            and this callback function will be executed asynchronous when some error occur while trade module is running.
    """

    def __init__(self, **kwargs):
        """Initialize Trade module."""
        e = None
        if not kwargs.get("account"):
            e = Error("param account miss")
        # if not kwargs.get("strategy"):
        #     e = Error("param strategy miss")
        if not kwargs.get("symbol"):
            e = Error("param symbol miss")
        if not kwargs.get("interval"):
            e = Error("param interval miss")
        if not kwargs.get("testnet"):
            kwargs["testnet"] = False
        if not kwargs.get("host"):
            kwargs["host"] = "https://api.binance.com"
        if not kwargs.get("wss"):
            kwargs["wss"] = "wss://stream.binance.com:9443"
        if not kwargs.get("access_key"):
            e = Error("param access_key miss")
        if not kwargs.get("secret_key"):
            e = Error("param secret_key miss")
        if e:
            logger.error(e, caller=self)
            SingleTask.run(kwargs["error_callback"], e)
            SingleTask.run(kwargs["init_callback"], False)

        self._account = kwargs["account"]
        self._strategy = kwargs["strategy"]
        self._platform = kwargs["platform"]
        self._symbol = kwargs["symbol"]
        self._interval = kwargs["interval"]
        self._host = kwargs["host"]
        self._wss = kwargs["wss"]
        self._access_key = kwargs["access_key"]
        self._secret_key = kwargs["secret_key"]
        self._order_update_callback = kwargs.get("order_update_callback")
        self._init_callback = kwargs.get("init_callback")
        self._error_callback = kwargs.get("error_callback")
        self._use_testnet = True if kwargs["testnet"] == True else False
        
        if self._use_testnet:
            logger.info("Using testnet", caller=self)
            self._host = "https://testnet.binance.vision"
            self._wss = "wss://testnet.binance.vision"

        self._raw_symbol = self._symbol.replace("/", "")  # Row symbol name, same as Binance Exchange.
        self._assets = {}  # Asset data. e.g. {"BTC": {"free": "1.1", "locked": "2.2", "total": "3.3"}, ... }
        self._orders = {}  # Order data. e.g. {order_no: order, ... }

        SingleTask.run(self._init_client)
        SingleTask.run(self._init_websocket)
        # self._client = Spot(api_key=self._access_key, api_secret=self._secret_key, base_url=self._host)
        # self._ws = SpotWebsocketStreamClient(on_message=self.process, on_open=self.connected_callback, stream_url=self._wss)
        # self._ws.book_ticker(symbol=self._raw_symbol)
        
    async def _init_client(self):
        self._client = Spot(api_key=self._access_key, api_secret=self._secret_key, base_url=self._host)
        
    async def _init_websocket(self):
        self._ws = SpotWebsocketStreamClient(on_message=self.process, on_open=self.connected_callback, stream_url=self._wss)
        # self._ws.book_ticker(symbol=self._raw_symbol)
        self._ws.kline(symbol=self._raw_symbol, interval=self._interval)
        
    def connected_callback(self, *args, **kwargs):
        """After websocket connection created successfully, pull back all open order information."""
        logger.info("Websocket connection authorized successfully.", caller=self)
        order_infos, error = self._client.get_open_orders(self._raw_symbol)
        if error:
            e = Error("get open orders error: {}".format(error))
            SingleTask.run(self._error_callback, e)
            SingleTask.run(self._init_callback, False)
            return

        # logger.info("SHX_DEBUG order",order_infos, caller=self)
        for order_info in order_infos:
            if order_info["status"] == "NEW":
                status = ORDER_STATUS_SUBMITTED
            elif order_info["status"] == "PARTIALLY_FILLED":
                status = ORDER_STATUS_PARTIAL_FILLED
            elif order_info["status"] == "FILLED":
                status = ORDER_STATUS_FILLED
            elif order_info["status"] == "CANCELED":
                status = ORDER_STATUS_CANCELED
            elif order_info["status"] == "REJECTED":
                status = ORDER_STATUS_FAILED
            elif order_info["status"] == "EXPIRED":
                status = ORDER_STATUS_FAILED
            else:
                logger.warn("unknown status:", order_info, caller=self)
                SingleTask.run(self._error_callback, "order status error.")
                continue

            order_id = str(order_info["orderId"])
            info = {
                "platform": self._platform,
                "account": self._account,
                "strategy": self._strategy,
                "order_id": order_id,
                "client_order_id": order_info["clientOrderId"],
                "action": ORDER_ACTION_BUY if order_info["side"] == "BUY" else ORDER_ACTION_SELL,
                "order_type": ORDER_TYPE_LIMIT if order_info["type"] == "LIMIT" else ORDER_TYPE_MARKET,
                "symbol": self._symbol,
                "price": order_info["price"],
                "quantity": order_info["origQty"],
                "remain": float(order_info["origQty"]) - float(order_info["executedQty"]),
                "status": status,
                "ctime": order_info["time"],
                "utime": order_info["updateTime"]
            }
            order = Order(**info)
            self._orders[order_id] = order
            SingleTask.run(self._order_update_callback, copy.copy(order))

        SingleTask.run(self._init_callback, True)

    # async def create_order(self, side, type, price, quantity, *args, **kwargs):
    #     """Create an order.

    #     Args:
    #         action: Trade direction, `BUY` or `SELL`.
    #         price: Price of each order.
    #         quantity: The buying or selling quantity.

    #     Returns:
    #         order_id: Order id if created successfully, otherwise it's None.
    #         error: Error information, otherwise it's None.
    #     """
    #     client_order_id = kwargs["client_order_id"]
    #     if type == "MARKET" and price != None:
    #         logger.error("Market type with Price not working", caller=self)
    #     params = {
    #         "symbol": self._raw_symbol,
    #         "side": side,
    #         "type": type,
    #         "price": price,
    #         "quantity": quantity,
    #     }
    #     result, error = await self._client.create_order(**params)
    #     if error:
    #         SingleTask.run(self._error_callback, error)
    #         return None, error
    #     order_id = str(result["orderId"])
    #     return order_id, None

    # async def revoke_order(self, *order_ids):
    #     """Revoke (an) order(s).

    #     Args:
    #         order_ids: Order id list, you can set this param to 0 or multiple items. If you set 0 param, you can cancel
    #             all orders for this symbol(initialized in Trade object). If you set 1 param, you can cancel an order.
    #             If you set multiple param, you can cancel multiple orders. Do not set param length more than 100.

    #     Returns:
    #         Success or error, see bellow.
    #     """
    #     # If len(order_nos) == 0, you will cancel all orders for this symbol(initialized in Trade object).
    #     if len(order_ids) == 0:
    #         order_infos, error = await self._client.get_open_orders(self._raw_symbol)
    #         if error:
    #             SingleTask.run(self._error_callback, error)
    #             return False, error
    #         for order_info in order_infos:
    #             _, error = await self._client.cancel_order(self._raw_symbol, orderId=order_info["orderId"])
    #             if error:
    #                 SingleTask.run(self._error_callback, error)
    #                 return False, error
    #         return True, None

    #     # If len(order_nos) == 1, you will cancel an order.
    #     if len(order_ids) == 1:
    #         success, error = await self._client.cancel_order(self._raw_symbol, orderId=order_ids[0])
    #         if error:
    #             SingleTask.run(self._error_callback, error)
    #             return order_ids[0], error
    #         else:
    #             return order_ids[0], None

    #     # If len(order_nos) > 1, you will cancel multiple orders.
    #     if len(order_ids) > 1:
    #         success, error = [], []
    #         for order_id in order_ids:
    #             _, e = await self._client.cancel_order(self._raw_symbol, orderId=order_id)
    #             if e:
    #                 SingleTask.run(self._error_callback, e)
    #                 error.append((order_id, e))
    #             else:
    #                 success.append(order_id)
    #         return success, error

    # async def get_open_order_ids(self):
    #     """Get open order id list.
    #     """
    #     success, error = await self._client.get_open_orders(self._raw_symbol)
    #     if error:
    #         SingleTask.run(self._error_callback, error)
    #         return None, error
    #     else:
    #         order_ids = []
    #         for order_info in success:
    #             order_id = str(order_info["orderId"])
    #             order_ids.append(order_id)
    #         return order_ids, None
    
    # @async_method_locker("BinanceTrade.process.locker")
    def process(self, manager, msg):
        """Process message that received from Websocket connection.

        Args:
            msg: message received from Websocket connection.
        """
        msg = json.loads(msg)
        logger.debug("msg:", json.dumps(msg), caller=self)
        e = msg.get("e")
        if e == "executionReport":
            self.process_order(msg)
        elif e == "kline":
            self.process_kline(msg)
    
    # @async_method_locker("BinanceTrade.process_order.locker")
    def process_order(self, msg):
        if msg["s"] != self._raw_symbol:
                return
        order_id = str(msg["i"])
        if msg["X"] == "NEW":
            status = ORDER_STATUS_SUBMITTED
        elif msg["X"] == "PARTIALLY_FILLED":
            status = ORDER_STATUS_PARTIAL_FILLED
        elif msg["X"] == "FILLED":
            status = ORDER_STATUS_FILLED
        elif msg["X"] == "CANCELED":
            status = ORDER_STATUS_CANCELED
        elif msg["X"] == "REJECTED":
            status = ORDER_STATUS_FAILED
        elif msg["X"] == "EXPIRED":
            status = ORDER_STATUS_FAILED
        else:
            logger.warn("unknown status:", msg, caller=self)
            SingleTask.run(self._error_callback, "order status error.")
            return
        order = self._orders.get(order_id)
        if not order:
            info = {
                "platform": self._platform,
                "account": self._account,
                "strategy": self._strategy,
                "order_id": order_id,
                "client_order_id": msg["c"],
                "action": ORDER_ACTION_BUY if msg["S"] == "BUY" else ORDER_ACTION_SELL,
                "order_type": ORDER_TYPE_LIMIT if msg["o"] == "LIMIT" else ORDER_TYPE_MARKET,
                "symbol": self._symbol,
                "price": msg["p"],
                "quantity": msg["q"],
                "ctime": msg["O"]
            }
            order = Order(**info)
            self._orders[order_id] = order
        order.remain = float(msg["q"]) - float(msg["z"])
        order.status = status
        order.utime = msg["T"]
        SingleTask.run(self._order_update_callback, copy.copy(order))

        if status in [ORDER_STATUS_FAILED, ORDER_STATUS_CANCELED, ORDER_STATUS_FILLED]:
            self._orders.pop(order_id)

    # @async_method_locker("BinanceTrade.process_kline.locker")
    def process_kline(self, msg):
        kline = Kline(self._raw_symbol).load_smart(msg["k"])
        EventKline(kline).publish()

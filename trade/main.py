# -*- coding:utf-8 -*-

import sys
import os
import argparse

from aioquant import quant
from aioquant.utils import logger
from aioquant.configure import config
from aioquant.binance import Binance

trader = None

def parse_args():
    parser = argparse.ArgumentParser(description='Process some .')
    parser.add_argument('--config', type=str, help='config file')
    parser.add_argument('--key', type=str, help='key file')

    args = parser.parse_args()
    return args

def initialize():
    cc = {
        "strategy": "my_strategy",
        "platform": "binance",
        "symbol": config.symbol,
        "account": config.account,
        "access_key": config.keys["binance"]["access_key"],
        "secret_key": config.keys["binance"]["secret_key"],
        "testnet": config.testnet,
        "interval": "1s",
    }
    if config.testnet:
        cc["access_key"] = config.keys["testnet"]["access_key"]
        cc["secret_key"] = config.keys["testnet"]["secret_key"]
        
    global trader 
    trader = Binance(**cc)
    
    from monitor.pricewatcher import PriceWatcher 
    PriceWatcher()
    
def close_connection():
    trader._ws.stop()

if __name__ == "__main__":
    args = parse_args()
    config_file = args.config
    key_file = args.key
    quant.start(
        config_file=config_file, 
        key_file=key_file,
        entrance_func=initialize,
        stop_func=close_connection)

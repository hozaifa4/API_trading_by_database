import ccxt
import sqlite3
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(filename)s] - %(message)s')

DATA_DIR = Path("data")
DB_FILE = DATA_DIR / 'balance.db'

EXCHANGES = {
    'binance': {'apiKey': os.getenv('BINANCE_API_KEY'), 'secret': os.getenv('BINANCE_SECRET_KEY')},
    'bybit': {'apiKey': os.getenv('BYBIT_API_KEY'), 'secret': os.getenv('BYBIT_SECRET_KEY')},
    'kucoin': {'apiKey': os.getenv('KUCOIN_API_KEY'), 'secret': os.getenv('KUCOIN_SECRET_KEY'), 'password': os.getenv('KUCOIN_API_PASSWORD')},
    'mexc': {'apiKey': os.getenv('MEXC_API_KEY'), 'secret': os.getenv('MEXC_SECRET_KEY')}
}

def main():
    """Fetches USDT balances from exchanges and stores them in the database."""
    logging.info("--- Starting Balance Scan ---")
    DATA_DIR.mkdir(exist_ok=True)
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS balances (exchange TEXT PRIMARY KEY, balance REAL)')
        cursor.execute('DELETE FROM balances')

        for name, config in EXCHANGES.items():
            if not config.get('apiKey'):
                logging.warning(f"API keys for {name.upper()} not found. Skipping.")
                continue
            try:
                exchange = getattr(ccxt, name)(config)
                balance_info = exchange.fetch_balance()
                usdt_balance = balance_info.get('USDT', {}).get('total', 0.0)
                cursor.execute('INSERT INTO balances (exchange, balance) VALUES (?, ?)', (name, usdt_balance))
                conn.commit()
                logging.info(f"Fetched balance for {name.upper()}: {usdt_balance:.2f} USDT")
            except Exception as e:
                logging.error(f"Could not fetch balance from {name.upper()}: {e}")
        
        conn.close()
    except Exception as e:
        logging.error(f"A database error occurred: {e}")
    logging.info("--- Balance Scan Finished ---")

if __name__ == '__main__':
    main()
import ccxt
import sqlite3
import logging
from pathlib import Path

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(filename)s] - %(message)s')

DATA_DIR = Path("data")
DB_FILE = DATA_DIR / 'listings.db'
EXCHANGES = ['binance', 'bybit', 'kucoin', 'mexc']

def main():
    """Fetches all USDT pairs from exchanges and stores them in the database."""
    logging.info("--- Starting Listings Scan ---")
    DATA_DIR.mkdir(exist_ok=True)
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS listings (exchange TEXT, symbol TEXT, PRIMARY KEY(exchange, symbol))')
        cursor.execute('DELETE FROM listings')
        
        for name in EXCHANGES:
            try:
                exchange = getattr(ccxt, name)()
                markets = exchange.load_markets()
                pairs = [(name, s) for s in markets if s.endswith('/USDT')]
                cursor.executemany('INSERT OR IGNORE INTO listings (exchange, symbol) VALUES (?, ?)', pairs)
                conn.commit()
                logging.info(f"Stored {len(pairs)} pairs from {name.upper()}.")
            except Exception as e:
                logging.error(f"Could not fetch from {name.upper()}: {e}")
        conn.close()
    except Exception as e:
        logging.error(f"A database error occurred: {e}")
    logging.info("--- Listings Scan Finished ---")

if __name__ == '__main__':
    main()
# trader_bot.py (চূড়ান্ত সংস্করণ - Polling with Timeout সমাধান সহ)

import json
import sqlite3
import logging
import ccxt
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# .env ফাইল থেকে এনভায়রনমেন্ট ভেরিয়েবল লোড করা
load_dotenv()

# --- মৌলিক সেটআপ ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(filename)s] - %(message)s')

DATA_DIR = Path("data")
LISTINGS_DB = DATA_DIR / 'listings.db'
BALANCE_DB = DATA_DIR / 'balance.db'
PORTFOLIO_DB = DATA_DIR / 'portfolio.db'

# --- ট্রেডিং ক্লাস ---
class SimulationTrader:
    """একটি নকল ট্রেডার যা শুধু দেখায় কী ট্রেড করা হতো, কিন্তু আসল ট্রেড করে না।"""
    def execute_trade(self, exchange, coin, amount, profit_margin):
        message = (f"✅ [SIMULATION] Trade Executed!\n\n"
                   f"Coin: {coin}\n"
                   f"Exchange: {exchange.upper()}\n"
                   f"Amount: ${amount} USDT\n\n"
                   f"A Market BUY order and a Limit SELL order at +{profit_margin}% would be placed now.")
        logging.info(message)
        return True, message

class LiveTrader:
    """আসল ট্রেডার যা ট্রেডের পর inteligent polling ব্যবহার করে ব্যালেন্স চেক করে।"""
    def get_exchange_instance(self, exchange_name):
        config = {
            'apiKey': os.getenv(f"{exchange_name.upper()}_API_KEY"),
            'secret': os.getenv(f"{exchange_name.upper()}_SECRET_KEY"),
        }
        if exchange_name == 'kucoin':
            config['password'] = os.getenv('KUCOIN_API_PASSWORD')
        
        if not config['apiKey'] or not config['secret']:
            raise ValueError(f"API credentials for {exchange_name.upper()} not found.")
        
        if exchange_name == 'bybit':
            config['options'] = {'defaultType': 'spot'}

        exchange = getattr(ccxt, exchange_name)(config)
        return exchange

    def execute_trade(self, exchange_name, coin_symbol, amount_usdt, profit_margin):
        logging.info(f"[LIVE MODE] ---> Executing trade on {exchange_name.upper()} for {coin_symbol}.")
        try:
            exchange = self.get_exchange_instance(exchange_name)
            base_currency = coin_symbol.split('/')[0]

            # ধাপ ১: মার্কেট বাই অর্ডার দেওয়া
            ticker = exchange.fetch_ticker(coin_symbol)
            current_price = ticker['last']
            if current_price == 0:
                raise Exception("Current price is zero, cannot calculate trade amount.")
            
            amount_to_buy = amount_usdt / current_price
            logging.info(f"Placing Market BUY order for ~{amount_to_buy:.8f} {coin_symbol}.")
            buy_order = exchange.create_market_buy_order(coin_symbol, amount_to_buy)
            logging.info(f"Market BUY order sent. Details: {buy_order}")

            # ধাপ ২: ব্যালেন্স সেটেল হওয়ার জন্য পোলিং করে অপেক্ষা
            amount_to_sell = 0
            max_wait_time = 15  # সর্বোচ্চ ১৫ সেকেন্ড অপেক্ষা করবে
            start_time = time.time()
            
            logging.info(f"Polling for {base_currency} balance to settle (max {max_wait_time} seconds)...")
            while time.time() - start_time < max_wait_time:
                updated_balance = exchange.fetch_balance()
                free_balance = updated_balance.get(base_currency, {}).get('free', 0.0)
                
                if free_balance and free_balance > 0:
                    amount_to_sell = free_balance
                    logging.info(f"Balance settled! Available to sell: {amount_to_sell:.8f} {base_currency}")
                    break
                
                time.sleep(1)
            
            if amount_to_sell == 0:
                raise Exception(f"Balance for {base_currency} did not settle after {max_wait_time} seconds.")

            # ধাপ ৩: সেলিং প্রাইস নির্ধারণ করা
            # আমরা বাই অর্ডারের সময়ের মূল্যটিই ব্যবহার করছি একটি আনুমানিক গড় মূল্য হিসেবে
            sell_price = current_price * (1 + profit_margin / 100)
            logging.info(f"Placing Limit SELL order for {amount_to_sell:.8f} {coin_symbol} at price {sell_price:.8f}")
            
            # ধাপ ৪: লিমিট সেল অর্ডার দেওয়া
            params = {}
            if exchange_name == 'bybit':
                params['category'] = 'spot'
            sell_order = exchange.create_limit_sell_order(coin_symbol, amount_to_sell, sell_price, params)
            logging.info(f"Limit SELL order successful: {sell_order['id']}")
            
            success_message = (f"🚀 [LIVE] Trade Successful!\n\n"
                               f"Bought & Selling: {amount_to_sell:.6f} {base_currency}\n"
                               f"On: {exchange_name.upper()}\n\n"
                               f"Sell order placed at ${sell_price:.6f}")
            return True, success_message

        except Exception as e:
            error_message = f"❌ [LIVE MODE] Trade failed: {e}"
            logging.error(error_message, exc_info=True)
            return False, error_message

# --- প্রধান ট্রেডার বট ক্লাস ---
class TraderBot:
    def __init__(self, config_path='config.json'):
        self.config = self.load_config(config_path)
        self.trader = self.get_trader()
        self.initialize_databases()
        self.cache = {}
        self.load_data_to_cache()

    def load_config(self, path):
        with open(path, 'r') as f: return json.load(f)

    def get_trader(self):
        if self.config['mode'] == 'simulation':
            return SimulationTrader()
        return LiveTrader()

    def initialize_databases(self):
        DATA_DIR.mkdir(exist_ok=True)
        for db_path in [LISTINGS_DB, BALANCE_DB, PORTFOLIO_DB]:
            try:
                conn = sqlite3.connect(db_path)
                if db_path == PORTFOLIO_DB:
                    conn.cursor().execute('CREATE TABLE IF NOT EXISTS portfolio (coin TEXT PRIMARY KEY, buy_timestamp TEXT NOT NULL)')
                conn.close()
            except Exception as e:
                logging.error(f"Could not initialize database {db_path}: {e}")

    def load_data_to_cache(self):
        try:
            conn_listings = sqlite3.connect(LISTINGS_DB)
            self.cache['listings'] = conn_listings.cursor().execute("SELECT exchange, symbol FROM listings").fetchall()
            conn_listings.close()
            conn_balances = sqlite3.connect(BALANCE_DB)
            self.cache['balances'] = conn_balances.cursor().execute("SELECT exchange, balance FROM balances").fetchall()
            conn_balances.close()
            logging.info("Databases loaded into in-memory cache successfully.")
            return "✅ Cache reloaded successfully."
        except Exception as e:
            logging.error(f"Failed to load databases into cache: {e}")
            return f"❌ Error: Failed to reload cache. Reason: {e}"

    def is_coin_in_cooldown(self, coin):
        conn = sqlite3.connect(PORTFOLIO_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT buy_timestamp FROM portfolio WHERE coin=?", (coin,))
        result = cursor.fetchone()
        conn.close()
        if result:
            last_buy_time = datetime.fromisoformat(result[0])
            cooldown_end_time = last_buy_time + timedelta(hours=self.config['cooldown_period_hours'])
            if datetime.now() < cooldown_end_time:
                return True, f"❄️ Cooldown Active for {coin}.\nAvailable after {cooldown_end_time.strftime('%Y-%m-%d %H:%M')}"
        return False, ""

    async def find_trade_opportunity(self, coin, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        await context.bot.send_message(chat_id=chat_id, text=f"🔍 Analyzing {coin.upper()}...")

        self.load_data_to_cache()
        coin_symbol = f"{coin.upper()}/USDT"
        
        in_cooldown, msg = self.is_coin_in_cooldown(coin_symbol)
        if in_cooldown: return msg

        exchanges_with_balance = [ex for ex, bal in self.cache.get('balances', []) if bal >= self.config['trade_amount_usdt']]
        if not exchanges_with_balance: return f"⚠️ No exchange has sufficient balance (>= ${self.config['trade_amount_usdt']})."

        exchanges_with_listing = [ex for ex, sym in self.cache.get('listings', []) if sym == coin_symbol]
        if not exchanges_with_listing: return f"❓ {coin_symbol} is not listed on any of our tracked exchanges."

        possible_exchanges = set(exchanges_with_balance) & set(exchanges_with_listing)
        if not possible_exchanges: return f"❌ No trade opportunity for {coin_symbol}.\n\nBalance on: {exchanges_with_balance}\nListed on: {exchanges_with_listing}"

        target_exchange = next((ex for ex in self.config['exchange_priority'] if ex in possible_exchanges), None)
        if not target_exchange: return "Logic error: No priority match."
        
        logging.info(f"Decision: {target_exchange.upper()} selected for {coin_symbol}.")
        await context.bot.send_message(chat_id=chat_id, text=f"⚡️ Opportunity found on {target_exchange.upper()}! Attempting trade...")

        success, trade_message = self.trader.execute_trade(
            target_exchange, coin_symbol, self.config['trade_amount_usdt'], self.config['profit_margin_percent']
        )
        
        if success: self.update_portfolio(coin_symbol)
        return trade_message

    def update_portfolio(self, coin):
        conn = sqlite3.connect(PORTFOLIO_DB)
        conn.cursor().execute("REPLACE INTO portfolio (coin, buy_timestamp) VALUES (?, ?)", (coin, datetime.now().isoformat()))
        conn.commit()
        conn.close()

# --- টেলিগ্রাম ফাংশন ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Solo Trader Bot is online. Post a coin symbol in the channel to begin analysis.")

async def reload_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_instance = context.bot_data['bot_instance']
    message = bot_instance.load_data_to_cache()
    await update.message.reply_text(message)

async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    coin_name = update.channel_post.text.strip()
    logging.info(f"Received '{coin_name}' from channel.")
    bot_instance = context.bot_data['bot_instance']
    final_message = await bot_instance.find_trade_opportunity(coin_name, update, context)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=final_message)

# --- মূল প্রোগ্রাম ---
def main():
    """টেলিগ্রাম বটটি চালু এবং সার্বক্ষণিক চলমান রাখে।"""
    bot_instance = TraderBot()
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logging.critical("TELEGRAM_BOT_TOKEN not found. Bot cannot start.")
        return
        
    application = Application.builder().token(token).build()
    application.bot_data['bot_instance'] = bot_instance
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reload", reload_cache))
    # জমে থাকা পুরনো মেসেজগুলো বাদ দেওয়ার জন্য এই প্যারামিটারটি যোগ করা হয়েছে
    application.add_handler(MessageHandler(filters.TEXT & filters.UpdateType.CHANNEL_POST, handle_channel_post))
    
    logging.info("Trader Bot starting polling...")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
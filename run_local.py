import schedule
import time
import threading
import logging
from listings_scanner import main as run_listings_scan
from balance_scanner import main as run_balance_scan
from trader_bot import main as run_trader_bot

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(filename)s] - %(message)s')

def run_scheduled_tasks():
    """সিডিউল অনুযায়ী ব্যাকগ্রাউন্ড কাজগুলো চালায়।"""
    while True:
        schedule.run_pending()
        time.sleep(1)

def main():
    """সবকিছু একসাথে চালানোর জন্য মূল ফাংশন।"""
    logging.info("--- Starting Solo Server on Local PC ---")

    # কাজগুলো সিডিউল করা
    schedule.every(5).minutes.do(run_balance_scan)
    schedule.every(4).hours.do(run_listings_scan)
    
    logging.info("Scheduled jobs have been set up.")

    # সিডিউলারকে একটি আলাদা থ্রেডে ব্যাকগ্রাউন্ডে চালানো
    scheduler_thread = threading.Thread(target=run_scheduled_tasks)
    scheduler_thread.daemon = True  # এর ফলে মূল প্রোগ্রাম বন্ধ হলে এই থ্রেডটিও বন্ধ হয়ে যাবে
    scheduler_thread.start()
    
    logging.info("Scheduler thread started in the background.")

    # মূল থ্রেডে ট্রেডিং বট চালানো
    logging.info("Starting the main Trader Bot...")
    run_trader_bot()

if __name__ == '__main__':
    # প্রথমবার চালানোর জন্য ডেটা তৈরি করা
    print("Running initial scans to create database files...")
    run_listings_scan()
    run_balance_scan()
    print("Initial scans complete. Starting main application...")
    
    main()
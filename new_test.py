import csv
import threading
import time
import logging

from selenium.webdriver import Keys
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters
from selenium import webdriver
from selenium.webdriver.common.by import By

# Set up logging
logging.basicConfig(level=logging.INFO)

# Global list to store auction items
auction_items = []

stop_event = threading.Event()
continue_event = threading.Event()
continue_event.set()


def write_auctions_to_csv(file_path='auction_items.csv'):
    try:
        with open(file_path, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['URL', 'Max Price'])
            for item in auction_items:
                writer.writerow([item['url'], item['max_price']])
        logging.info(f"Data successfully written to {file_path}")
    except Exception as e:
        logging.error(f"Error writing to CSV: {e}")


class AuctionThread(threading.Thread):
    def __init__(self, url, max_chase, chat_id, context: CallbackContext):
        super().__init__()
        self.lock = threading.Lock()
        self.url = url
        self.max_chase = max_chase
        self.chat_id = chat_id
        self.context = context
        self.stop_event = threading.Event()
        self.continue_event = threading.Event()
        self.continue_event.set()  # Start with bidding allowed
        self.user_credentials = {'username': 'winnauctions@gmail.com', 'password': 'WinnPrime2024!'}

    def run(self):
        self.chase_function()

    def check_login_status(self, driver):
        try:
            driver.find_element(By.ID, 'divNames')
            return True
        except:
            return False

    def login(self, driver):
        try:
            login_url = driver.find_element(By.XPATH, '//*[@id="navbar"]/ul/li/div/a').get_attribute('href')
            driver.get(login_url)
            username = self.user_credentials.get('username')
            password = self.user_credentials.get('password')

            if username and password:
                driver.find_element(By.ID, 'Username').send_keys(username)
                driver.find_element(By.ID, 'Password').send_keys(password)
                driver.find_element(By.ID, 'SubmitLogin').click()
                time.sleep(5)  # Wait for the page to fully load
                self.send_telegram_alert("Login successful!")
            else:
                self.send_telegram_alert("Username and password not found")
        except Exception as e:
            logging.error(f"Error during login: {e}")
            self.send_telegram_alert(f"Error during login: {e}")

    def init_driver(self):
        options = webdriver.ChromeOptions()
        driver = webdriver.Chrome(options=options)
        return driver

    def chase_function(self):
        driver = self.init_driver()
        driver.get(self.url)

        if not self.check_login_status(driver):
            logging.info("User not logged in. Re-logging...")
            self.login(driver)

        try:
            item_name = driver.find_element(By.CLASS_NAME, 'auction-Itemlist-Title').text.strip()
            item_image = driver.find_element(By.XPATH, '//*[@id="carousel-custom"]/div/div/a[1]/img').get_attribute(
                'src')
            logging.info(f"Monitoring item: {item_name}")

            last_bid_time = None
            winning_alert_sent = False
            # outbid_status = False
            while not self.stop_event.is_set():
                if not self.continue_event.is_set():
                    self.send_telegram_alert("Bidding Stopped as per your request")
                    break

                if not self.check_login_status(driver):
                    logging.info("User not logged in. Re-logging...")
                    self.login(driver)
                    driver.get(self.url)

                min_next_bid_text = driver.find_element(By.ID, 'min-next-bid').text.strip()
                if min_next_bid_text:
                    min_next_bid = float(min_next_bid_text)
                else:
                    logging.error("Could not fetch the minimum next bid.")
                    continue

                your_bid_value = min_next_bid + 0.01
                print("My bid Value is: ", your_bid_value)

                remaining_time = self.get_time_remaining(driver)
                print('Remaining time is : ', remaining_time)

                current_winning_status = self.check_winning_status(driver)
                print("My current Winning Status is: ", current_winning_status)

                # Check if auction is won
                if self.is_time_within_threshold(remaining_time, '0 h : 0 m : 0 s') and current_winning_status:
                    if not winning_alert_sent:
                        self.send_telegram_alert(f"Item won: {item_name}")
                        winning_alert_sent = True
                    break

                # First bid placement
                if self.is_time_within_threshold(remaining_time, '10 h : 2 m : 15 s') and not current_winning_status:
                    if your_bid_value <= self.max_chase:
                        if not self.check_outbid_status(driver):
                            self.place_bid(driver, your_bid_value)
                            last_bid_time = time.time()
                            print('Last Bid time is', last_bid_time)
                            logging.info(f"Placed initial bid of {your_bid_value}")

                            if not self.check_login_status(driver):
                                logging.info("User not logged in. Re-logging...")
                                self.login(driver)

                        # If outbid, enter the loop to monitor and place the next bid in the last 15 seconds
                        if self.check_outbid_status(driver):
                            try:
                                close_m = driver.find_element(By.XPATH, '//*[@id="bidForm"]/div[2]/button[1]')
                                close_m.click()
                            except:
                                pass
                            logging.info(
                                f"Outbid detected before the last 15 seconds. Waiting until the final 15 seconds.")
                            self.send_telegram_alert(
                                f"You've been outbid on {item_name}. Waiting for the final 15 seconds.")

                            try:
                                close_btn = driver.find_element(By.XPATH, '//*[@id="myModalContent"]/div/div[4]/button')
                                close_btn.click()
                            except:
                                pass

                            if not self.check_login_status(driver):
                                logging.info("User not logged in. Re-logging...")
                                self.login(driver)

                            # Wait for the final 15 seconds
                            while True:
                                remaining_time = self.get_time_remaining(driver)
                                print(f"Monitoring for outbid... Remaining time: {remaining_time}")

                                if not self.check_login_status(driver):
                                    logging.info("User not logged in. Re-logging...")
                                    self.login(driver)

                                # Check if the remaining time is within the last 15 seconds
                                if self.is_time_within_threshold(remaining_time, '0 h : 0 m : 15 s'):
                                    logging.info("Final 15 seconds reached. Placing bid.")

                                    if your_bid_value <= self.max_chase:
                                        if not self.check_login_status(driver):
                                            logging.info("User not logged in. Re-logging...")
                                            self.login(driver)

                                        self.place_bid(driver, your_bid_value)
                                        last_bid_time = time.time()
                                        logging.info(f"Placed bid of {your_bid_value} in the final 15 seconds.")
                                    else:
                                        logging.info(f"Bid value exceeds max chase, skipping bid.")

                                    break  # Exit the loop after placing the final bid

                                # Small sleep to avoid a tight loop
                                time.sleep(1)

                    else:
                        alert_message = (f"Item: {item_name}\n"
                                         f"Current bid ${min_next_bid} exceeds your maximum price of ${self.max_chase}.\n"
                                         "Do you want to increase your max chase price?")
                        self.send_telegram_alert(alert_message)
                        self.send_telegram_options()

                        logging.info(f"Waiting for user input to update max_chase (current: {self.max_chase})")
                        self.continue_event.clear()

                        # Wait for user input for 10 seconds or until user updates max chase
                        self.continue_event.wait(timeout=10)
                        self.lock = threading.Lock()
                        with self.lock:
                            self.max_chase = self.context.user_data.get('custom_max', self.max_chase)

                        logging.info(f"Updated max chase price: {self.max_chase}")
                        self.context.user_data['continue_bidding'] = True
                        self.continue_event.set()

                        if not self.context.user_data.get('continue_bidding', True):
                            logging.info(f"User opted to stop bidding on {item_name}.")
                            self.stop_event.set()
                            break

                # Continue monitoring if no outbid
                time.sleep(1)

        except Exception as e:
            logging.error(f"Error during auction monitoring: {e}")
        finally:
            self.stop_event.set()
            driver.quit()

    def is_time_within_threshold(self, remaining_time, threshold_time):
        remaining_parts = list(
            map(int, remaining_time.replace(' h : ', ':').replace(' m : ', ':').replace(' s', '').split(':')))
        threshold_parts = list(
            map(int, threshold_time.replace(' h : ', ':').replace(' m : ', ':').replace(' s', '').split(':')))
        return remaining_parts <= threshold_parts

    def place_bid(self, driver, your_bid_value):
        # Ensure bid value is formatted to 2 decimal places
        formatted_bid_value = f"{your_bid_value:.2f}"
        print("*************************", formatted_bid_value)
        # Find the bid input element and clear it
        your_bid = driver.find_element(By.ID, 'BidAmount')
        your_bid.click()
        your_bid.send_keys(Keys.DELETE)
        time.sleep(0.5)
        your_bid.send_keys(formatted_bid_value)

        try:
            bid_now = driver.find_element(By.XPATH, '//*[@id="divAuctionItemDetail"]/div[8]/a')
            bid_now.click()
        except:
            pass
        time.sleep(0.2)
        try:
            agree_And_continue = driver.find_element(By.XPATH, '//*[@id="chkTermsAndCondition"]')
            agree_And_continue.click()
        except:
            pass
        try:
            agreed_btn = driver.find_element(By.ID, 'agreed-button')
            agreed_btn.click()
        except:
            pass

        try:
            click_ok = driver.find_element(By.XPATH, '/html/body/div[7]/div[7]/button[2]')
            click_ok.click()
        except:
            pass

        try:
            place_bid = driver.find_element(By.ID, 'agreed')
            place_bid.click()
            print('clicked placed bid')
        except:
            pass

        try:
            close_btn = driver.find_element(By.XPATH, '//*[@id="myModalContent"]/div/div[2]/button')
            close_btn.click()
            print('clicked closed')
        except:
            pass
        print(f"Bid placed: ${your_bid_value}")

    def get_time_remaining(self, driver):
        try:
            timer_text = driver.find_element(By.CLASS_NAME, 'auction-timer').text.strip()
            h = m = s = 0
            parts = timer_text.split(':')

            if len(parts) == 3:
                h_part, m_part, s_part = parts
                h = int(h_part.replace('h', '').strip()) if 'h' in h_part else 0
                m = int(m_part.replace('m', '').strip()) if 'm' in m_part else 0
                s = int(s_part.replace('s', '').strip()) if 's' in s_part else 0
            elif len(parts) == 2:
                m_part, s_part = parts
                m = int(m_part.replace('m', '').strip()) if 'm' in m_part else 0
                s = int(s_part.replace('s', '').strip()) if 's' in s_part else 0
            elif len(parts) == 1:
                s_part = parts[0]
                s = int(s_part.replace('s', '').strip()) if 's' in s_part else 0

            formatted_time = f"{h} h : {m} m : {s} s"
            logging.info(f"Time remaining: {formatted_time}")
            return formatted_time

        except Exception as e:
            logging.error(f"Error getting time remaining: {e}")
            return "0 h : 0 m : 0 s"

    def check_winning_status(self, driver):
        try:
            return "Winning" in driver.find_element(By.ID, 'CurrentBidAmount_').text.strip()
        except:
            return False

    def check_outbid_status(self, driver):
        try:
            outbid_text = driver.find_element(By.CLASS_NAME, 'font-1rem').text.strip()
            return 'Outbid' in outbid_text
        except:
            return False

    def wait_for_final_seconds(self, driver):
        while True:
            remaining_time = self.get_time_remaining(driver)
            if remaining_time.startswith('0 h : 0 m : 15 s') or remaining_time.startswith('0 h : 0 m : 0 s'):
                break
            time.sleep(1)

    def send_telegram_alert(self, message):
        bot = Bot(token='7541145419:AAGb55AbCcehjinlyylDiTHdnPZoLaoaA9I')
        bot.send_message(chat_id=self.chat_id, text=message)

    def send_telegram_options(self):
        bot = Bot(token='7541145419:AAGb55AbCcehjinlyylDiTHdnPZoLaoaA9I')
        keyboard = [
            [InlineKeyboardButton("2.00", callback_data='2.00')],
            [InlineKeyboardButton("5.00", callback_data='5.00')],
            [InlineKeyboardButton("10.00", callback_data='10.00')],
            [InlineKeyboardButton("Custom", callback_data='custom')],
            [InlineKeyboardButton("No, I don't want to increase the value", callback_data='no_increase')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        bot.send_message(chat_id=self.chat_id, text="MaxChase reached. Would you like to increase the value?",
                         reply_markup=reply_markup)


def start_monitoring_auctions(auctions, context: CallbackContext):
    threads = [AuctionThread(url, max_chase, chat_id, context) for url, max_chase, chat_id in auctions]
    for thread in threads:
        thread.start()
    return threads


def stop_all_threads(threads):
    for thread in threads:
        thread.stop_event.set()
        thread.join()


def start(update: Update, context: CallbackContext):
    global chat_id
    chat_id = update.message.chat_id
    welcome_message = (
        "Welcome to the Auction Bot!\n\n"
        "Here are the commands you can use:\n"
        "/start - Start the bot and get an introduction.\n"
        "/help - Get a list of commands.\n"
        "/instructions - Learn how the bot works.\n"
        "/a <URL1> <max_price1>,<URL2> <max_price2>,... - Add auction URLs and max prices.\n"
        "/l - List all added auction URLs and their max prices.\n"
        "/r <URL> - Remove an auction URL from the list.\n"
        "Use /help for a list of commands and /instructions to learn how this bot works."
    )
    update.message.reply_text(welcome_message)


def help_command(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Here are the commands you can use:\n"
        "/start - Start the bot and get an introduction.\n"
        "/help - Get a list of commands.\n"
        "/instructions - Learn how the bot works.\n"
        "/a <URL1> <max_price1>,<URL2> <max_price2>,... - Add auction URLs and max prices.\n"
        "/l - List all added auction URLs and their max prices.\n"
        "/r <URL> - Remove an auction URL from the list.\n"
    )


def instructions(update: Update, context: CallbackContext):
    update.message.reply_text(
        "This bot helps you monitor auction items. Here's how it works:\n\n"
        "1. **Add Auctions**: Use `/a <URL> <max_price>` to add auction items. The bot will monitor these "
        "auctions and notify you of the status.\n"
        "2. **List Auctions**: Use `/l` to see all the auctions you've added.\n"
        "3. **Remove Auctions**: Use `/r <URL>` to remove an auction URL from the list.\n"
        "The bot will alert you when the maximum bid (MaxChase) is reached and ask if you want to increase it."
    )


def add_auction(update: Update, context: CallbackContext):
    global auction_items

    if not context.args:
        update.message.reply_text("Usage: /a <URL1> <max_price1>,<URL2> <max_price2>,...")
        return

    auction_input = ' '.join(context.args).split(',')
    for item in auction_input:
        item = item.strip()
        if not item:
            continue

        try:
            url, max_price_str = item.rsplit(' ', 1)
            max_price = float(max_price_str)

            existing_auction = next((auction for auction in auction_items if auction['url'] == url), None)
            if existing_auction:
                if existing_auction['max_price'] == max_price:
                    update.message.reply_text(f"URL already exists: {url} with the same max price: ${max_price}")
                else:
                    existing_auction['max_price'] = max_price
                    update.message.reply_text(f"Max chase price updated for URL: {url} to ${max_price}")
                    write_auctions_to_csv()
                    context.user_data['custom_max'] = max_price
            else:
                auction_items.append({'url': url, 'max_price': max_price})
                update.message.reply_text(f"Auction URL added: {url} with max price: ${max_price}")
                write_auctions_to_csv()
                context.user_data['custom_max'] = max_price

                # Start monitoring this new auction in a separate thread
                monitoring_thread = threading.Thread(
                    target=AuctionThread(url, max_price, update.message.chat_id, context).chase_function)
                monitoring_thread.start()

        except ValueError:
            update.message.reply_text(
                f"Invalid format or price for pair: '{item}'. Ensure the URL is followed by a space and a numeric price.")
        except Exception as e:
            update.message.reply_text(f"Error processing item '{item}': {str(e)}")


def list_auctions(update: Update, context: CallbackContext):
    global auction_items

    if not auction_items:
        update.message.reply_text("No auctions have been added yet.")
        return

    message = "Current auction items:\n"
    for auction in auction_items:
        message += f"URL: {auction['url']}, Max Price: ${auction['max_price']}\n"

    update.message.reply_text(message)


def remove_auction(update: Update, context: CallbackContext):
    global auction_items

    if not context.args:
        update.message.reply_text("Usage: /r <URL>")
        return

    url = context.args[0].strip()
    for auction in auction_items:
        if auction['url'] == url:
            auction_items.remove(auction)
            update.message.reply_text(f"Removed auction URL: {url}")
            write_auctions_to_csv()
            return

    update.message.reply_text(f"URL not found in the list: {url}")


def button(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data

    # Retrieve the current max chase value (assuming you store it in user data)
    current_max_chase = context.user_data.get('custom_max', 0)  # Default to 0 if not set
    print('My current max chase is: ', current_max_chase)
    if data == 'no_increase':
        continue_event.set()  # Resume bidding if stopped
        query.answer()
        query.edit_message_text(text="MaxChase reached. Continuing with current max value.")
        return

    if data == 'custom':
        context.user_data['custom_max'] = True
        query.answer()
        query.edit_message_text(text="Enter your custom max chase value:")
        return

    # If the user selects one of the options to add (2, 5, 10)
    if data in ['2.00', '5.00', '10.00']:
        increment_value = float(data)  # Convert the selected increment to a float
        context.user_data['custom_max'] = current_max_chase + increment_value  # Add to existing value
        query.answer()
        query.edit_message_text(
            text=f"Custom max chase increased by ${data}. New max chase: ${context.user_data['custom_max']}.")

        continue_event.set()  # Resume bidding if stopped
        return


def handle_custom_max_chase(update: Update, context: CallbackContext):
    if 'custom_max' in context.user_data:
        new_max_chase = context.user_data['custom_max']
        chat_id = update.message.chat_id
        url = next(item['url'] for item in auction_items if item['url'] == update.message.reply_to_message.text)

        for thread in threading.enumerate():
            if isinstance(thread, AuctionThread) and thread.url == url:
                thread.max_chase = new_max_chase  # Update the max chase value
                thread.continue_event.set()  # Resume bidding if it was stopped
                update.message.reply_text(f"Custom max chase value updated to ${new_max_chase}.")
                return

        update.message.reply_text(f"No auction thread found for URL: {url}")


def main():
    updater = Updater('7541145419:AAGb55AbCcehjinlyylDiTHdnPZoLaoaA9I')
    dp = updater.dispatcher

    # Add command handlers
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("instructions", instructions))
    dp.add_handler(CommandHandler("a", add_auction))
    dp.add_handler(CommandHandler("l", list_auctions))
    dp.add_handler(CommandHandler("r", remove_auction))
    dp.add_handler(CallbackQueryHandler(button))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_custom_max_chase))

    # Start polling and idle
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()

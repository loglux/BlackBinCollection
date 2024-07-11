import os
from dotenv import load_dotenv
import time
from datetime import datetime, timedelta
from O365 import Account
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.ui import WebDriverWait


class BlackBin:
    def __init__(self):
        load_dotenv()  # Load environment variables from .env file
        client_id = os.getenv("CLIENT_ID")
        client_secret = os.getenv("CLIENT_SECRET")
        self.credentials = (client_id, client_secret)
        self.options = webdriver.ChromeOptions()
        self.options.add_argument("--disable-dev-shm-usage")
        self.options.add_argument("--disable-extensions")
        self.options.add_argument("--disable-gpu")
        # self.options.add_argument("--no-sandbox")
        self.options.add_argument("--headless")
        self.options.add_experimental_option("excludeSwitches", ['enable-automation'])
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " \
                     "(KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36"
        self.options.add_argument('--user-agent={}'.format(user_agent))
        self.url = "https://online.belfastcity.gov.uk/find-bin-collection-day/Default.aspx"
        self.year = int()
        self.month = int()
        self.day = int()

    def start_chrome(self):
        self.driver = webdriver.Remote("http://selenium-server:4444/wd/hub", options=self.options)

    def get_bin(self, house_address):
        house_address = house_address.upper()
        postcode = house_address.split(', ')[2]
        self.driver.get(self.url)
        time.sleep(1)
        # user_agent = self.driver.execute_script("return navigator.userAgent;")
        # print(user_agent)
        WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "label[for='searchBy_radio_1']"))).click()
        WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.ID, "Postcode_textbox"))).send_keys(postcode)
        self.driver.find_element(By.ID, "AddressLookup_button").click()
        select = Select(self.driver.find_element(By.ID, "lstAddresses"))
        try:
            select.select_by_visible_text(house_address)
            self.driver.find_element(By.ID, "SelectAddress_button").click()
            try:
                table = self.driver.find_element(By.ID, "ItemsGrid").find_elements(By.TAG_NAME, "tr")[1].text
                table = table.split(' ')
                del table[:3]
                month = table[3]
                months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
                if month in months:
                    self.month = months.index(month) + 1
                self.day = int(table[4])
                self.year = int(table[5])
                print(table)
            except NoSuchElementException:
                print("The Information is Is Missing From Belfast City Council Website")
                info = self.driver.find_element(By.ID, "BinDetailsPnl").text
                print(info)
                self.get_exit()
                quit()
        except NoSuchElementException:
            print("The Address Is Incorrect!")
            print(house_address)
            self.get_exit()
            quit()

    def get_exit(self):
        self.driver.quit()

    def update_calendar(self, calendar_name=None):
        account = Account(self.credentials)
        schedule = account.schedule()
        if not calendar_name:
            calendar = schedule.get_default_calendar()
        else:
            calendar = schedule.get_calendar(calendar_name=calendar_name)
        collection_start = datetime(self.year, self.month, self.day, 0, 0)
        collection_end = collection_start + timedelta(days=1)
        q = calendar.new_query('start').greater_equal(collection_start)
        q.chain('and').on_attribute('end').less_equal(collection_end)
        events = calendar.get_events(query=q, include_recurring=False)
        for e in events:
            if e.subject == 'Bin collection':
                print("The Event " + "#" + e.subject + "#" + " Is Already In The Calendar")
                quit()
        collection = calendar.new_event()  # creates a new unsaved event
        collection.subject = 'Bin collection'
        collection.location = 'Belfast'
        collection.start = collection_start
        collection.is_all_day = True
        collection.remind_before_minutes = 360
        print(collection)
        collection.save()

if __name__ == '__main__':
    # "House_Number Street Name (like: 3 Anna Street), Belfast, POST_CODE"
    load_dotenv()  # Ensure environment variables are loaded
    house = os.getenv("HOUSE_ADDRESS")
    calendar_name = os.getenv("CALENDAR_NAME", "Events")  # Load event name from .env or use default
    bins = BlackBin()
    bins.start_chrome()
    bins.get_bin(house)
    bins.get_exit()
    bins.update_calendar(calendar_name)

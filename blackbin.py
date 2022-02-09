from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.select import Select
from selenium.common.exceptions import NoSuchElementException
import time
import datetime as dt
from O365 import Account


class BlackBin:
    def __init__(self, event_subject='Bin collection'):
        self.options = Options()
        self.url = "https://dof.belfastcity.gov.uk/BinCollectionSchedulesV2/addressLookup.aspx"
        self.credentials = ('', '')
        self.event_subject = event_subject
        self.year = int()
        self.month = int()
        self.day = int()

    def start_chrome(self, headless=False):
        if headless:
            self.options.add_argument("--disable-dev-shm-usage")
            self.options.add_argument("--disable-extensions")
            self.options.add_argument("--disable-gpu")
            self.options.add_argument("--no-sandbox")
            self.options.headless = True
        self.options.add_experimental_option("excludeSwitches", ['enable-automation'])
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " \
                     "(KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36"
        self.options.add_argument('--user-agent={}'.format(user_agent))
        self.chromepath = "C:/Users/../webdriver/chromedriver.exe"
        self.driver = webdriver.Chrome(executable_path=self.chromepath, options=self.options)

    def get_bin(self, house_address):
        house_address = house_address.upper()
        postcode = house_address.split(', ')[2]
        self.driver.get(self.url)
        time.sleep(1)
        self.driver.find_element_by_css_selector("label[for='searchBy_radio_1']").click()
        WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.ID, "Postcode_textbox")))
        self.driver.find_element_by_id("Postcode_textbox").send_keys(postcode)
        self.driver.find_element_by_id("AddressLookup_button").click()
        select = Select(self.driver.find_element_by_id("lstAddresses"))
        try:
            select.select_by_visible_text(house_address)
            self.driver.find_element_by_id("SelectAddress_button").click()
            try:
                table = self.driver.find_element_by_id("ItemsGrid").find_elements_by_tag_name("tr")[1].text
                table = table.split(' ')
                del table[:3]
                # week_day = table[0]
                # frequency = table[1]
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
                info = self.driver.find_element_by_id("BinDetailsPnl").text
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
        collection_start = dt.datetime(self.year, self.month, self.day)
        collection_end = collection_start + dt.timedelta(days=1)
        q = calendar.new_query('start').greater_equal(collection_start)
        q.chain('and').on_attribute('end').less_equal(collection_end)
        events = calendar.get_events(query=q, include_recurring=False)
        for e in events:
            if e.subject == self.event_subject:
                print("The Event " + "#" + e.subject + "#" + " Is Already In The Calendar")
                quit()
        collection = calendar.new_event()  # creates a new unsaved event
        collection.subject = self.event_subject
        collection.location = 'Belfast'
        collection.start = dt.datetime(self.year, self.month, self.day, 0, 0)
        collection.is_all_day = True
        collection.remind_before_minutes = 360
        print(collection)
        collection.save()


if __name__ == '__main__':
    # "House_Number Street Name (like: 3 Anna Street), Belfast, POST_CODE"
    house = ""
    # A subject of the event is 'Bin collection' by default
    # Your can change this subject, if you put an argument here, e.g.
    #
    bins = BlackBin()
    bins.start_chrome(True)
    bins.get_bin(house)
    bins.get_exit()
    # if the argument is empty, the default calendar is chosen:
    bins.update_calendar('Events')

# Black Bin Collection Day in Belfast
The scritpt takes the next Black Bin collection date information from Belfast City Hall Website
https://dof.belfastcity.gov.uk/BinCollectionSchedulesV2/addressLookup.aspx
And then publishes the event in your Outlook Calendar.
## Requirements
```angular2html
selenium
O365
```
1. You must setup access righs to be able modify your Outlook Calendar.
The process has been described on the O365 module's site https://github.com/O365/python-o365

In short words, you must setup access rights and obtain a token file o365_token.txt
 
2. You must install Chrome browser and webdirver (https://chromedriver.chromium.org/downloads).

3. In the blackbin.py you must point your secret keys and the 
```angular2html
self.credentials = ('client_id', 'client_secret')
```
and path to the chrome's webdriver
```angular2html
self.chromepath = "C:/Users/.../webdriver/chromedriver.exe"
```
 
## How Does It Work?
### 1. You should point your address in the house = ""
For example:
```angular2html
house = '58 London Street, Belfast, BT6 8EN'
```
or
```angular2html
house = 'Apartment 42,2 North Howard Street, Belfast, BT13 2AW'
```
### 2. You should point your calendar's name
```angular2html
bins.update_calendar('Events')
```
or leave a blank variable if you intent to use your default calendar:
```angular2html
bins.update_calendar()
```
You can also change a subject for your bin collection event, if you put an argument. If no argument, the subject is 'Bin collection' by default.
```angular2html
bins = BlackBin('Black Bin Collection')
```
And chenge a notification time before the event. This settings push a reminder at 18:00 a day before the collection. You can change it.
```angular2html
collection.remind_before_minutes = 360
```
## Usage
The script can be installed in Linux and be stared by CRON

For example: “At 12:00 on Tuesday and Friday.”
````angular2html
0 12 * * 2,5 cd /opt/scripts && /usr/local/bin/pipenv run python blackbin.py >/dev/null 2>&1
````
Here you can figure out how to use CRON
https://crontab.guru/
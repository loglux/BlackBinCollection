# Black Bin Collection Day in Belfast
The scritpt takes the next Black Bin collection date information from Belfast City Hall Website
https://dof.belfastcity.gov.uk/BinCollectionSchedulesV2/addressLookup.aspx

## Requirements
```angular2html
selenium
O365
```
1. You must setup access righs to be able modify your Outlook Calendar.
The process has been described on the O365 module's site https://github.com/O365/python-o365

In short words, you must setup rights and obtain a token file o365_token.txt
 
2. You must install chrome browser and webdirver.

3. Int the blackbin.py you must point your secret keys and the 
```angular2html
self.credentials = ('', '')
```
and path to the chrome's webdriver
```angular2html
self.chromepath = "C:/Users/call2/.../webdriver/chromedriver.exe"
```
 
## How Does It Work?
###1. You should point your address in the house = ""
For example:
```angular2html
house = '24 Ann Street, Belfast, BT1 4EF'
```
###2. You should point your calendar's name
```angular2html
bins.update_calendar('Events')
```
or leave a blank variable if you intent to use your default calendar:
```angular2html
bins.update_calendar()
```
You can alsoe change a subject here for your bin collection event
```angular2html
collection.subject = 'Bin collection'
```
And chenge a notification time before the event. This settings push a remander at 18:00 a day before the collection. You can change it.
```angular2html
collection.remind_before_minutes = 360
```
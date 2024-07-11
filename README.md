# Black Bin Collection Day in Belfast

BlackBin is a script that automates the process of checking the next Black Bin collection day on the Belfast City Hall for a specific address and adds it to your Outlook Calendar. This helps you stay organized and reminds you when to put out your bin for collection.

## Prerequisites

- Docker
- Docker Compose

## Setup

1. Clone this repository: `git clone https://github.com/loglux/BlackBinCollection.git`
2. Navigate to the project directory: `cd BlackBinCollection`
3. **Configure environment variables**:
   - Create a `.env` file in the root of the project directory.
   - Add the following variables to the `.env` file, replacing placeholder values with your actual details:
     ```dotenv
     CLIENT_ID=your_client_id
     CLIENT_SECRET=your_client_secret
     HOUSE_ADDRESS=House_Number Street Name, Belfast, POST_CODE
     CALENDAR_NAME=your_calendar_name
     ```
     For example:
     ```dotenv
     CLIENT_ID=12345678-abcd-1234-ef00-123456789abc
     CLIENT_SECRET=abcd1234Efgh5678Ijkl
     HOUSE_ADDRESS=3 Anna Street, Belfast, BT1 1AA
     CALENDAR_NAME=MyCalendar
     ```
   - Ensure your `.env` file is correctly formatted and saved.
4. **Install dependencies**:
```bash
pip install -r requirements.txt 
```
5. **Run the script**:
```bash
python blackbin.py
```
## Manual Docker Container Setup

If you prefer to set up the Docker containers manually, follow these steps:

1. Build the Selenium server container:
   - Open a terminal and navigate to the project directory.
   - Run the following command: `docker run -d --name selenium-server -p 4444:4444 selenium/standalone-chrome`
2. Build the BlackBin container:
   - Run the following command: `docker build -t blackbin .`
3. Run the BlackBin container:
   - Run the following command: `docker run -d --name blackbin --network selenium-network blackbin`
4. Adjust the cron task in the 'Dockerfile' to specify your desired schedule. The default cron task runs the script at 7:30 PM on Mondays, Fridays, and Saturdays.

## Docker Container Setup using docker_start.sh

To automate the Docker container setup process, you can use the `docker_start.sh` file included in the project. Follow these steps:

1. Open a terminal and navigate to the project directory.
2. Update the shebang in the docker_start.sh script:
   - Open the docker_start.sh file.
   - Update the shebang (#!/opt/bin/sh) at the beginning of the script if necessary, depending on your system (#!/opt/bin/sh is desinged for ASUStor NAS).
   - Save the changes.
3. Run the following command: `sudo chmod +x docker_start.sh` (only needed for the first time).
4. Execute the `docker_start.sh` script:
   - Run the following command: `sudo ./docker_start.sh`

The script will create a network called `selenium-network` and start the Selenium server container (`selenium-server`) and the BlackBin container (`blackbin`).

## Usage
The script will prompt you to enter your address in the format: `House_Number Street Name (e.g., 123 Main St), Belfast, POST_CODE`. It will then retrieve the next Black Bin collection day for that address from the Belfast City Hall website (https://online.belfastcity.gov.uk/find-bin-collection-day/Default.aspx) and add it to your Outlook Calendar.

Once the setup is complete, the Black Bin collection day reminder will be automatically scheduled to run according to the specified cron task. It will check the next collection day for your address in Belfast and add it to your Outlook Calendar.

You can view the added event in your Outlook Calendar to stay informed about the upcoming Black Bin collection day.

## Manual execution of the script

1. Open a terminal and navigate to the project directory.
2. Run the script inside the BlackBin container:
   - Run the following command: `sudo docker exec -it blackbin bash -c "python blackbin.py"`

Please note that the script uses the Selenium library to scrape information from the Belfast City Hall website, so make sure you have a stable internet connection during the script's execution.

If you encounter any issues or have any questions, please feel free to open an issue in this repository.

Happy bin collection day reminders!

## Obtaining an Access Token

To use the BlackBin script with your Microsoft 365 account, you need to obtain an access token. Follow these steps to generate the token file:

1. Go to the [Microsoft 365 App Registration Portal](https://portal.azure.com/#blade/Microsoft_AAD_IAM/ActiveDirectoryMenuBlade/RegisteredApps) and sign in with your Microsoft 365 account.
2. Register a new application and note down the client ID and client secret.
3. Grant the necessary API permissions to the application:
   - `User.Read`: Read user profile
   - `offline_access`: Access user data even when the user is not present
4. Save the changes and generate a new access token using the client ID an

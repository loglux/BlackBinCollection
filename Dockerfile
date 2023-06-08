# Start from a Python 3.9 base image
FROM python:3.9

# Set the working directory in the container to /app
WORKDIR /app

# Install cron
RUN apt-get update && apt-get install -y cron

# Copy your Python script, text file, and requirements file into the Docker image
COPY blackbin.py o365_token.txt requirements.txt ./

# Install the Python packages specified in your requirements file
RUN pip install --no-cache-dir -r requirements.txt

# Add the cron job to the crontab
RUN (crontab -l 2>/dev/null; echo "30 19 * * 1,5,6 cd /app && /usr/local/bin/python /app/blackbin.py >/dev/null 2>&1") | crontab -

# When the Docker container starts, run cron in the foreground
CMD ["cron", "-f"]


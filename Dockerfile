# Start from a Python 3.9 base image
FROM python:3.11

# Set the working directory in the container to /app
WORKDIR /app

# Install cron
RUN apt-get update && apt-get install -y cron netcat-traditional iputils-ping dnsutils

# Copy your Python script, text file, and requirements file into the Docker image
COPY blackbin.py web_ui.py o365_token.txt .env requirements.txt update_token.py auth_google.py ./
COPY integrations/ ./integrations/
COPY templates/ ./templates/

ENV CONFIG_PATH=/data/blackbin_config.json

# Install the Python packages specified in your requirements file
RUN pip install --no-cache-dir -r requirements.txt

# Local config volume
RUN mkdir -p /data

# Expose REST API and web UI ports
EXPOSE 5000 5050

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# When the Docker container starts, run cron in the foreground
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

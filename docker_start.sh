#!/bin/bash

# Check if the selenium-server container already exists
if [ "$(docker ps -a | grep selenium-server)" ]; then
    echo "selenium-server container already exists, updating..."
    docker stop selenium-server
    docker rm selenium-server
fi
docker run -d --name selenium-server --network host selenium/standalone-chrome

# Check if the blackbin container already exists
if [ "$(docker ps -a | grep blackbin)" ]; then
    echo "blackbin container already exists, updating..."
    docker stop blackbin
    docker rm blackbin
fi
docker build -t blackbin .
docker run -d --name blackbin --network host blackbin
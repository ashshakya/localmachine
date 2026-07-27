#!/bin/bash

set -e

TAG=$1

export TAG=$TAG

cd ~/dashboard

echo "Deploying $TAG"

docker compose pull

docker compose up -d

docker image prune -f

echo "Deployment complete."
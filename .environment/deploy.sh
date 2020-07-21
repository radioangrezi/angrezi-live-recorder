#!/bin/bash

# accessible var DEPLOY_REPO_NAME
# accessible var DEPLOY_DEST
# accessible var DEPLOY_FROM

# run as angrezi user
SERVICE_USER=live-recorder
SERVICE_NAME=angrezi-live-recorder

VIRTUALENV="$DEPLOY_DEST/../venv"

sudo systemctl stop $SERVICE_NAME

# make virtualenv
if [ ! -d "$VIRTUALENV" ]; then
    sudo virtualenv -p python2 $VIRTUALENV
    sudo chown -R $SERVICE_USER:$SERVICE_USER $VIRTUALENV
fi

# remove and deploy all files
sudo rm -rf $DEPLOY_DEST
sudo mkdir $DEPLOY_DEST

# copy application files
sudo cp -r $DEPLOY_FROM/. $DEPLOY_DEST

# chown by user
sudo chown -R $SERVICE_USER:$SERVICE_USER $DEPLOY_DEST

# update virtualenv
sudo -u $SERVICE_USER $VIRTUALENV/bin/pip install -r $DEPLOY_DEST/requirements.txt

# restart service
sudo systemctl restart $SERVICE_NAME


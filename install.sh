#! /bin/bash

# check if the user is root
# - required due to user permissions in the /opt folder
# - required as other users have issues with the permissions in the /dev/ttyUSB*
if [ $EUID -ne 0 ]; then
   echo "Please run as root"
   exit 1
fi

# get the current directory
CURRENT_DIR=$(pwd)

# AT INTERFACE SERVICE
# ------------------------------------------------------------
# if the link already exists, do nothing
if [ -L /opt/serial-at-api ]; then
   echo "Link already exists"
   systemctl status serialmodeminterface
   exit 0
else
    # create link in opt directory for all the API services
    cp -R $CURRENT_DIR/src/code/serial-at-api /opt/serial-at-api

    # create the python virtual environment
    cd /opt/serial-at-api
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    deactivate

    # create systemd service for the API service
    cp $CURRENT_DIR/src/code/serial-at-api/service/serialmodeminterface.service /etc/systemd/system/.

    # reload the systemd daemon
    systemctl daemon-reload
    # enable and start the service
    systemctl enable serialmodeminterface
    systemctl start serialmodeminterface

    # show the status of the service
    systemctl status serialmodeminterface
fi
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
# for more information about the service refer to ./src/code/serial-at-api/README.md
# if the link already exists, do nothing
if [ -d /opt/serial-at-api ]; then
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

# QCSUPER DEPENDANCIES INSTALLATION
# ------------------------------------------------------------
# for more information about the service refer to https://github.com/p1sec/qcsuper
# if the link already exists, do nothing
if [ -d /opt/qcsuper ]; then
   echo "Link already exists"
   systemctl status qcsuper
   exit 0
else
    # create link in opt directory for all the API services
    cd /opt
    git clone https://github.com/P1sec/QCSuper.git qcsuper
    cd qcsuper
    python3 -m venv .venv
    source .venv/bin/activate
    # pickup the requirements for the QCSuper service
    echo "pyserial" >> requirements.txt
    echo "pyusb"    >> requirements.txt
    echo "crcmod"   >> requirements.txt
    echo "pycrate"  >> requirements.txt
    pip3 install -r requirements.txt
    deactivate
fi

# SIMTRACE2 DEPENDANCIES INSTALLATION
# ------------------------------------------------------------
# install simtrace2 dependencies
# for more information about the service refer to https://github.com/p1sec/simtrace2
# if the link already exists, do nothing
wget https://obs.osmocom.org/projects/osmocom/public_key
install -Dm644 public_key /usr/share/osmocom-keyring/osmocom.asc
echo "deb [signed-by=/usr/share/osmocom-keyring/osmocom.asc] https://downloads.osmocom.org/packages/osmocom:/latest/Debian_13/ ./" > /etc/apt/sources.list.d/osmocom.list
apt-get update
apt-get install tcpdump libosmocore22 libosmocore-utils simtrace2-utils -y

# SIMTRACE2 API SERVICE
# ------------------------------------------------------------
# for more information about the service refer to ./src/code/serial-simtracing/README.md
# if the link already exists, do nothing
if [ -d /opt/serial-simtracing ]; then
   echo "Link already exists"
   systemctl status serialsimtrace
   exit 0
else
    # create link in opt directory for all the API services
    cp -R $CURRENT_DIR/src/code/serial-simtracing /opt/serial-simtracing

    # create the python virtual environment
    cd /opt/serial-simtracing
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    deactivate

    # create systemd service for the API service
    cp $CURRENT_DIR/src/code/serial-simtracing/service/serialsimtrace.service /etc/systemd/system/.

    # reload the systemd daemon
    systemctl daemon-reload
    # enable and start the service
    systemctl enable serialsimtrace
    systemctl start serialsimtrace

    # show the status of the service
    systemctl status serialsimtrace
fi
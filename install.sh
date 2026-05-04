#!/usr/bin/env bash
#
# Usage:
#   sudo ./install.sh -h            # show the usage
#   sudo ./install.sh -i            # full install
#   sudo ./install.sh -d            # delete all the services
#

# check if the user is root
# - required due to user permissions in the /opt folder
# - required as other users have issues with the permissions in the /dev/ttyUSB*
if [ $EUID -ne 0 ]; then
   echo "Please run as root"
   exit 1
fi

# don't let systemctl status / journalctl drop into the pager and wait for input
export SYSTEMD_PAGER=cat

# get the current directory
CURRENT_DIR=$(pwd)

usage() { sed -n '2,6p' "$0"; }

INSTALL=0
DELETE=0
while getopts ":ihd" opt; do
   case "$opt" in
      h) usage; exit 0 ;;
      i) echo -e "\033[32mInstalling all the services...\033[0m"; INSTALL=1 ;;
      d) echo -e "\033[31mDeleting all the services...\033[0m"; DELETE=1 ;;
      \?) echo "invalid option: -$OPTARG" >&2; usage; exit 2 ;;
   esac
done

function installall {
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
   # SIMTRACE2 API SERVICE
   # ------------------------------------------------------------
   # for more information about the service refer to ./src/code/serial-simtracing/README.md
   # if the link already exists, do nothing
   if [ -d /opt/serial-modemtracing ]; then
      echo "Link already exists"
      systemctl status serialmodemtrace
      exit 0
   else
      # create link in opt directory for all the API services
      cp -R $CURRENT_DIR/src/code/serial-modemtracing /opt/serial-modemtracing

      # create the python virtual environment
      cd /opt/serial-modemtracing
      python3 -m venv .venv
      source .venv/bin/activate
      pip install -r requirements.txt
      deactivate

      # create systemd service for the API service
      cp $CURRENT_DIR/src/code/serial-modemtracing/service/serialmodemtrace.service /etc/systemd/system/.

      # reload the systemd daemon
      systemctl daemon-reload
      # enable and start the service
      systemctl enable serialmodemtrace
      systemctl start serialmodemtrace

      # show the status of the service
      systemctl status serialmodemtrace
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

   # WEBAPP SERVICE
   # ------------------------------------------------------------
   # if the link already exists, do nothing
   if [ -d /opt/webapp-flask ]; then
      echo "Link already exists"
      systemctl status webinterface
      exit 0
   else
      # create link in opt directory for all the API services
      cp -R $CURRENT_DIR/src/gui/webapp-flask /opt/webapp-flask

      # create the python virtual environment
      cd /opt/webapp-flask
      python3 -m venv .venv
      source .venv/bin/activate
      pip install -r requirements.txt
      deactivate

      # create systemd service for the API service
      cp $CURRENT_DIR/src/gui/webapp-flask/service/webinterface.service /etc/systemd/system/.

      # reload the systemd daemon
      systemctl daemon-reload
      # enable and start the service
      systemctl enable webinterface
      systemctl start webinterface

      # show the status of the service
      systemctl status webinterface
   fi
}

function cleanall {
   # AT INTERFACE SERVICE
   if [ -d /opt/serial-at-api ]; then
      rm -rf /opt/serial-at-api
      systemctl stop serialmodeminterface
      systemctl disable serialmodeminterface
      rm -rf /etc/systemd/system/serialmodeminterface.service
   else
      echo -e "\033[31mSerial AT API service not installed\033[0m"
   fi
   # QCSuper SERVICE
   if [ -d /opt/qcsuper ]; then
      rm -rf /opt/qcsuper
   else
      echo -e "\033[31mQCSuper service not installed\033[0m"
   fi
   # MODEM TRACING SERVICE
   if [ -d /opt/serial-modemtracing ]; then
      rm -rf /opt/serial-modemtracing
      systemctl stop serialmodemtrace
      systemctl disable serialmodemtrace
      rm -rf /etc/systemd/system/serialmodemtrace.service
   else
      echo -e "\033[31mSerial MODEM TRACING service not installed\033[0m"
   fi
   # SIMTRACE2 API SERVICE
   if [ -d /opt/serial-simtracing ]; then
      rm -rf /opt/serial-simtracing
      systemctl stop serialsimtrace
      systemctl disable serialsimtrace
      rm -rf /etc/systemd/system/serialsimtrace.service
   else
      echo -e "\033[31mSerial SIMTRACE2 API service not installed\033[0m"
   fi
   # WEBAPP SERVICE
   if [ -d /opt/webapp-flask ]; then
      rm -rf /opt/webapp-flask
      systemctl stop webinterface
      systemctl disable webinterface
      rm -rf /etc/systemd/system/webinterface.service
   else
      echo -e "\033[31mWebapp service not installed\033[0m"
   fi
   # update systemd daemon
   systemctl daemon-reload
   # show the status of the services
   systemctl status serialmodeminterface
   systemctl status qcsuper
   systemctl status serialmodemtrace
   systemctl status serialsimtrace
   systemctl status webinterface
}

if [ "$INSTALL" -eq 1 ]; then
   installall
   exit 0
elif [ "$DELETE" -eq 1 ]; then
   cleanall
   exit 0
else
   echo "Nothing to do..."
fi
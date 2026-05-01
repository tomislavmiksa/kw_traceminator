# Introduction

This module is created in order to communicate with the modem serial interface.
At the moment only Quectel EC25 is supported, plan to add BG96 in a very near future.

Application is running API on the `http://localhost/8666` and the most common calls are

```
# get the basic application information
curl http://localhost:8666/

# execute the AT command and get the output result
# - with the command bellow you are getting back the output of the ATI Command
curl --request POST --header  "Content-Type: application/json" --data '{"cmd": "ATI"}' http://localhost:8666/at
```

# Application Setup

## Set Python

- as to access serial port requires the root permissions, all CMD bellow should be executed as root
- API should be ran by  root user

```
python3 -m venv .venv
source .venv/bin/activate

pip3 install -r ./requirements.txt
```

## User must have permissiong for serial

```
sudo usermod -a -G dialout $USER
```

## Recommandation

- helps with testing the API and access to it

```
sudo apt install jq
```

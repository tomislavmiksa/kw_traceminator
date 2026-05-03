import json
import subprocess
from pathlib import Path

MODEM_DATA_FILE = Path(__file__).parent / "data" / "modem.json"

# function to load the modem data from the JSON file
# - the file contains the modem name and the corresponding interfaces mapping (AT, NMEA, Diag, Modem, NDIS)
# - the function returns the modem data as a dictionary
def loadModemData() -> dict:
   with MODEM_DATA_FILE.open("r", encoding="utf-8") as f:
      data = json.load(f)
   return data[0] if isinstance(data, list) else data

# function to get the ports mapping for the specific interface
# - the function returns the port name as a string
# - if interface is not detected return None
def getModemInterfaces(interface):
   # GET the modems connected to the system
   result = subprocess.run(
      f"ls -l /dev/serial/by-id/ | grep Android | grep {interface} | cut -f 11 | cut -d '/' -f 3",
      shell=True,
      capture_output=True,
      text=True,
   )
   return "/dev/" + result.stdout.strip() if result.stdout.strip() else None

def getModemPorts() -> dict:
   modems = loadModemData()
   for modem in modems:
         return { "modem": modem, 
                  "Diag": getModemInterfaces(modems[modem]['Diag']), 
                  "NMEA": getModemInterfaces(modems[modem]['NMEA']), 
                  "AT": getModemInterfaces(modems[modem]['AT']), 
                  "Modem": getModemInterfaces(modems[modem]['Modem']), 
                  "NDIS": getModemInterfaces(modems[modem]['NDIS'])
                }
   # if modem is not detected return interface value as None
   return { "modem": None, 
            "Diag": None, 
            "NMEA": None, 
            "AT": None, 
            "Modem": None, 
            "NDIS": None
          }

# function to test the module
# - the function tests the module by loading the modem data and initializing the AT port
# - the function prints the modem data and the AT port mapping
if __name__ == "__main__":
   modems = loadModemData()
   print(modems)
   a = getModemPorts()
   print(a)

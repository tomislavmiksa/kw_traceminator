import json
import subprocess
from pathlib import Path

MODEM_DATA_FILE = Path(__file__).parent / "data" / "modem.json"

# function to load the modem data from the JSON file
# - the file contains the modem name and the corresponding interfaces mapping (AT, NMEA, Diag, Modem, NDIS)
# - the function returns the modem data as a array of dictionaries
def loadModemData() -> list:
   with MODEM_DATA_FILE.open("r", encoding="utf-8") as f:
      data = json.load(f)
   return data

# function to get the modem type
# - the function returns the modem type and the mapping as a tuple
# - if modem is not detected return None, None
def getModemType(modems) -> tuple:
   for modem in modems:
      m = list(modem.keys())[0]
      mapping = modem[m]
      result = subprocess.run(
         f"lsusb | grep {m} | wc -l",
         shell=True,
         capture_output=True,
         text=True,
      )
      if result.stdout.strip() != "0":
         return m, mapping
   return None, None

# function to get the ports mapping for the specific interface
# - the function returns the port name as a string
# - if interface is not detected return None
def getModemInterfaces(interface):
   # GET the modems connected to the system
   result = subprocess.run(
      f"ls -l /dev/serial/by-id/ | grep -e Android -e Qualcomm -e Quectel| grep {interface} | cut -f 11 | cut -d '/' -f 3",
      shell=True,
      capture_output=True,
      text=True,
   )
   print(result.stdout.strip())
   return "/dev/" + result.stdout.strip() if result.stdout.strip() else None

def getModemPorts() -> dict:
   modems = loadModemData()
   m, mapping = getModemType(modems)
   if m is not None:
      for i in ['Diag', 'NMEA', 'AT', 'Modem', 'NDIS']:
         if i in mapping:
            mapping[i] = getModemInterfaces(mapping[i])
         else:
            mapping[i] = None
      mapping['modem'] = m
      return mapping
   else:
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
   m, mapping = getModemType(modems)
   print(m, mapping)
   a = getModemPorts()
   print(a)

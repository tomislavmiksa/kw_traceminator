import subprocess

def initializeAtPort():
   # INITIALIZE THE AT PORT
   # - if no modem is detected, exit the program
   # - if modem is detected, map the AT command to the corresponding port
   result = subprocess.run(
      "lsusb | grep Quectel | grep EC25 | wc -l",
      shell=True,
      capture_output=True,
      text=True,
   )
   if int(result.stdout) > 0:
      # EC25 modem is detected, mapping the AT command to the corresponding port
      # - if00 -> Diag port
      # - if01 -> NMEA port
      # - if02 -> AT port
      # - if03 -> Modem port
      # - if04 -> NDIS port
      result = subprocess.run(
         "ls -l /dev/serial/by-id/ | grep Android | grep if02 | awk '{print $11}' | cut -d '/' -f 3",
         shell=True,
         capture_output=True,
         text=True,
      )
      print(f"AT port: {result.stdout}")
      return "Quectel EC25", result.stdout.strip()
   else:
      # EC25 modem is not detected, return error
      return None,None
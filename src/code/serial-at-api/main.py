import re
import serial
import time

from modules.detectAT import getModemPorts
from flask import Flask, request, jsonify

# INITIALIZE THE AT PORT
# - makes no sense to proceed if the modem is not detected
# - if no modem is detected, exit the program
# - if modem is detected, map the AT command to the corresponding port
ports = getModemPorts()
if 'AT' not in ports:
   print("ERROR: no valid modem detected")
   exit(1)
port = ports['AT']

app = Flask(__name__)

# the entry point to return the basic information about the API
# call: curl http://localhost:8666/
@app.route("/")
def root():
   return { "Version" : "1.0.0" , "Modem": ports, "Description": "API to send AT commands to the modem" }

# this is the most important call and the reason why all this is running at all
# is is used to communicate and control the modem
# call: curl --request POST --header  "Content-Type: application/json" --data '{"cmd": "ATI"}' http://localhost:8666/at
@app.route("/at", methods=['POST'])
def sendAt():
   # verify if command passed is AT command
   regex = "^[aA][tT].*"
   # parse JSON parameters required
   content = request.get_json(silent=True)
   if content is None:
      return { "Response" : "400 - Bad request" }
   elif 'cmd' not in content.keys():
      return { "Response" : "400 - Bad request" }
   elif content['cmd'] is None:
      return { "Response" : "400 - Bad request" }
   elif not re.match(regex, content['cmd']):
      return { "Response" : "400 - Bad request" }
   else:
      # establish serial connection
      s =  serial.Serial(port=port,baudrate=115200,timeout=0,rtscts=0,xonxoff=0)
      # clear the old junk if any
      # s.flushInput()
      # s.flushOutput()
      # send command
      cmd = content['cmd'].strip() + '\r\n'
      if 'timeout' in content:
         if content['timeout'] is None:
            timeout = 2
      else:
         timeout = 2
      print( s.write(cmd.encode(encoding = 'ascii', errors = 'strict')) ) 
      # Get response
      # - wait if the modem is busy
      time.sleep(timeout)
      resp = s.readall().decode('utf-8').strip()
      # make it more readable
      resp = re.sub(r"[\r\n]+", ";", resp)          # replace new lines with semicolon
      resp = re.sub(r"(?:\\[rn])+", ";",  resp)     # replace carriage return with semicolon
      resp = re.sub(r"(?:\s*;\s*)+", ";",  resp)    # replace multiple semicolons with a single semicolon
      # close serial connection
      s.close()
      return { "Response" : "200", "cmd": content['cmd'].strip(), "response": resp }

# returns the information about the modem port mappings
# will be used by other modules to get the correct mapping for the modem
# call: curl http://localhost:8666/modem
@app.route("/modem", methods=['GET'])
def getModemInterfaces():
   return jsonify(ports)

if __name__ == "__main__":
   app.run(host="0.0.0.0", port=8666, debug=False)
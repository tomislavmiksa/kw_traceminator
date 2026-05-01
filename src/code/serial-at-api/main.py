import re
import serial
import time

from modules.detectAT import initializeAtPort
from flask import Flask, request, jsonify

# INITIALIZE THE AT PORT
# - if no modem is detected, exit the program
# - if modem is detected, map the AT command to the corresponding port
modem, port = initializeAtPort()
port = "/dev/" + port
if port is None:
   print("ERROR: no valid modem detected")
   exit(1)

app = Flask(__name__)

# the entry point to return the basic information about the API
# curl http://localhost:5000/
@app.route("/")
def root():
   return { "Version" : "1.0.0" , "Modem": modem, "AT port": port, "Description": "API to send AT commands to the modem" }

# this is the most important call and the reason why all this is running at all
# is is used to communicate and control the modem
# curl --request POST --header  "Content-Type: application/json" --data '{"cmd": "ATI"}' http://localhost:5000/at
@app.route("/at", methods=['POST'])
def sendAt():
   # parse JSON parameters required
   content = request.get_json(silent=True)
   # verify if command passed is AT command
   regex = "^[aA][tT].*"
   if content['cmd'] is not None and re.match(regex, content['cmd']):
      
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
      resp = s.readall().decode('utf-8').rstrip()

      # close serial connection
      s.close()
      return { "Response" : "200", "cmd": cmd, "response": resp }
   else:
      return { "Response" : "400 - Bad request" }

if __name__ == "__main__":
   app.run(host="0.0.0.0", port=8666, debug=False)
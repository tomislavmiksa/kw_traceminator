import re
import serial
import time

from flask import Flask, request, jsonify

port = "/dev/ttyUSB2"
app = Flask(__name__)

@app.route("/")
def hello_world():
   return { "Version" : "1.0.0" }

@app.route("/test")
def test():
   return { "Version" : "1.0.0" }

# curl --request POST --header  "Content-Type: application/json" --data '{"cmd": "ATI", "timeout": 1}' http://localhost:5000/sendAtCmd
@app.route("/sendAtCmd", methods=['POST'])
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
      if content['timeout'] is None:
         timeout = 2
      else:
         timeout = content['timeout']
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
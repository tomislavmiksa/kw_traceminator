1:sh:date:::
2:at:AT:OK:5::
3:at:AT+CGMI::::
4:at:AT+CGMM::::
5:at:AT+GSN::::
6:at:ATI::::
9:at:AT+CMEE=2::::

30:at:AT+CPIN?:READY:3::goto 1
31:at:AT+QCCID:::
32:at:AT+CIMI:::

40:at:AT+COPS?:OK::
41:at:AT+QCFG="roamservice":2::
42:at:AT+QSPN:::
43:at:AT+QENG="servingcell":::
50:at:AT+CGDCONT?:data.apn.name:3:goto 60:
51:at:AT+CGDCONT=1,"IP","data.apn.name"

60:at:AT+CREG=2::::
61:at:AT+CREG?:2,(1|5):20::goto 40
70:at:AT+QIACT?:\.::goto 80:
71:at:AT+QIACT=1::::
72:sh:sleep 10::::
80:at:AT+CCLK?::::

90:at:AT+QIOPEN=1,0,"TCP","postman-echo.com",80,1234,0::::
91:sh:sleep 3::::
92:at:AT+QISTATE=1,0::::
93:at:AT+QICLOSE=1::::

100:sh:sleep 30:::goto 1:


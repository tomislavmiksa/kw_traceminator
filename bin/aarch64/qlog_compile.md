# Steps to compile QLog 

This instructions are valid for Rapberry Pi

The OS is 

```bash
unzip QLog_Linux_Android_V1.9.zip
cd QLog_Linux_Android_V1.9/

sudo apt update
udo add-apt-repository universe
sudo apt install build-essential qtbase5-dev qtchooser qt5-qmake qttools5-dev libqt5serialport5-dev qtwebengine5-dev libqt5charts5-dev libhamlib-dev qtkeychain-qt5-dev pkg-config
qmake QLog.pro
make
sudo make install
```
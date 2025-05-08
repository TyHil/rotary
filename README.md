# Rotary

Specialized Python program run on my Raspberry Pi that interfaces with a rotary phone dial to control my bedside lamp and LED Strip. The lights are plugged into smart plugs which allows them to be controlled via Samsung's SmartThings API. The LED strip runs on an Arduino (code [here](https://github.com/TyHil/led-strip-effects-and-game/)) which allows it to be controlled over serial to change mode and act as a light alarm.

> [!IMPORTANT]
> This project requires a SmartThings Personal Access Token (PAT) generated before December 30th 2024. Otherwise, the token will need to be changed every 24 hours.

<img alt="The device on the wall" src="Photos/20250131_221023.jpg" width="500"/>

## Setup

1. Clone the project and install packages:

```
git clone https://github.com/TyHil/rotary.git
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. Ensure the Serial interface is enabled by running `sudo raspi-config` and navigating to "Interface Options" then "Serial" and choosing "No" to the login shell over serial and "Yes" to enable the serial hardware.

3. Run `cp src/config.example.py src/config.py` and add your SmartThings token to the new file.

4. Run `cp src/alarms.example.py src/alarms.py` and add your alarm times to the new file.

5. Run `cp rotary.example.service /etc/systemd/system/rotary.service`, edit the new file to have the correct `User` and `ExecStart` for you, and run `sudo systemctl daemon-reload`.

6. Optionally add the contents of `example.bash_aliases` to your `~/.bash_aliases` or run `mv example.bash_aliases ~/.bash_aliases`.

7. Connect your rotary dial to GND and GPIO18 (pins 6 and 12) and your RPI->Arduino to 3V3->3V3, GPIO4->GND, GPIO14->RX, and GPIO15->TX (pins 1, 7, 8, and 12). Use a voltage level-shifter if your Arduino does not run in 3.3 volts.

8. Finally run `source ~/.bash_aliases` and `rotary start` to start the progam.

## License

GPL-3.0 License

# Raspberry Pi Hand Tool Monitor & Media Kiosk

A Raspberry Pi application using Pygame to display real-time voltage, current, and power readings from a Modbus RTU device (RS-485), aimed at monitoring hand tools. Features GPIO button input for navigation and basic image/video playback from local storage. Designed for fullscreen kiosk-style operation.

[![Optional Screenshot](placeholder_screenshot.png)]()

## Features

*   **Real-time Sensor Display:** Shows Voltage (V), Current (A), and calculated Power (W) read from a Modbus RTU slave device via RS-485.
*   **Fullscreen GUI:** Utilizes Pygame for a clean, full-screen display suitable for dedicated screens/kiosks.
*   **Media Playback:** Displays locally stored images (.png, .jpg, .jpeg) and plays videos (.mp4, .avi, .mov) using OpenCV.
*   **GPIO Button Control:** Uses physical buttons connected to Raspberry Pi GPIO pins for navigating between media items and the sensor display screen.
*   **Startup Sequence:** Automatically cycles through configured media files on startup before defaulting to the sensor display (configurable timeout).
*   **Visual Alerts:** Includes an optional blinking indicator for the current display box when readings exceed a defined threshold.
*   **RS-485 RTS Control:** Implements direction control for non-automatic RS-485 adapters using the serial port's RTS signal (requires hardware modification and kernel support).

## Hardware Requirements

*   **Raspberry Pi:** Model 3B+ or 4 Recommended.
*   **Display:** HDMI or DSI display connected to the Pi. Touchscreen optional but supported for interaction.
*   **RS-485 Converter (USB or HAT):**
    *   **IMPORTANT:** The provided code uses **kernel RTS control** (`pyserial.rs485.RS485Settings`). This method **REQUIRES** either:
        *   An RS-485 converter that specifically features **Automatic Direction Control / Auto Flow Control**.
        *   OR a simpler converter where you can **physically connect the converter's `DE` (Data Enable) pin to the `RTS` (Request To Send) output pin** of the USB-to-Serial chip on the *same converter board*. (See Wiring section). Simple converters without this modification *will not work* with this code.
*   **Modbus RTU Slave Device:** The sensor or meter providing Voltage/Current readings.
*   **GPIO Push Buttons:** Connected to the Raspberry Pi's GPIO header (number configured in the script).
*   **Power Supply:** Adequate power supply for the Raspberry Pi and connected peripherals.
*   **SD Card:** With Raspberry Pi OS installed.
*   **Wiring:** Jumper wires (e.g., Dupont cables) for GPIO connections.

## Software Dependencies

*   **OS:** Raspberry Pi OS (Desktop version recommended for GUI development/testing).
*   **Python:** Version 3.7 or higher.
*   **Libraries:**
    *   `pygame`: For the graphical user interface.
    *   `pymodbus`: For Modbus RTU communication.
    *   `pyserial`: (Version 3.0 or higher **required** for `rs485_mode`). Used for serial port configuration and RTS control.
    *   `opencv-python`: For video playback (`cv2`).
    *   `RPi.GPIO`: For button input.
*   **Git:** For cloning the repository.

## Installation

1.  **Update System:**
    ```bash
    sudo apt update
    sudo apt upgrade -y
    ```

2.  **Install Dependencies:**
    ```bash
    sudo apt install -y python3-pip libopenjp2-7 libtiff5 libatlas-base-dev libjpeg-dev zlib1g-dev libpython3-dev # Pre-requisites for OpenCV/Pillow if needed
    pip3 install pygame pymodbus "pyserial>=3.0" opencv-python RPi.GPIO
    ```
    *(Note: Installing OpenCV can sometimes be lengthy).*

3.  **Enable Serial Port & Disable Serial Console:**
    *   Run `sudo raspi-config`.
    *   Navigate to `3 Interface Options`.
    *   Navigate to `P6 Serial Port`.
    *   Select `<No>` when asked "Would you like a login shell to be accessible over serial?".
    *   Select `<Yes>` when asked "Would you like the serial port hardware to be enabled?".
    *   Finish and Reboot if prompted.

4.  **Clone Repository:**
    ```bash
    cd ~ # Or your preferred directory
    git clone https://github.com/ShubhamRaskar00/hand-tool-monitor
    cd hand-tool-monitor 
    ```

5.  **Grant Serial Port Access:** Add your user (e.g., `pi`) to the `dialout` group:
    ```bash
    sudo usermod -a -G dialout $USER
    ```
    You **must log out and log back in** (or reboot) for this change to take effect.

## Configuration

Edit the main Python script (`hand_tool_monitor.py` or your chosen filename) to adjust settings within the "Constants" section near the top:

*   `MEDIA_FOLDER`: Path to the directory containing your images and videos.
*   `BUTTON_PINS`: List of GPIO BCM pin numbers used for your buttons.
*   `BUTTON_MEDIA_MAP`: Dictionary mapping GPIO pins to media file indices (starting from 0).
*   `BUTTON_VOLTAGE_DISPLAY`: GPIO pin number dedicated to showing the sensor screen.
*   `MODBUS_PORT`: Serial port device name (usually `/dev/ttyUSB0` or `/dev/ttyAMA0` or `/dev/ttyS0`).
*   `MODBUS_BAUDRATE`, `SERIAL_PARITY`, `SERIAL_STOPBITS`, `SERIAL_BYTESIZE`: Must match your Modbus slave device settings.
*   `MODBUS_UNIT_ID`: The Modbus Slave ID of your sensor device.
*   `CURRENT_BLINK_THRESHOLD`: The current reading (Amps) above which the current display box will blink red.
*   Other timing constants (`STARTUP_TIMEOUT`, `MODBUS_READ_INTERVAL`, etc.) as needed.

## Wiring

**1. RS-485 Converter (Using RTS Control - Method 1 from prompt)**

*   Connect the Raspberry Pi's USB port to the USB input of your RS-485 Converter.
*   Connect the **A(+)** terminal on the converter to the **A(+)** terminal on your Modbus Slave device.
*   Connect the **B(-)** terminal on the converter to the **B(-)** terminal on your Modbus Slave device.
*   Connect the **GND** terminal on the converter to the **GND** terminal on your Modbus Slave device (recommended for noise immunity).
*   **CRITICAL HARDWARE MODIFICATION:**
    *   You **must** connect the **`DE` (Data Enable)** pin (or equivalent single direction-control pin) on the converter PCB **directly to the `RTS` (Request To Send)** pin/pad of the USB-to-Serial chip (e.g., FT232RL, CH340) on that *same converter PCB*. This might require soldering a small wire.
    *   Ensure the **`RE` (Receive Enable)** pin is permanently enabled (usually tied to Ground/LOW) or appropriately linked (often inversely) to the `DE` pin, according to your converter's specific design.
    *   **Consult your specific converter's schematic or documentation.**

**2. GPIO Buttons**

*   Connect one side of each push button to a Ground (GND) pin on the Raspberry Pi.
*   Connect the other side of each push button to the corresponding GPIO pin defined in the `BUTTON_PINS` list (using BCM numbering).
*   *(The script uses `pull_up_down=GPIO.PUD_DOWN`, meaning it expects the pin to go HIGH when the button connects it to 3.3V. Adjust wiring or `PUD` setting if needed. For `PUD_DOWN`, connect button between GPIO pin and 3.3V. For `PUD_UP`, connect button between GPIO pin and GND).* Double-check the final `PUD_` setting in your code and wire accordingly.

## Autorun on Startup (Desktop Method - As per Bald Guy DIY Video)

This method uses the LXDE/XDG autostart mechanism to launch the script *after* the graphical desktop environment has loaded. It is suitable for GUI applications like this one.

1.  **Open Terminal:** Access the command line on your Raspberry Pi.

2.  **Navigate to Autostart Directory:**
    The autostart directory is typically hidden in your user's config folder. Use `cd` to navigate there. Create it if it doesn't exist:
    ```bash
    mkdir -p ~/.config/autostart
    cd ~/.config/autostart
    ```

3.  **Create a `.desktop` File:**
    Use a text editor (like `nano` or `mousepad`) to create a new file. The filename should end with `.desktop`. Let's call it `hand_tool_monitor.desktop`:
    ```bash
    nano hand_tool_monitor.desktop
    ```

4.  **Paste the Following Content:**
    Copy the text below and paste it into the editor.

    ```ini
    [Desktop Entry]
    Name=Hand Tool Monitor Kiosk
    Comment=Starts the Modbus sensor and media display application
    Exec=python3 /home/pi/hand-tool-monitor/hand_tool_monitor.py
    Path=/home/pi/hand-tool-monitor/
    Type=Application
    Terminal=true
    StartupNotify=false
    Encoding=UTF-8
    Hidden=false
    ```

5.  **IMPORTANT: Modify the `Exec` and `Path` lines:**
    *   **`Exec=`:** Replace `/home/pi/hand-tool-monitor/hand_tool_monitor.py` with the **absolute, full path** to *your* Python script. Make sure this path is correct!
    *   **`Path=`:** Replace `/home/pi/hand-tool-monitor/` with the **absolute, full path** to the *directory* containing your Python script. Setting this working directory helps the script find relative resources like the `media` folder correctly.

6.  **Terminal Setting:**
    *   `Terminal=true`: As shown in the video, this will open a terminal window when the script starts. This is useful for seeing startup messages, print statements for debugging, and error messages.
    *   `Terminal=false`: For a cleaner kiosk look (no terminal window visible), change this to `false` **after** you are sure the script runs correctly. Errors might not be obvious if the terminal is hidden.

7.  **Save and Close:**
    *   If using `nano`: Press `Ctrl+X`, then `Y` to confirm saving, then `Enter`.

8.  **Reboot:**
    ```bash
    sudo reboot
    ```

After the Raspberry Pi reboots and the desktop loads, your Python script should automatically launch (possibly opening a terminal window first if `Terminal=true`).

**Troubleshooting Autostart:**
*   **Path Incorrect:** The most common issue. Double-check the *full* paths in the `Exec=` and `Path=` lines of the `.desktop` file. Use `pwd` in the terminal in your script's directory to confirm the path.
*   **Permissions:** Ensure the Python script itself has execute permissions (though usually running with `python3` bypasses this). `chmod +x /path/to/your/script.py` (optional).
*   **Script Errors:** Run the script manually from the terminal first (`python3 /path/to/your/script.py`) to ensure it works without errors *before* trying to autostart it. Check for errors in the terminal if using `Terminal=true`.
*   **Dependencies:** Make sure all required libraries are installed for the user the desktop logs in as.
*   **Environment:** Autostart runs slightly differently than a manual terminal launch. Sometimes environment variables are missing. Setting the `Path=` helps mitigate some issues.

## Usage

*   **Manual Start:** Open a terminal, navigate to the script directory, and run:
    ```bash
    python3 hand_tool_monitor.py
    ```
*   **Interaction:** Use the connected GPIO push buttons according to the `BUTTON_PINS` and `BUTTON_MEDIA_MAP` configuration to cycle through media or view the sensor display. Press `ESC` on a connected keyboard to exit the application.

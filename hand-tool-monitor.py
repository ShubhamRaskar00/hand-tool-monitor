import pygame
import sys
import os
import cv2
import RPi.GPIO as GPIO
import time
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import math


# Initialize Pygame
pygame.init()
pygame.mouse.set_visible(False)

# Screen setup with double buffering
info = pygame.display.Info()
screen_width, screen_height = info.current_w, info.current_h
try:
    screen = pygame.display.set_mode((screen_width, screen_height), pygame.FULLSCREEN | pygame.DOUBLEBUF)
except pygame.error as e:
    print(f"Display mode error: {e}. Using FULLSCREEN only.")
    screen = pygame.display.set_mode((screen_width, screen_height), pygame.FULLSCREEN)

# GPIO setup
GPIO.setwarnings(False)
GPIO.cleanup()  # Reset GPIO state to avoid mode conflicts
GPIO.setmode(GPIO.BCM)  # Set mode after cleanup
button_pins = [10, 11, 12, 13, 15]
for pin in button_pins:
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

# Media setup
media_folder = "/home/pi/media"
image_files = [f for f in os.listdir(media_folder) if f.lower().endswith((".png", ".jpg", ".jpeg"))]
video_files = [f for f in os.listdir(media_folder) if f.lower().endswith((".mp4", ".avi", ".mov"))]
media_files = sorted(image_files + video_files)
if len(media_files) < 4:
    print(f"Warning: Only {len(media_files)} media files found, need at least 4")
    pygame.quit()
    sys.exit()
    
# Preload images
preloaded_images = {}
for img in image_files:
    img_path = os.path.join(media_folder, img)
    try:
        image = pygame.image.load(img_path)
        image = pygame.transform.scale(image, (screen_width, screen_height))
        preloaded_images[img] = image
    except Exception as e:
        print(f"Error preloading image {img_path}: {e}")



# ADS1115 setup
i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c)  # Increased data rate for faster sampling
ads.gain = 1  # Gain = 1 for 4.096V range

chan_current = AnalogIn(ads, ADS.P0)  # A0 for current (ACS712)
# Constants
ACS712_SENSITIVITY = 0.66  # 66mV/A for ACS712-05B
VCC = 5.0  # Sensor supply voltage
V_ZERO_CURRENT = VCC / 2  # 2.5V at 0A
NUM_SAMPLES = 200
CALIBRATION_FACTOR = 220  # Adjust based on known voltage

def read_voltage():
    voltage_readings = []
    
    for _ in range(NUM_SAMPLES):
        chan_voltage = AnalogIn(ads, ADS.P1)  # Read from channel 0
        
        voltage_readings.append(chan_voltage.voltage)
        time.sleep(0.01)  # Small delay to capture waveform variation

    # Find min and max values
    V_max = max(voltage_readings)
    V_min = min(voltage_readings)
    print("Analog Value: ", chan_voltage.value, "Voltage: ", chan_voltage.voltage)

    # Calculate peak-to-peak voltage
    V_peak = (V_max - V_min) / 2

    # Calculate RMS voltage
    V_rms = V_peak / math.sqrt(2)

    # Convert to actual AC voltage using calibration factor
    V_actual = V_rms * CALIBRATION_FACTOR
    print("Measured Voltage: {:.2f} V".format(V_actual))
    
    print(f"Measured Voltage: {V_actual:.2f} V")
    return V_actual

def read_current():
    """Read current from ACS712 sensor."""
    V_measured = chan_current.voltage  # Voltage output from ACS712

    # Convert voltage to current
    current = (V_measured - V_ZERO_CURRENT) / ACS712_SENSITIVITY
    print(f"Measured Current: {current:.2f} A")
    if(current < 0.16):
        current = 0


    return current

def calculate_power(voltage, current):
    """Calculate real power (assuming unity power factor)."""
    return voltage * current


def display_image_with_timeout(image_path, duration):
    """Display an image for a set duration, return pressed button pin."""
    start_time = time.time()
    filename = os.path.basename(image_path)
    if filename in preloaded_images:
        screen.blit(preloaded_images[filename], (0, 0))
        pygame.display.update()
    else:
        return None
    while time.time() - start_time < duration:
        for pin in button_pins:
            if GPIO.input(pin) == GPIO.HIGH:
                time.sleep(0.05)  # Debounce
                if GPIO.input(pin) == GPIO.HIGH:
                    return pin
        time.sleep(0.1)
    return None

def play_video_with_timeout(video_path, duration):
    """Play a video for a set duration, return pressed button pin."""
    start_time = time.time()
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error opening video: {video_path}")
        return None
    frame_rate = cap.get(cv2.CAP_PROP_FPS) or 30
    frame_time = int(1000 / frame_rate)  # Time per frame in ms
    try:
        while time.time() - start_time < duration:
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # Loop video
                continue
            frame = cv2.resize(frame, (screen_width, screen_height))
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_surface = pygame.surfarray.make_surface(frame.swapaxes(0, 1))
            screen.blit(frame_surface, (0, 0))
            pygame.display.update()
            for pin in button_pins:
                if GPIO.input(pin) == GPIO.HIGH:
                    time.sleep(0.05)
                    if GPIO.input(pin) == GPIO.HIGH:
                        return pin
            pygame.time.wait(frame_time)  # Match video frame rate
    finally:
        cap.release()
    return None

def play_video(video_path):
    """Play a video until interrupted by a button or exit event."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error opening video: {video_path}")
        return None
    clock = pygame.time.Clock()
    frame_rate = cap.get(cv2.CAP_PROP_FPS) or 30
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            frame = cv2.resize(frame, (screen_width, screen_height))
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_surface = pygame.surfarray.make_surface(frame.swapaxes(0, 1))
            screen.blit(frame_surface, (0, 0))
            pygame.display.update()
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                    return None
            for pin in button_pins:
                if GPIO.input(pin) == GPIO.HIGH:
                    time.sleep(0.05)
                    if GPIO.input(pin) == GPIO.HIGH:
                        return pin
            clock.tick(frame_rate)
    finally:
        cap.release()

def display_media(media_path):
    """Display media based on file type."""
    filename = os.path.basename(media_path)
    if filename in preloaded_images:
        screen.blit(preloaded_images[filename], (0, 0))
        pygame.display.update()
    elif media_path.lower().endswith((".mp4", ".avi", ".mov")):
        play_video(media_path)
        
# Fonts
font = pygame.font.SysFont("Arial", int(screen_height * 0.10))  # Values
title_font = pygame.font.SysFont("Arial", int(screen_height * 0.08))  # Title
label_font = pygame.font.SysFont("Arial", int(screen_height * 0.05))  # Labels
border_radius = 20
padding = 10

def display_voltage_current():
    """Display voltage, current, and power with real sensor data."""
    running = True
    while running:
        screen.fill((0, 0, 0))  # Clear screen
        BLACK = (0, 0, 0)
        WHITE = (255, 255, 255)
        YELLOW = (255, 255, 0)
        RED = (255, 0, 0)


        # Title
        title_text = title_font.render("Hand tools rated voltage and rated current", True, YELLOW)
        screen.blit(title_text, title_text.get_rect(center=(screen_width // 2, int(screen_height * 0.05))))

        # Section dimensions
        section_width = int(screen_width * 0.8)
        section_height = int(screen_height * 0.15)
        section_x = (screen_width - section_width) // 2
        y1, y2, y3 = [int(screen_height * (0.2 + i * 0.2)) for i in range(3)]
        value_width = int(section_width * 0.2)
        value_x = section_x + int(section_width * 0.6)
        unit_x_center = value_x + value_width + (section_width - (value_x + value_width - section_x)) // 2

        # Sensor readings
        voltage = read_voltage()
        current = read_current()
        power = calculate_power(voltage, current)
        
        
        
        if voltage < 20:
            voltage = 0
        
        # Get the current time in milliseconds
        current_time = pygame.time.get_ticks()

        # Check if power is greater than 10
        if current > 10:
        # Make the rectangle blink every 500ms (adjust as needed)
            rect_color = RED if (current_time // 100) % 2 == 0 else WHITE
        else:
            rect_color = WHITE  # Stay white when power is 10 or below

        # Power Consumption
        pygame.draw.rect(screen, WHITE, (section_x, y1, section_width, section_height), border_radius=border_radius)
        pygame.draw.rect(screen, BLACK, (value_x, y1 + padding, value_width, section_height - 2 * padding))
        power_label = label_font.render("POWER CONSUMPTION", True, BLACK)
        screen.blit(power_label, power_label.get_rect(midleft=(section_x + 60, y1 + section_height // 2)))
        power_value = font.render(f"{power:.1f}", True, YELLOW)
        screen.blit(power_value, power_value.get_rect(center=(value_x + value_width // 2, y1 + section_height // 2)))
        power_unit = font.render("W", True, BLACK)
        screen.blit(power_unit, power_unit.get_rect(center=(unit_x_center, y1 + section_height // 2)))

        # Rated Voltage
        pygame.draw.rect(screen, WHITE, (section_x, y2, section_width, section_height), border_radius=border_radius)
        pygame.draw.rect(screen, BLACK, (value_x, y2 + padding, value_width, section_height - 2 * padding))
        voltage_label = label_font.render("RATED VOLTAGE", True, BLACK)
        screen.blit(voltage_label, voltage_label.get_rect(midleft=(section_x + 60, y2 + section_height // 2)))
        voltage_value = font.render(f"{voltage:.1f}", True, YELLOW)
        screen.blit(voltage_value, voltage_value.get_rect(center=(value_x + value_width // 2, y2 + section_height // 2)))
        voltage_unit = font.render("V", True, BLACK)
        screen.blit(voltage_unit, voltage_unit.get_rect(center=(unit_x_center, y2 + section_height // 2)))

        # Rated Current
        pygame.draw.rect(screen, rect_color, (section_x, y3, section_width, section_height), border_radius=border_radius)
        pygame.draw.rect(screen, BLACK, (value_x, y3 + padding, value_width, section_height - 2 * padding))
        current_label = label_font.render("RATED CURRENT", True, BLACK)
        screen.blit(current_label, current_label.get_rect(midleft=(section_x + 60, y3 + section_height // 2)))
        current_value = font.render(f"{current:.1f}", True, YELLOW)
        screen.blit(current_value, current_value.get_rect(center=(value_x + value_width // 2, y3 + section_height // 2)))
        current_unit = font.render("A", True, BLACK)
        screen.blit(current_unit, current_unit.get_rect(center=(unit_x_center, y3 + section_height // 2)))

        pygame.display.update()
        
        # Check for button press to exit
        for pin in button_pins:
            if GPIO.input(pin) == GPIO.HIGH:
                time.sleep(0.05)  # Debounce
                if GPIO.input(pin) == GPIO.HIGH:
                    running = False  # Exit loop when a button is pressed

            # Check for Pygame quit event (ESC key or window close)
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                running = False

        time.sleep(1)  # Small delay to update every second
    
# Button actions
button_actions = {
    10: lambda: display_media(os.path.join(media_folder, media_files[0])),
    11: lambda: display_media(os.path.join(media_folder, media_files[1])),
    12: display_voltage_current,
    13: lambda: display_media(os.path.join(media_folder, media_files[2])),
    15: lambda: display_media(os.path.join(media_folder, media_files[3]))
}

def startup_display(media_path):
    """Display startup media and return pressed button pin."""
    if media_path.lower().endswith((".png", ".jpg", ".jpeg")):
        return display_image_with_timeout(media_path, 30)
    elif media_path.lower().endswith((".mp4", ".avi", ".mov")):
        return play_video_with_timeout(media_path, 30)
    return None

# Startup sequence
for media in media_files[:4]:
    media_path = os.path.join(media_folder, media)
    pressed_pin = startup_display(media_path)
    if pressed_pin:
        button_actions[pressed_pin]()
        break
else:
    display_voltage_current()
    
# Main loop
running = True
DEBOUNCE_TIME = 0.2
last_press_times = {pin: 0 for pin in button_pins}
while running:
    current_time = time.time()
    for event in pygame.event.get():
        if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
            running = False
    for pin in button_pins:
        if GPIO.input(pin) == GPIO.HIGH and (current_time - last_press_times[pin]) > DEBOUNCE_TIME:
            last_press_times[pin] = current_time
            button_actions[pin]()
    pygame.time.wait(10)

# Cleanup
GPIO.cleanup()
pygame.quit()
sys.exit()


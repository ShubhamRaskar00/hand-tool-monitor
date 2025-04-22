import pygame
import sys
import os
import cv2
import RPi.GPIO as GPIO
import time
import traceback

# --- Modbus Imports ---
from pymodbus.client.sync import ModbusSerialClient as ModbusClient
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.exceptions import ConnectionException
# --- End Modbus Imports ---

# --- Constants ---
MEDIA_FOLDER = "/home/pi/media"
BUTTON_PINS = [4, 17, 27, 23, 24]  # GPIO BCM Pins
MODBUS_PORT = "/dev/ttyUSB0"
MODBUS_BAUDRATE = 9600
MODBUS_UNIT_ID = 0x1
MODBUS_TIMEOUT = 0.5  # Shorter timeout for faster failure detection
MODBUS_READ_INTERVAL = 0.8 # Seconds between sensor reads (adjust if needed)

# Media files indices mapping to buttons (adjust if file order changes)
BUTTON_MEDIA_MAP = {
    4: 0,
    17: 1,
    23: 2,
    24: 3
}
BUTTON_VOLTAGE_DISPLAY = 27 # Button dedicated to voltage display

STARTUP_MEDIA_COUNT = 4
STARTUP_TIMEOUT = 15 # Shorter startup timeout per media

# Timing and Debounce
DEBOUNCE_TIME = 0.15  # Shorter debounce for quicker response (adjust if bounce occurs)
MAIN_LOOP_WAIT_MS = 30 # Small wait in main loop (milliseconds)
SENSOR_DISPLAY_WAIT_MS = 50 # Wait in sensor display loop
VIDEO_FRAME_WAIT_SAFETY_MARGIN_MS = 5 # Added to frame time for stability
MEDIA_WAIT_MS = 50 # Wait while showing static image

# Display Colors
COLOR_BLACK = (0, 0, 0)
COLOR_WHITE = (255, 255, 255)
COLOR_YELLOW = (255, 255, 0)
COLOR_RED = (255, 0, 0)

# Current Threshold for Blinking Box
CURRENT_BLINK_THRESHOLD = 10.0 # Amps

# --- Pygame Initialization ---
pygame.init()
pygame.mouse.set_visible(False)

# Screen setup
info = pygame.display.Info()
screen_width, screen_height = info.current_w, info.current_h
try:
    # Explicitly request hardware acceleration if available, along with double buffering
    screen = pygame.display.set_mode((screen_width, screen_height), pygame.FULLSCREEN | pygame.DOUBLEBUF | pygame.HWSURFACE)
    print("Using FULLSCREEN, DOUBLEBUF, HWSURFACE")
except pygame.error as e:
    print(f"Hardware surface error: {e}. Falling back.")
    try:
        screen = pygame.display.set_mode((screen_width, screen_height), pygame.FULLSCREEN | pygame.DOUBLEBUF)
        print("Using FULLSCREEN, DOUBLEBUF")
    except pygame.error as e2:
        print(f"Double buffer error: {e2}. Using FULLSCREEN only.")
        screen = pygame.display.set_mode((screen_width, screen_height), pygame.FULLSCREEN)
pygame.display.set_caption("Hand Tool Monitor")


# --- GPIO Setup ---
GPIO.setwarnings(False)
GPIO.cleanup()
GPIO.setmode(GPIO.BCM)
for pin in BUTTON_PINS:
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
print("GPIO setup complete.")

# --- Modbus Client Setup ---
client = ModbusClient(method="rtu", port=MODBUS_PORT, stopbits=1,
                      bytesize=8, parity='N', baudrate=MODBUS_BAUDRATE,
                      timeout=MODBUS_TIMEOUT) # Use constant timeout
modbus_connected = False # Track connection status


# --- Media Loading ---
media_files = []
preloaded_images = {}
try:
    all_files = sorted([f for f in os.listdir(MEDIA_FOLDER) if os.path.isfile(os.path.join(MEDIA_FOLDER, f))])
    media_files = [f for f in all_files if f.lower().endswith((".png", ".jpg", ".jpeg", ".mp4", ".avi", ".mov"))]

    if len(media_files) < STARTUP_MEDIA_COUNT:
        print(f"Error: Only {len(media_files)} media files found in {MEDIA_FOLDER}, need at least {STARTUP_MEDIA_COUNT}.")
        # Allow continuing but some buttons might not work
        # pygame.quit() sys.exit() removed to allow partial function

    for f in media_files:
        if f.lower().endswith((".png", ".jpg", ".jpeg")):
            img_path = os.path.join(MEDIA_FOLDER, f)
            try:
                image = pygame.image.load(img_path).convert() # Use convert() for potential speedup
                image = pygame.transform.scale(image, (screen_width, screen_height))
                preloaded_images[f] = image
            except Exception as e:
                print(f"Error preloading image {img_path}: {e}")
    print(f"Found {len(media_files)} media files. Preloaded {len(preloaded_images)} images.")

except FileNotFoundError:
    print(f"Error: Media folder '{MEDIA_FOLDER}' not found.")
    # Allow continuing, but media buttons won't work
except Exception as e:
    print(f"Error listing/loading media files: {e}")


# --- Font Initialization ---
# Using default fonts for broader compatibility, can be changed to specific TTF files
try:
    font_value = pygame.font.SysFont("Arial", int(screen_height * 0.10), bold=True)
    font_title = pygame.font.SysFont("Arial", int(screen_height * 0.07), bold=True)
    font_label = pygame.font.SysFont("Arial", int(screen_height * 0.05))
except Exception as e:
    print(f"Font loading error: {e}. Using default font.")
    font_value = pygame.font.Font(None, int(screen_height * 0.10)) # Fallback
    font_title = pygame.font.Font(None, int(screen_height * 0.08))
    font_label = pygame.font.Font(None, int(screen_height * 0.05))

# --- Helper Functions ---

def check_modbus_connection():
    """Checks and attempts to establish Modbus connection."""
    global modbus_connected
    if not client.is_socket_open():
        modbus_connected = False
        print("Modbus connecting...")
        try:
            modbus_connected = client.connect()
            if modbus_connected:
                print("Modbus connection successful.")
            else:
                # Don't print failure every time if it keeps failing
                # print("Modbus connection failed.")
                pass
        except Exception as e:
            print(f"Modbus connection error: {e}")
            modbus_connected = False
    else:
        # Socket is open, assume we are connected unless a read fails
        modbus_connected = True
    return modbus_connected

def read_modbus_float32(address):
    """Reads a 32-bit float from two Modbus holding registers."""
    global modbus_connected
    if not modbus_connected:
        if not check_modbus_connection():
            return 0.0 # Return default if connection fails

    try:
        response = client.read_holding_registers(address, 2, unit=MODBUS_UNIT_ID)
        if response.isError():
            print(f"Modbus read error (Addr {address}): {response}")
            modbus_connected = False # Assume disconnect on error
            return 0.0
        decoder = BinaryPayloadDecoder.fromRegisters(response.registers, Endian.Big, wordorder=Endian.Little)
        value = decoder.decode_32bit_float()
        modbus_connected = True # Mark as connected after successful read
        return value
    except ConnectionException as e:
        print(f"Modbus ConnectionException during read (Addr {address}): {e}")
        modbus_connected = False
        client.close() # Ensure socket is closed on connection exception
        return 0.0
    except Exception as e:
        print(f"Exception during Modbus read (Addr {address}): {e}")
        # Consider closing connection here too depending on error type
        # modbus_connected = False
        # client.close()
        return 0.0

def read_voltage():
    """Reads voltage via Modbus."""
    # Address 142 expected
    return read_modbus_float32(142)

def read_current():
    """Reads current via Modbus."""
     # Address 150 expected
    return read_modbus_float32(150)

def calculate_power(voltage, current):
    """Calculates power. Handles potential None or non-numeric inputs."""
    v = voltage if isinstance(voltage, (int, float)) else 0.0
    c = current if isinstance(current, (int, float)) else 0.0
    return abs(v * c) # Often power is positive, but depends on meter


def play_video_cv(video_path, interrupt_pins):
    """Plays a video using OpenCV until interrupted by specified pins or ESC."""
    cap = None
    pressed_pin = None
    clock = pygame.time.Clock()
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"Error opening video: {video_path}")
            return None

        frame_rate = cap.get(cv2.CAP_PROP_FPS)
        if not frame_rate or frame_rate <= 0:
            frame_rate = 30.0
            print(f"Warning: Invalid frame rate for {video_path}, defaulting to {frame_rate}")
        frame_time_ms = int(1000.0 / frame_rate)

        playing = True
        while playing:
            ret, frame = cap.read()
            if not ret:
                # Option 1: Loop the video
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
                # Option 2: Stop playback
                # playing = False
                # continue

            # --- Event and Button Checking ---
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                    print("Video interrupted by QUIT/ESC.")
                    playing = False
                    pressed_pin = "QUIT"
                    break # Exit event loop

            if not playing: break # Exit main loop if quit event detected

            for pin in interrupt_pins:
                if GPIO.input(pin) == GPIO.HIGH:
                     # Minimal debounce inside loop
                     time.sleep(0.02)
                     if GPIO.input(pin) == GPIO.HIGH:
                        print(f"Video interrupted by button {pin}.")
                        playing = False
                        pressed_pin = pin
                        break # Exit button loop
            if not playing: break # Exit main loop if button detected
            # --- End Checking ---


            # --- Frame Display ---
            try:
                # Performance: Resize first
                frame = cv2.resize(frame, (screen_width, screen_height), interpolation=cv2.INTER_NEAREST) # INTER_NEAREST is fastest
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) # Essential conversion
                # Performance: Direct surface creation (avoids extra copy with swapaxes if possible)
                frame_surface = pygame.image.frombuffer(frame.tobytes(), (screen_width, screen_height), "RGB")
                # Previous method (if frombuffer fails or looks wrong):
                # frame_surface = pygame.surfarray.make_surface(frame.swapaxes(0, 1))
                screen.blit(frame_surface, (0, 0))
                pygame.display.flip() # Use flip with double buffering
            except Exception as e:
                 print(f"Error processing/displaying video frame: {e}")
                 playing = False # Stop on error
            # --- End Frame Display ---

            # clock.tick(frame_rate) # Caps FPS but can cause drift
            pygame.time.wait(max(1, frame_time_ms - VIDEO_FRAME_WAIT_SAFETY_MARGIN_MS)) # Alternative timing

    except Exception as e:
        print(f"Error during video playback: {e}")
        traceback.print_exc()
    finally:
        if cap:
            cap.release()
            print(f"Released video capture for {video_path}")
    return pressed_pin


def display_static_image(image_filename, interrupt_pins):
    """Displays a preloaded image until interrupted by specified pins or ESC."""
    if image_filename in preloaded_images:
        screen.blit(preloaded_images[image_filename], (0, 0))
        pygame.display.flip() # Use flip with double buffering
    else:
        print(f"Error: Image '{image_filename}' not preloaded.")
        # Display fallback screen?
        screen.fill(COLOR_BLACK)
        # Optional: Render error text
        pygame.display.flip()
        time.sleep(2) # Show error briefly
        return None

    waiting = True
    pressed_pin = None
    while waiting:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                print("Image display interrupted by QUIT/ESC.")
                waiting = False
                pressed_pin = "QUIT"
                break
        if not waiting: break

        for pin in interrupt_pins:
            if GPIO.input(pin) == GPIO.HIGH:
                 # Minimal debounce
                 time.sleep(0.02)
                 if GPIO.input(pin) == GPIO.HIGH:
                    print(f"Image display interrupted by button {pin}.")
                    waiting = False
                    pressed_pin = pin
                    break
        if not waiting: break

        pygame.time.wait(MEDIA_WAIT_MS) # Reduce CPU usage
    return pressed_pin

def display_media(media_path):
    """Displays image or video based on file type. Returns interrupt pin or 'QUIT'."""
    filename = os.path.basename(media_path)
    interrupt_pins = BUTTON_PINS # Allow any button to interrupt media playback

    if filename.lower().endswith((".png", ".jpg", ".jpeg")):
        return display_static_image(filename, interrupt_pins)
    elif filename.lower().endswith((".mp4", ".avi", ".mov")):
        return play_video_cv(media_path, interrupt_pins)
    else:
        print(f"Error: Unsupported media type or file not found: {media_path}")
        return None


# --- Sensor Display Screen ---

# Pre-render static elements for the sensor display
title_surf = font_title.render("Hand Tool Monitor", True, COLOR_YELLOW)
title_rect = title_surf.get_rect(center=(screen_width // 2, int(screen_height * 0.07)))

power_label_surf = font_label.render("POWER", True, COLOR_BLACK)
voltage_label_surf = font_label.render("VOLTAGE", True, COLOR_BLACK)
current_label_surf_black = font_label.render("CURRENT", True, COLOR_BLACK)
current_label_surf_white = font_label.render("CURRENT", True, COLOR_WHITE) # For red background

power_unit_surf = font_value.render("W", True, COLOR_BLACK)
voltage_unit_surf = font_value.render("V", True, COLOR_BLACK)
current_unit_surf_black = font_value.render("A", True, COLOR_BLACK)
current_unit_surf_white = font_value.render("A", True, COLOR_WHITE) # For red background

# Calculate layout dimensions once
section_width = int(screen_width * 0.75)
section_height = int(screen_height * 0.18)
section_x = (screen_width - section_width) // 2
padding = int(screen_height * 0.015)
border_radius = int(screen_height * 0.03)

y_start = int(screen_height * 0.20)
y_spacing = int(screen_height * 0.22)
y_power, y_voltage, y_current = [y_start + i * y_spacing for i in range(3)]

value_width = int(section_width * 0.25) # Wider value box
value_x = section_x + int(section_width * 0.55) # Adjusted value X position
value_box_height = section_height - 2 * padding
value_box_radius = border_radius // 2

label_x = section_x + int(section_width * 0.25) # Centered label X
unit_x = section_x + int(section_width * 0.9) # Unit X (right aligned)

power_label_rect = power_label_surf.get_rect(center=(label_x, y_power + section_height // 2))
voltage_label_rect = voltage_label_surf.get_rect(center=(label_x, y_voltage + section_height // 2))
current_label_rect_black = current_label_surf_black.get_rect(center=(label_x, y_current + section_height // 2))
current_label_rect_white = current_label_surf_white.get_rect(center=(label_x, y_current + section_height // 2))

power_unit_rect = power_unit_surf.get_rect(center=(unit_x, y_power + section_height // 2))
voltage_unit_rect = voltage_unit_surf.get_rect(center=(unit_x, y_voltage + section_height // 2))
current_unit_rect_black = current_unit_surf_black.get_rect(center=(unit_x, y_current + section_height // 2))
current_unit_rect_white = current_unit_surf_white.get_rect(center=(unit_x, y_current + section_height // 2))


def display_voltage_current():
    """Displays voltage, current, and power with Modbus sensor data."""
    running = True
    last_read_time = 0
    voltage, current, power = 0.0, 0.0, 0.0
    voltage_surf, current_surf, power_surf = None, None, None # Surfaces for values

    while running:
        loop_start_time = time.monotonic() # More precise for timing loops

        # --- Check Events and Buttons ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                print("Sensor display interrupted by QUIT/ESC.")
                running = False
                return "QUIT"

        for pin in BUTTON_PINS:
            if GPIO.input(pin) == GPIO.HIGH:
                 time.sleep(0.02) # Debounce
                 if GPIO.input(pin) == GPIO.HIGH:
                    print(f"Button {pin} pressed, exiting sensor display.")
                    running = False
                    return pin # Return pressed pin
        # --- End Check ---

        # --- Read Modbus Data Periodically ---
        now = time.monotonic()
        if now - last_read_time >= MODBUS_READ_INTERVAL:
            voltage = read_voltage()
            current = read_current()
            # Basic Filtering/Thresholding
            voltage = voltage if voltage > 5.0 else 0.0 # Ignore very low voltage readings
            current = current if current > 0.1 else 0.00 # Ignore very low current readings
            power = calculate_power(voltage, current)

            # --- Re-render value surfaces ONLY when data changes ---
            power_surf = font_value.render(f"{power:.0f}", True, COLOR_YELLOW) # Integer Watts often fine
            voltage_surf = font_value.render(f"{voltage:.1f}", True, COLOR_YELLOW)
            current_surf = font_value.render(f"{current:.1f}", True, COLOR_YELLOW)
            last_read_time = now
            # print(f"Read V:{voltage:.1f} I:{current:.1f} P:{power:.0f}") # Optional debug
        # --- End Modbus Read ---

        # --- Drawing ---
        screen.fill(COLOR_BLACK) # Clear screen

        # Draw Title (pre-rendered)
        screen.blit(title_surf, title_rect)

        # Determine current box color (blinking)
        pygame_time_ms = pygame.time.get_ticks()
        current_box_color = COLOR_WHITE
        if current > CURRENT_BLINK_THRESHOLD:
            if (pygame_time_ms // 400) % 2 == 0: # Faster blink
                current_box_color = COLOR_RED

        # --- Draw Sections ---
        # Power
        pygame.draw.rect(screen, COLOR_WHITE, (section_x, y_power, section_width, section_height), border_radius=border_radius)
        pygame.draw.rect(screen, COLOR_BLACK, (value_x, y_power + padding, value_width, value_box_height), border_radius=value_box_radius)
        screen.blit(power_label_surf, power_label_rect)
        if power_surf: screen.blit(power_surf, power_surf.get_rect(center=(value_x + value_width // 2, y_power + section_height // 2)))
        screen.blit(power_unit_surf, power_unit_rect)

        # Voltage
        pygame.draw.rect(screen, COLOR_WHITE, (section_x, y_voltage, section_width, section_height), border_radius=border_radius)
        pygame.draw.rect(screen, COLOR_BLACK, (value_x, y_voltage + padding, value_width, value_box_height), border_radius=value_box_radius)
        screen.blit(voltage_label_surf, voltage_label_rect)
        if voltage_surf: screen.blit(voltage_surf, voltage_surf.get_rect(center=(value_x + value_width // 2, y_voltage + section_height // 2)))
        screen.blit(voltage_unit_surf, voltage_unit_rect)

        # Current (with dynamic background color)
        pygame.draw.rect(screen, current_box_color, (section_x, y_current, section_width, section_height), border_radius=border_radius)
        pygame.draw.rect(screen, COLOR_BLACK, (value_x, y_current + padding, value_width, value_box_height), border_radius=value_box_radius)
        # Select appropriate pre-rendered label/unit based on background
        current_label_to_blit = current_label_surf_white if current_box_color == COLOR_RED else current_label_surf_black
        current_unit_to_blit = current_unit_surf_white if current_box_color == COLOR_RED else current_unit_surf_black
        current_label_rect_to_use = current_label_rect_white if current_box_color == COLOR_RED else current_label_rect_black
        current_unit_rect_to_use = current_unit_rect_white if current_box_color == COLOR_RED else current_unit_rect_black

        screen.blit(current_label_to_blit, current_label_rect_to_use)
        if current_surf: screen.blit(current_surf, current_surf.get_rect(center=(value_x + value_width // 2, y_current + section_height // 2)))
        screen.blit(current_unit_to_blit, current_unit_rect_to_use)
        # --- End Draw Sections ---


        pygame.display.flip() # Update the full screen
        # --- End Drawing ---

        # Control loop speed
        elapsed_ms = (time.monotonic() - loop_start_time) * 1000
        wait_ms = max(1, SENSOR_DISPLAY_WAIT_MS - int(elapsed_ms))
        pygame.time.wait(wait_ms)

    return None # Return None if loop exited normally (button press handled)


# --- Startup Sequence ---

def run_startup_sequence():
    """Cycles through initial media files or waits for interaction."""
    global next_action
    startup_interrupted = False
    print("Starting startup sequence...")
    for i in range(STARTUP_MEDIA_COUNT):
         if i >= len(media_files):
             print(f"Warning: Not enough media files ({len(media_files)}) for full startup sequence ({STARTUP_MEDIA_COUNT}).")
             break

         media_path = os.path.join(MEDIA_FOLDER, media_files[i])
         filename = media_files[i]
         interrupt_pins = BUTTON_PINS # Any button can interrupt

         pressed_pin = None
         if filename.lower().endswith((".png", ".jpg", ".jpeg")):
             if filename in preloaded_images:
                 print(f"Startup: Displaying image '{filename}'...")
                 screen.blit(preloaded_images[filename], (0,0))
                 pygame.display.flip()
                 start_time = time.monotonic()
                 while time.monotonic() - start_time < STARTUP_TIMEOUT:
                     for event in pygame.event.get(): # Check exit keys
                         if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                             pressed_pin = "QUIT"; break
                     if pressed_pin: break
                     for pin in interrupt_pins: # Check buttons
                         if GPIO.input(pin) == GPIO.HIGH:
                            time.sleep(0.02) # Debounce
                            if GPIO.input(pin) == GPIO.HIGH: pressed_pin = pin; break
                     if pressed_pin: break
                     pygame.time.wait(50) # Don't hog CPU
             else:
                 print(f"Startup: Skipping missing image '{filename}'")
                 time.sleep(1) # Still pause briefly
         elif filename.lower().endswith((".mp4", ".avi", ".mov")):
             print(f"Startup: Playing video '{filename}'...")
             # Simplified video play for timeout - essentially same as play_video_cv but with timeout arg
             # Reusing play_video_cv by passing timeout and handling result
             # NOTE: Reimplementing inline is cleaner if `play_video_cv` logic is complex.
             # Here, just calling `play_video_cv` and checking its result implies it runs indefinitely.
             # Need a dedicated timed play function or add timeout logic to `play_video_cv`
             # -- Quick fix: using the `play_video_with_timeout` logic directly here ---
             start_time = time.monotonic()
             cap = None
             try:
                cap = cv2.VideoCapture(media_path)
                if cap.isOpened():
                    frame_rate = cap.get(cv2.CAP_PROP_FPS) or 30.0
                    frame_time_ms = int(1000.0 / frame_rate)
                    while time.monotonic() - start_time < STARTUP_TIMEOUT:
                        ret, frame = cap.read()
                        if not ret: cap.set(cv2.CAP_PROP_POS_FRAMES, 0); continue
                        # Check events/buttons
                        for event in pygame.event.get():
                           if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                               pressed_pin = "QUIT"; break
                        if pressed_pin: break
                        for pin in interrupt_pins:
                            if GPIO.input(pin) == GPIO.HIGH:
                               time.sleep(0.02)
                               if GPIO.input(pin) == GPIO.HIGH: pressed_pin = pin; break
                        if pressed_pin: break
                        # Display Frame
                        try:
                            frame = cv2.resize(frame, (screen_width, screen_height), interpolation=cv2.INTER_NEAREST)
                            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            frame_surface = pygame.image.frombuffer(frame.tobytes(), (screen_width, screen_height), "RGB")
                            screen.blit(frame_surface, (0,0))
                            pygame.display.flip()
                        except Exception as e: print(f"Frame display error: {e}"); break # Exit inner loop on error
                        # Wait
                        pygame.time.wait(max(1, frame_time_ms - VIDEO_FRAME_WAIT_SAFETY_MARGIN_MS))
                else: print(f"Failed to open startup video: {filename}")
             except Exception as e: print(f"Error during startup video play: {e}")
             finally:
                 if cap: cap.release()
             # --- End quick fix video ---

         else:
              print(f"Startup: Skipping unsupported file '{filename}'")
              time.sleep(1)


         # --- Handle result of startup item ---
         if pressed_pin == "QUIT":
             print("Startup interrupted by QUIT.")
             next_action = "QUIT" # Signal main loop to exit
             startup_interrupted = True
             break
         elif pressed_pin in BUTTON_PINS:
             print(f"Startup interrupted by button {pressed_pin}.")
             # Map button press directly to an action
             if pressed_pin == BUTTON_VOLTAGE_DISPLAY:
                 next_action = display_voltage_current
             elif pressed_pin in BUTTON_MEDIA_MAP:
                 media_index = BUTTON_MEDIA_MAP[pressed_pin]
                 if 0 <= media_index < len(media_files):
                     media_path = os.path.join(MEDIA_FOLDER, media_files[media_index])
                     next_action = lambda p=media_path: display_media(p) # Use lambda to capture path
                 else:
                      print(f"Warning: Media index {media_index} out of range for button {pressed_pin}.")
                      next_action = display_voltage_current # Default fallback
             else:
                 print(f"Warning: No action defined for startup interrupt button {pressed_pin}")
                 next_action = display_voltage_current # Default fallback
             startup_interrupted = True
             break
         elif pressed_pin is not None:
             print(f"Warning: Unhandled startup interrupt result: {pressed_pin}")

         if startup_interrupted: break
         # End of loop for one media item

    # If sequence finished without interruption, default to voltage display
    if not startup_interrupted and next_action != "QUIT":
        print("Startup sequence finished. Defaulting to sensor display.")
        next_action = display_voltage_current

    print("End of startup sequence function.")


# --- Main Loop ---
running = True
next_action = None
last_press_times = {pin: 0 for pin in BUTTON_PINS}

try:
    # Initial Modbus connection attempt (non-blocking)
    check_modbus_connection()

    # Run Startup Sequence - this sets the initial `next_action`
    run_startup_sequence()

    while running:
        loop_start_time = time.monotonic()

        # --- Execute Pending Action ---
        current_action = next_action
        next_action = None # Clear pending action before execution

        action_result = None
        if current_action == "QUIT":
            running = False
        elif callable(current_action):
            print(f"Executing action: {current_action.__name__}")
            action_result = current_action() # Execute the function (e.g., display_voltage_current or display_media)
        # --- Action Execution Complete ---


        # --- Handle Action Result ---
        # This logic decides the *next* state based on how the action ended
        if action_result == "QUIT":
            print("Action resulted in QUIT signal.")
            running = False
        elif action_result in BUTTON_PINS:
            # The action (e.g., sensor display) was interrupted by a button.
            # Queue the corresponding action for the *next* loop iteration.
            pin = action_result
            print(f"Action returned button {pin}. Queuing next action.")
            if pin == BUTTON_VOLTAGE_DISPLAY:
                next_action = display_voltage_current
            elif pin in BUTTON_MEDIA_MAP:
                media_index = BUTTON_MEDIA_MAP[pin]
                if 0 <= media_index < len(media_files):
                     media_path = os.path.join(MEDIA_FOLDER, media_files[media_index])
                     # Use default argument in lambda to capture the current value of media_path
                     next_action = lambda p=media_path: display_media(p)
                else:
                    print(f"Warning: Media index {media_index} out of range for result button {pin}. Defaulting.")
                    next_action = display_voltage_current # Fallback
            else:
                 print(f"Warning: No action mapped for result button {pin}. Defaulting.")
                 next_action = display_voltage_current # Fallback
        elif action_result is not None:
             print(f"Warning: Action returned unexpected value: {action_result}. Defaulting.")
             next_action = display_voltage_current # Default state if something unexpected happened


        # --- Check for Events and Button Presses (only if no action is pending) ---
        if next_action is None and running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                    print("Main loop: Quit event detected.")
                    running = False
                    break # Exit event loop

            if not running: break # Exit main loop

            # Check buttons
            now = time.monotonic()
            for pin in BUTTON_PINS:
                if GPIO.input(pin) == GPIO.HIGH:
                    if (now - last_press_times[pin]) > DEBOUNCE_TIME:
                        print(f"Main loop: Button {pin} pressed.")
                        last_press_times[pin] = now

                        # Set the action for the next loop iteration
                        if pin == BUTTON_VOLTAGE_DISPLAY:
                            next_action = display_voltage_current
                        elif pin in BUTTON_MEDIA_MAP:
                            media_index = BUTTON_MEDIA_MAP[pin]
                            if 0 <= media_index < len(media_files):
                                media_path = os.path.join(MEDIA_FOLDER, media_files[media_index])
                                next_action = lambda p=media_path: display_media(p) # Capture path
                            else:
                                print(f"Warning: Media index {media_index} out of range for button {pin}.")
                                next_action = display_voltage_current # Fallback
                        else:
                             print(f"Warning: No action defined for button {pin}")
                             # Maybe default to sensor screen if an unassigned button is hit?
                             # next_action = display_voltage_current
                        break # Handle only one button press per cycle

        # --- End Event/Button Check ---

        # Main loop wait to prevent high CPU usage when idle
        if running:
             elapsed_ms = (time.monotonic() - loop_start_time) * 1000
             wait_ms = max(1, MAIN_LOOP_WAIT_MS - int(elapsed_ms))
             pygame.time.wait(wait_ms)

    # --- End Main Loop ---

except KeyboardInterrupt:
    print("\nStopping application via KeyboardInterrupt...")
    running = False

except Exception as e:
    print("\n--- An unexpected error occurred ---")
    print(f"Error: {e}")
    traceback.print_exc()
    print("------------------------------------")
    running = False

finally:
    # --- Cleanup ---
    print("\nPerforming cleanup...")
    if client and client.is_socket_open():
        print("Closing Modbus client connection...")
        client.close()
    print("Cleaning up GPIO...")
    GPIO.cleanup()
    print("Quitting Pygame...")
    pygame.quit()
    print("Application exited.")
    sys.exit()
import machine
import rp2
import sys
import utime
from machine import Pin
from dht import DHT11

# --- 1. PIO Programma kameras datu uztveršanai ---
@rp2.asm_pio(set_init=rp2.PIO.IN_LOW, out_shiftdir=rp2.PIO.SHIFT_RIGHT, autopush=True, push_thresh=8)
def ov7670_capture():
    wait(0, gpio, 13) # Gaidām VSYNC Low
    wait(1, gpio, 13) # Gaidām VSYNC High (Kadra sākums)
    
    label("line_start")
    wait(1, gpio, 12) # Gaidām HREF High (Rindas sākums)
    
    label("pixel_wait")
    wait(1, gpio, 11) # Gaidām PCLK High
    in_(pins, 8)      # Nolasa 8 bitus no GP0-GP7
    wait(0, gpio, 11) # Gaidām PCLK Low
    
    jmp(pin, "pixel_wait") # Ja HREF ir High, turpinām pikseļus
    jmp(pin, "line_start") # Ja rinda beigusies, gaidām nākamo

# --- 2. Aparatūras konfigurācija ---

# Kamera XCLK (24MHz uz GP10)
xclk = machine.PWM(machine.Pin(10))
xclk.freq(24000000)
xclk.duty_u16(32768)

# I2C kameras konfigurācijai
i2c = machine.I2C(0, scl=machine.Pin(5), sda=machine.Pin(4), freq=100000)
CAM_ADDR = 0x21

# Sensori
dht_sensor = DHT11(Pin(27, Pin.IN, Pin.PULL_UP))
sound_pin = Pin(26, Pin.IN, Pin.PULL_UP)

def write_reg(reg, val):
    i2c.writeto_mem(CAM_ADDR, reg, bytes([val]))

def init_cam():
    write_reg(0x12, 0x80) # Reset
    utime.sleep_ms(100)
    write_reg(0x12, 0x00) # YUV režīms
    write_reg(0x11, 0x01) # Prescaler
    print("Kamera inicializēta.")

# PIO State Machine iestatīšana
sm = rp2.StateMachine(0, ov7670_capture, freq=125_000_000, in_base=machine.Pin(0), jmp_pin=machine.Pin(12))

# --- 3. Galvenā loģika ---
WIDTH, HEIGHT = 160, 120
buffer = bytearray(WIDTH * HEIGHT)
sound_trigger_count = 0  # Skaitītājs skaņas reizēm

init_cam()
print("Sistēma gatava. Monitorējam sensorus...")

while True:
    try:
        # 1. DHT11 mērījumi
        dht_sensor.measure()
        temp = dht_sensor.temperature()
        humi = dht_sensor.humidity()
        
        # 2. Skaņas mērījums (analizējam 500ms logā)
        current_sound_hits = 0
        for _ in range(1000):
            if sound_pin.value() == 1:
                current_sound_hits += 1
            utime.sleep_ms(1)
        
        print(f"T: {temp}C, H: {humi}%, Sound: {current_sound_hits}")

       # 3. Pārbauda skaņas "3 reizes" nosacījumu
        if current_sound_hits > 400: # Slieksnis, ko uzskatām par "troksni"
            sound_trigger_count += 1
        else:
            sound_trigger_count = 0 # Ja kluss, nometam skaitītāju (var pielāgot pēc vajadzības)

        # 4. Galvenais nosacījums bildes uzņemšanai
        if temp > 40 or humi > 80 or sound_trigger_count >= 3:
            print("KONSTATĒTS PAAUGSTINĀTS TROKSINS! Uzņemam attēlu...")\
            
            sm.active(1)
            sm.get(buffer)
            sm.active(0)
            
            # Nosūta datus uz PC
            sys.stdout.write("START")
            sys.stdout.buffer.write(buffer)
            
            sound_trigger_count = 0 # Atiestata pēc bildes uzņemšanas
            utime.sleep_ms(2000)    # Pauze, lai izvairītos no dubultām bildēm
            
    except Exception as e:
        print("Kļūda sensoru nolasīšanā:", e)
    
    utime.sleep_ms(500)



import time
import spidev
from pmw3901 import PMW3901

# 1. Ruční nastavení SPI sběrnice
spi = spidev.SpiDev()
spi.open(0, 0)  # Port 0, Device 0 (CE0)
spi.max_speed_hz = 400000  # Snížení na 400 kHz pro stabilitu
spi.mode = 0b11            # PMW3901 obvykle vyžaduje SPI Mode 3

print(f"SPI rychlost nastavena na: {spi.max_speed_hz} Hz")

try:
    # 2. Inicializace senzoru
    # Zkusíme mu vnutit parametry, které už známe z help()
    sensor = PMW3901(spi_port=0, spi_cs=0)
    
    # Pokud ani toto nepomůže, zkusíme najít, kde se v tom objektu schovává SPI
    # Vypíšeme si dostupné atributy pro debug, kdyby to spadlo
    # print(dir(sensor)) 

    print("Test zahájen. Hýbej senzorem...")
    tx, ty = 0, 0
    
    while True:
        try:
            dx, dy = sensor.get_motion()
            if dx != 0 or dy != 0:
                tx += dx
                ty += dy
                print(f"Rel: x {dx:4d} y {dy:4d} | Abs: x {tx:6d} y {ty:6d}")
        except RuntimeError:
            # RuntimeError často značí, že SPI nestíhá nebo je zahlcené
            pass
        
        time.sleep(0.01)

except KeyboardInterrupt:
    print("\nTest ukončen.")
finally:
    spi.close()

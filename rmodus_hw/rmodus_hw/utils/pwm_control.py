from gpiozero import PWMOutputDevice
from gpiozero.exc import GPIOPinInUse

class PWMControl:
    def __init__(self, pin, frequency=1000):
        try:
            self.motor = PWMOutputDevice(pin, frequency=frequency)
        except GPIOPinInUse:
            print(f"Pin {pin} uz se pouziva. Ukoncuji stare instance...")
            raise 

    def set_speed(self, speed):
        self.motor.value = max(0.0, min(1.0, speed))

    def stop(self):
        self.motor.close()

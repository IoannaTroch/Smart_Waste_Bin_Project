from gpiozero import DigitalInputDevice

class PirSampler:
    def __init__(self, pin: int):
        # Store the pin number for reference
        self.pin = pin
        
        # Initialize the hardware pin as a digital input
        self.dev = DigitalInputDevice(pin)

    def read(self) -> bool:
        """
        Reads the current state of the sensor.
        Returns:
            True if the signal is HIGH (motion detected)
            False if the signal is LOW (no motion)
        """
        return bool(self.dev.value)
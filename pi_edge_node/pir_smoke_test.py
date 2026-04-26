import time
import argparse
import sys
from gpiozero import DigitalInputDevice

def main():
    # Set up command line arguments
    p = argparse.ArgumentParser(description="PIR Hardware Smoke Test")
    p.add_argument("--pin", type=int, required=True, help="GPIO pin number (e.g., 18)")
    args = p.parse_args()

    print(f"--- Starting Hardware Smoke Test on Pin {args.pin} ---")
    
    try:
        # We use DigitalInputDevice directly to test the pure electrical connection
        sensor = DigitalInputDevice(args.pin)
        
        print("Waiting 2 seconds for the PIR sensor lens to warm up...")
        time.sleep(2) 
        
        print("Ready! Wave your hand in front of the sensor. (Press Ctrl+C to exit)\n")

        previous_state = None

        # Infinite loop to constantly check the wire's voltage
        while True:
            # Read the raw electrical state (True = High Voltage, False = Low Voltage)
            current_state = bool(sensor.value)
            
            # Only print when the state actually changes, so we don't flood the terminal
            if current_state != previous_state:
                if current_state:
                    print(f"[{time.strftime('%H:%M:%S')}] Motion!)")
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] No Motion!")
                
                previous_state = current_state
                
            time.sleep(0.05)
            
    except KeyboardInterrupt:
        print("\nSmoke test stopped by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\nHardware Error: {e}")
        print("Check your 5V, GND, and Data wires!")
        sys.exit(1)

if __name__ == "__main__":
    main()

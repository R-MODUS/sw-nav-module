import serial
import struct
import time

class UART:
    def __init__(self, port='/dev/serial0'):
        self.ser = serial.Serial(
            port=port,
            baudrate=115200,
            timeout=0.1
        )
        self.i = 0

    def send_packet(self, data, header=0xAA, index=False, log=False):
        lenght = len(data) + 2
        if index:
            lenght += 1
            data = [self.i] + data
            self.i += 1
            if self.i >= 255: self.i = 0

        checksum = sum(data) % 256
        char = f'{lenght}B'
        packet = struct.pack(char, header, *data, checksum)
        self.ser.write(packet)

        if log:
            self._print_packet(packet, pretext='Send')

    def read_packet(self, len_data, header=0xAA, log=False):
        while self.ser.any():
            byte = self.ser.read(1)
            if byte and byte[0] == header:
                frame = self.ser.read(len_data+1)
                if not frame or len(frame) != len_data+1:
                    return None
                
                data = frame[:-1]
                received_checksum = frame[-1]
                calculated_checksum = sum(data) % 256

                if received_checksum != calculated_checksum:
                    continue

                if log:
                    packet = bytes([header]) + frame
                    self._print_packet(packet, pretext='Received')  

                return data
        return None

    @staticmethod
    def _print_packet(packet, pretext=''):
        print('\n{pretext} (HEX): ', ' '.join(f'{b:02X}' for b in packet))
        print('{pretext} (DEC): ', list(packet))


if __name__ == "__main__":
    uart = UART(port='/dev/ttyUSB0')
    while True:
        uart.send_packet([255,255,255,255,0,0,1,1], index=False, log=True)
        time.sleep(0.1)

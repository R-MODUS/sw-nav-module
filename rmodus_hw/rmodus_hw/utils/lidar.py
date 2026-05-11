import serial
import time


class Lidar:
    def __init__(self, port='/dev/serial0'):
        self.ser = serial.Serial(
            port=port,
            baudrate=115200,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            timeout=0.01
        )

    def read_packet(self, timeout_sec=5.0):
        packet = ""
        started = False
        deadline = time.monotonic() + timeout_sec
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f'LiDAR: za {timeout_sec}s nepřišel platný paket (port, baud 115200, napájení, motor?)'
                )
            byte = self.ser.read(1)
            if not byte:
                continue
            enc = f"{byte.hex()}:"
            if enc == "fa:" and not started:
                packet = "fa:"
                started = True
            elif started:
                packet += enc
            if packet.count(":") >= 22:
                return packet

    @staticmethod
    def decode_packet(packet_hex):
        b = [int(x, 16) for x in packet_hex.strip().split(":") if x]
        if len(b) < 22:
            raise ValueError("Chybný paket: méně než 22 bajtů")
        if b[0] != 0xFA:
            raise ValueError("Neplatný start paketu")
        
        idx = b[1] - 0xA0
        speed_raw = b[2] | (b[3] << 8)
        speed_rpm = speed_raw / 64.0
        
        points = []
        for i in range(4):
            base = 4 + i * 4
            dist = ((b[base+1] & 0x1F) << 8) | b[base]
            invalid = bool(b[base+1] & 0x80)
            strength = b[base+2] | (b[base+3] << 8)
            angle = idx * 4 + i
            #print(angle, dist, invalid, strength, speed_rpm)
            points.append({
                "angle": angle,
                "distance": dist if not invalid else -1,
                "invalid": invalid,
                "strength": strength,
                "rpm": speed_rpm
            })
        return points, speed_rpm

    def get_scan(self, startZero=False, max_seconds=30.0):
        t_start = time.time()
        deadline = t_start + max_seconds

        ranges = [float('inf')] * 360
        intensities = [0] * 360
        rpm = 0.0
        i = 0
        foundStart = False if startZero else True

        while True:
            remain = deadline - time.time()
            if remain <= 0:
                raise TimeoutError(
                    'LiDAR: nestihl poskládat 360° scan v limitu '
                    f'({max_seconds}s). Zkus startZero=False nebo HW.'
                )
            packet = self.read_packet(timeout_sec=min(5.0, remain))
            points, rpm = self.decode_packet(packet)

            if startZero and not foundStart and any(p['angle'] == 0 for p in points):
                foundStart = True

            if foundStart:
                for p in points:
                    angle = p['angle']
                    if not p['invalid']:
                        ranges[angle] = p['distance'] / 1000.0  # mm -> m
                        intensities[angle] = float(p['strength'])
                    else:
                        ranges[angle] = -1.0
                        intensities[angle] = -1.0
                i += 1
                if i >= 360 // 4:  # nasbírat 360 úhlů (4 úhly na paket)
                    break

        scan_time = time.time() - t_start
        return ranges, intensities, rpm, scan_time


if __name__ == '__main__':
    lidar = Lidar(port='/dev/ttyUSB0')

    while True:
        
        ranges, intensities, rpm, scan_time = lidar.get_scan(startZero=True)

        print('-------------------------------------------')
        print(f"Scan time: {scan_time:.3f} s")
        print(f"RPM: {rpm:.2f}")
        print(f"Frequency: {1/scan_time:.2f} Hz")
        print(len(ranges), f"Ranges (m): {ranges[:10]} ...")
        print(f"Intensities: {intensities[:10]} ...")

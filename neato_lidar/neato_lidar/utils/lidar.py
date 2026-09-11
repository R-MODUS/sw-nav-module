import serial
import time


class Lidar:
    """Neato XV-series LDS serial protocol (115200 baud, FA packets)."""

    def __init__(self, port="/dev/ttyUSB0"):
        self.ser = serial.Serial(
            port=port,
            baudrate=115200,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            timeout=0.01,
        )

    def read_packet(self, timeout_sec=5.0):
        packet = ""
        started = False
        deadline = time.monotonic() + timeout_sec
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"Neato LiDAR: no valid packet in {timeout_sec}s "
                    "(check port, baud 115200, power, motor)"
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
            raise ValueError("Invalid packet: fewer than 22 bytes")
        if b[0] != 0xFA:
            raise ValueError("Invalid packet start")

        idx = b[1] - 0xA0
        speed_raw = b[2] | (b[3] << 8)
        speed_rpm = speed_raw / 64.0

        points = []
        for i in range(4):
            base = 4 + i * 4
            dist = ((b[base + 1] & 0x1F) << 8) | b[base]
            invalid = bool(b[base + 1] & 0x80)
            strength = b[base + 2] | (b[base + 3] << 8)
            angle = idx * 4 + i
            points.append(
                {
                    "angle": angle,
                    "distance": dist if not invalid else -1,
                    "invalid": invalid,
                    "strength": strength,
                    "rpm": speed_rpm,
                }
            )
        return points, speed_rpm

    def get_scan(self, startZero=False, max_seconds=30.0):
        t_start = time.time()
        deadline = t_start + max_seconds

        ranges = [float("inf")] * 360
        intensities = [0] * 360
        rpm = 0.0
        i = 0
        foundStart = False if startZero else True

        while True:
            remain = deadline - time.time()
            if remain <= 0:
                raise TimeoutError(
                    f"Neato LiDAR: failed to assemble 360 deg scan in {max_seconds}s"
                )
            packet = self.read_packet(timeout_sec=min(5.0, remain))
            points, rpm = self.decode_packet(packet)

            if startZero and not foundStart and any(p["angle"] == 0 for p in points):
                foundStart = True

            if foundStart:
                for p in points:
                    angle = p["angle"]
                    if not p["invalid"]:
                        ranges[angle] = p["distance"] / 1000.0  # mm -> m
                        intensities[angle] = float(p["strength"])
                    else:
                        ranges[angle] = -1.0
                        intensities[angle] = -1.0
                i += 1
                if i >= 360 // 4:
                    break

        scan_time = time.time() - t_start
        return ranges, intensities, rpm, scan_time

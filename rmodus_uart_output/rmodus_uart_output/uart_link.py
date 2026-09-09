"""Minimal UART framing for Twist payloads (3× float32 LE + checksum)."""

from __future__ import annotations

import struct

import serial


class UartLink:
    def __init__(self, port: str, baudrate: int = 115200, header: int = 0xAA):
        self.header = header
        self.ser = serial.Serial(port=port, baudrate=baudrate, timeout=0.1)

    def send_twist(self, linear_x: float, linear_y: float, angular_z: float) -> None:
        payload = struct.pack("<fff", float(linear_x), float(linear_y), float(angular_z))
        checksum = sum(payload) % 256
        self.ser.write(bytes([self.header]) + payload + bytes([checksum]))

    def close(self) -> None:
        if self.ser and self.ser.is_open:
            self.ser.close()

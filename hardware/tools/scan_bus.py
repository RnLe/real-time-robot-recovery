"""Read-only scan of a Feetech servo bus. Writes nothing to EEPROM.

Usage:
    uv run --frozen --extra hardware python hardware/tools/scan_bus.py <PORT>

Probes every supported baud rate and lists the motor IDs that respond. A healthy
assembled SO-101 arm reports ids [1..6] at 1000000 baud, all model 777.
"""
import sys

from lerobot.motors.feetech import FeetechMotorsBus

port = sys.argv[1]
print(f"Scanning {port} across all baud rates (read-only)...\n")
found = FeetechMotorsBus.scan_port(port)
if not found:
    print("No motors responded on any baud rate.")
    sys.exit(1)
for baudrate, ids in sorted(found.items()):
    print(f"  baud {baudrate}: motor id(s) {sorted(ids)}")

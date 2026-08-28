"""Read-only status of an assembled SO-101 bus. Writes nothing."""
import sys

from lerobot.motors import Motor, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus

JOINTS = {"shoulder_pan":1,"shoulder_lift":2,"elbow_flex":3,
          "wrist_flex":4,"wrist_roll":5,"gripper":6}
port = sys.argv[1]
motors = {n: Motor(i, "sts3215", MotorNormMode.DEGREES) for n, i in JOINTS.items()}
bus = FeetechMotorsBus(port=port, motors=motors)
bus.connect(handshake=True)
print("handshake OK: all 6 motors present, firmware consistent\n")

pos = bus.sync_read("Present_Position", normalize=False)
torque = bus.sync_read("Torque_Enable", normalize=False)
volt = bus.sync_read("Present_Voltage", normalize=False)
temp = bus.sync_read("Present_Temperature", normalize=False)

print(f"{'joint':<15}{'id':>3}{'raw':>7}{'deg':>8}{'torque':>8}{'volt':>7}{'temp':>6}")
for n, i in JOINTS.items():
    print(f"{n:<15}{i:>3}{pos[n]:>7}{pos[n]*360/4096:>8.1f}"
          f"{'ON' if torque[n] else 'off':>8}{volt[n]/10:>6.1f}V{temp[n]:>5}C")

if any(torque.values()):
    print("\nWARNING: torque is ON. Do not force those joints by hand.")
else:
    print("\nAll torque disabled - free to move by hand.")
bus.disconnect()

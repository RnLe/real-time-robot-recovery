"""Read torque/gain registers from a bus. Read-only."""
import sys

from lerobot.motors import Motor, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus

J = {"shoulder_pan":1,"shoulder_lift":2,"elbow_flex":3,"wrist_flex":4,"wrist_roll":5,"gripper":6}
FIELDS = ["Max_Torque_Limit","Torque_Limit","P_Coefficient","I_Coefficient","D_Coefficient",
          "Protection_Current","Overload_Torque","Protective_Torque","Protection_Time",
          "Over_Current_Protection_Time","Unloading_Condition","Maximum_Velocity_Limit",
          "Present_Load","Present_Current","Torque_Enable"]
bus = FeetechMotorsBus(port=sys.argv[1],
                       motors={n: Motor(i,"sts3215",MotorNormMode.DEGREES) for n,i in J.items()})
bus.connect(handshake=True)
vals = {f: bus.sync_read(f, normalize=False) for f in FIELDS}
w = max(len(f) for f in FIELDS) + 1
print(f"{'register':<{w}}" + "".join(f"{n[:11]:>12}" for n in J))
for f in FIELDS:
    print(f"{f:<{w}}" + "".join(f"{vals[f][n]:>12}" for n in J))
bus.disconnect()

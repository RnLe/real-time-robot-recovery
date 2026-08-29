#!/usr/bin/env bash
# Fetch the SO-101 URDF and STL meshes used by the 3D visualization tools.
#
# The meshes are ~15 MB and are not kept in version control. Run this once per
# machine; hardware/tools/so101/ is gitignored.
#
#   bash hardware/tools/fetch_so101_meshes.sh
set -euo pipefail

RAW="https://raw.githubusercontent.com/TheRobotStudio/SO-ARM100/main/Simulation/SO101"
DEST="$(dirname "$0")/so101"
MESHES=(
  base_motor_holder_so101_v1 base_so101_v2 motor_holder_so101_base_v1
  motor_holder_so101_wrist_v1 moving_jaw_so101_v1 rotation_pitch_so101_v1
  sts3215_03a_no_horn_v1 sts3215_03a_v1 under_arm_so101_v1 upper_arm_so101_v1
  waveshare_mounting_plate_so101_v2 wrist_roll_follower_so101_v1
  wrist_roll_pitch_so101_v2
)

mkdir -p "$DEST/assets"
echo "Fetching URDF..."
curl -fsSL --retry 3 "$RAW/so101_new_calib.urdf" -o "$DEST/so101.urdf"
for m in "${MESHES[@]}"; do
  echo "  $m.stl"
  curl -fsSL --retry 3 "$RAW/assets/$m.stl" -o "$DEST/assets/$m.stl"
done
echo "Done: $DEST/so101.urdf plus $(ls "$DEST/assets" | wc -l) meshes"

# GR00T / Unitree G1 Output

Common Behavior Data retargeted onto a **Unitree G1** -- the embodiment NVIDIA
GR00T drives -- as a joint-space trajectory, a USD stage and a GR00T-LeRobot
dataset.

- `g1_robot.usda` ......... the robot: one Xform per G1 link, at the URDF's own origins
- `scene.usda` ............ the set: floor, backdrop, chair, table, lights, film camera
- `motion.usda` ........... **open this one.** Sublayers the two above and adds
  nothing but time samples
- `motion.npz` ............ joint angles, root pose and link frames as arrays
- `g1_joint_trajectory.csv` the 43 joint angles per frame, in the GR00T order
- `groot_lerobot/` ........ a GR00T-LeRobot v2.1 dataset (the Isaac Lab Arena G1 modality)
- `adapter_report.json` ... retarget residuals, joints on their limits, and what
  could not be represented
- `groot_g1_simulation.mp4` rendered video (same trajectory as the stage)

## Open it

```bash
./isaac-sim.sh --/app/file/openPath=<abs path>/motion.usda
usdview motion.usda           # nothing in the stage is Isaac-specific
```

## The 43 numbers

`observation.state` and `action` are the Unitree G1's 43 joints in the order
the Isaac Lab Arena G1 embodiment uses -- left leg (6), right leg (6), waist
(3), left arm (7), left Dex3 hand (7), right arm (7), right Dex3 hand (7).
`meta/modality.json` carries that slicing, so a GR00T loader configured for the
Arena G1 embodiment reads this dataset without changes.

`action[t]` is `state[t+1]`, with the last frame repeated: this is a kinematic
replay, so the commanded next pose *is* the next pose. No policy produced these
numbers and none is implied.

## Mode: retarget, not replay

The other CBD adapters measure the subject and animate a figure with the
subject's proportions. This one cannot: a G1 has fixed link lengths and hard
joint limits, so the human motion is solved into the robot's joint space by
matching **segment directions** -- where the upper arm, forearm, hand, thigh,
shank and foot point, in the frame of the joint that carries each -- under the
URDF's limits. What is left over is in `adapter_report.json`, in degrees, per
segment. Nothing is scaled to hide it.

The set is scaled instead. The one number in `adapter_report.json` under
`scale` is the ratio between the robot's own seated pelvis height and the
subject's; the floor, chair, table and camera are scaled by it and the robot
keeps its factory dimensions.

## Coordinate frames

| | Frame |
|---|---|
| Canonical CBD | Y-up, right-handed, subject faces +Z |
| Unitree G1 / URDF | Z-up, X forward, Y left, origin at the pelvis |
| This stage | Z-up, metres, robot faces -Y, camera on the -Y side |

Canonical to G1 is the cyclic relabelling `(x, y, z) -> (z, x, y)`, a proper
rotation. G1 to stage is a single -90 deg yaw, carried by the `/World/G1` root
Xform, so every link below it is in the robot's own frame and matches the URDF.

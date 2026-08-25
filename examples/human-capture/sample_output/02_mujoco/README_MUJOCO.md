# MuJoCo Output

Model and motion are separated (Section 22):

- `humanoid.xml` ... body / joint definition (MJCF)
- `motion.npz` .... qpos trajectory derived from Common Behavior Data
- `object_trajectory.csv` ... object proxy positions with `position_source`
- `replay_mujoco.py` ... viewer playback (kinematic replay, mj_forward only)
- `mujoco_simulation.mp4` ... rendered video (same trajectory as the viewer)

## Local playback (Windows)

```
pip install mujoco
py -m mujoco.viewer --mjcf="humanoid.xml"   # model only
py replay_mujoco.py                          # model + motion
```

Mode: Kinematic Replay (`data.qpos[:] = recorded_qpos[frame]` + `mj_forward`).
Physically correct contact/forces are out of scope for Demo 2.0.

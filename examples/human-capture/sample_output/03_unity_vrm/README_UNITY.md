# Unity / VRM Output

Avatar model and motion are separated (Section 26):

- `avatar.vrm` ..... place a VRM 1.0 avatar here
  (e.g. VRM Consortium sample `Seed-san.vrm`)
- `motion.vrma` .... VRM Animation exported from Common Behavior Data
- `unity_vrm_animation.mp4` ... capture this locally in Unity

## Recommended: UniVRM SimpleVrma sample (no coding required)

1. Create a Unity project (2022.3 LTS or Unity 6, 3D template)
2. From https://github.com/vrm-c/UniVRM/releases download BOTH
   `UniVRM-0.1xx.x_xxxx.unitypackage` and
   `VRM_Samples-0.1xx.x_xxxx.unitypackage`, then import both via
   `Assets > Import Package > Custom Package...`
3. Open the scene `Assets/VRM10_Samples/SimpleVrma/SimpleVrma` and press Play
4. Use the on-screen UI to open `avatar.vrm` and `motion.vrma`
5. Turn OFF the `BoxMan` checkbox to hide the white skeleton preview
   (if BoxMan moves but the avatar does not, the issue is on the avatar
   side; if neither moves, the issue is on the vrma side)
6. Record the Game view with Unity Recorder
   (`Window > Package Manager` -> install Recorder ->
   `Window > General > Recorder` -> Movie / H.264 MP4)

Recording fps does NOT need to match the analysis fps - the comparison
cell aligns videos by timestamp. Just cover the full `duration_sec`
listed in `04_behavior_dataset/manifest.json`.

Unity performs no MediaPipe inference, motion smoothing, joint
calculation, or dataset generation - Load VRM, Load VRMA, Play only.

## Optional: replay the object trajectory (Level 1, kinematic)

The object trajectory is part of the Common Behavior Data, so it can be
replayed in Unity just like the human motion:

1. Copy `object_trajectory_unity.json` and `ObjectTrajectoryPlayer.cs`
   into the Unity project's `Assets/` folder
2. In the SimpleVrma scene (NOT in play mode), create an empty GameObject
   and add the `ObjectTrajectoryPlayer` component
3. Assign `object_trajectory_unity.json` to the `trajectoryJson` field
4. Press Play; a primitive matching the object class appears and follows
   the recorded trajectory. Press **Space** to restart the object motion
   at the moment the avatar's motion loops back to the start
5. If left/right looks mirrored against the avatar, turn OFF `mirrorX`

Position depth is monocular-estimated (see `source` per frame); rotation
and physical contact are out of scope for this level.

After capturing, rename the recording to `unity_vrm_animation.mp4`,
copy it back into this folder, and re-run the comparison cell to build
the three-screen video.

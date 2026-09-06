#!/usr/bin/env python3
"""Bake the physics result into a stage anyone can open.

The physics pass decides the trajectory; this writes it down. Every link of the
referenced G1 asset gets time-sampled `xformOp:translate` and `xformOp:orient`,
so the finished stage plays back with no simulator, no articulation and no
contact -- `usdview motion.usda` works, and so does the renderer this adapter
already had, unchanged.

**The angles baked here are `q_actual`, not `q_target`** -- what the robot did,
not what it was asked to do. That is the point of running physics at all: v1
shipped a kinematic replay and said so ("nothing here is a dynamically feasible
G1 trajectory"), and a dataset that was never checked against contact is worth
less than one that was. The difference between the two is in
`settle_final.json` under `physics.tracking_*`, so nothing is hidden by the
choice.

Baking is possible at all because the asset keeps its 53 links as flat children
of one root, each with its own transform, rather than nesting them -- so a link
pose is a value to write, not a chain to rebuild.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from pxr import Usd, UsdGeom, Gf, Sdf

import invariants as I

LINK_SUFFIX = "_link"


def _quat(R):
    """Rotation matrix -> Gf.Quatd (w, (x, y, z))."""
    t = R[0, 0] + R[1, 1] + R[2, 2]
    if t > 0:
        s = np.sqrt(t + 1.0) * 2
        w, x, y, z = 0.25 * s, (R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        w, x, y, z = (R[2, 1] - R[1, 2]) / s, 0.25 * s, (R[0, 1] + R[1, 0]) / s, (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        w, x, y, z = (R[0, 2] - R[2, 0]) / s, (R[0, 1] + R[1, 0]) / s, 0.25 * s, (R[1, 2] + R[2, 1]) / s
    else:
        s = np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        w, x, y, z = (R[1, 0] - R[0, 1]) / s, (R[0, 2] + R[2, 0]) / s, (R[1, 2] + R[2, 1]) / s, 0.25 * s
    return Gf.Quatd(float(w), Gf.Vec3d(float(x), float(y), float(z)))


def _look_at(eye, target, up=(0.0, 0.0, 1.0)):
    """USD cameras look down -Z with +Y up."""
    eye, target, up = (np.asarray(v, float) for v in (eye, target, up))
    fwd = target - eye
    fwd /= np.linalg.norm(fwd)
    z = -fwd
    x = np.cross(up, z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    return _quat(np.column_stack([x, y, z]))


def _set_op(prim, name, value, time=None):
    xf = UsdGeom.Xformable(prim)
    for op in xf.GetOrderedXformOps():
        if op.GetOpName() == name:
            op.Set(value, time) if time is not None else op.Set(value)
            return True
    return False


def bake(stage_path: Path, out_path: Path, q, joint_names, root_pos, fps,
         camera=True, ego=True, ego_width=640, ego_height=480):
    """Write time samples for every link, from the joint trajectory."""
    stage = Usd.Stage.Open(str(stage_path))
    n = len(q)
    stage.SetTimeCodesPerSecond(fps)
    stage.SetStartTimeCode(0)
    stage.SetEndTimeCode(n - 1)
    # /World/G1 already carries the root pose -- its children are expressed in
    # its frame, so adding root_pos to the baked link transforms applies it
    # twice. The first render put the robot at z 1.19 instead of 0.59 and it
    # read as floating a metre above its own seat, which is what a doubled root
    # looks like when every other number is right.
    root = np.zeros(3)

    g1 = stage.GetPrimAtPath("/World/G1")
    links = [c for c in g1.GetChildren() if c.GetName().endswith(LINK_SUFFIX)
             or c.GetName() == "pelvis"]
    written = 0
    for t in range(n):
        P, R = I.forward_kinematics(q[t], joint_names, with_rot=True)
        tc = Usd.TimeCode(t)
        for link in links:
            name = link.GetName()
            if name not in P:
                continue
            _set_op(link, "xformOp:translate",
                    Gf.Vec3d(*(root + P[name])), tc)
            _set_op(link, "xformOp:orient", _quat(R[name]), tc)
            written += 1

    if camera:
        P0 = I.forward_kinematics(q[0], joint_names)
        offset = np.asarray(root_pos, float)     # world, for the camera only
        head = offset + P0["torso_link"]
        knee = offset + P0["left_knee_link"]
        # frame the whole seated figure, from a three-quarter view low enough
        # that the floor is in shot -- without it there is no scale reference
        # and a correct pose still reads as floating
        centre = np.array([float((head[0] + knee[0]) / 2.0), 0.0,
                           float(head[2] * 0.62)])
        target = Gf.Vec3d(*centre)
        # near the seated figure's own eye level: from above, a correct pose
        # still reads as hovering because the floor foreshortens away
        eye = np.array([2.20, -1.85, float(head[2]) * 0.80])
        cam = UsdGeom.Camera.Define(stage, "/World/Camera")
        cam.CreateFocalLengthAttr(32.0)
        cam.CreateClippingRangeAttr(Gf.Vec2f(0.05, 100.0))
        xf = UsdGeom.Xformable(cam)
        xf.AddTranslateOp().Set(Gf.Vec3d(*eye))
        xf.AddOrientOp().Set(Gf.Quatf(_look_at(eye, np.array(target))))
        key = UsdGeom.Xform.Define(stage, "/World/KeyLight")
        UsdGeom.Xformable(key).AddTranslateOp().Set(Gf.Vec3d(1.5, -1.5, 2.6))
        light = stage.DefinePrim("/World/KeyLight/Dome", "DomeLight")
        light.CreateAttribute("inputs:intensity", Sdf.ValueTypeNames.Float).Set(900.0)

    # The GR00T dataset's `observation.images.ego_view` is the robot's own head
    # camera, and v2's first pass left it as v1's -- rendered from the capsule
    # stand-in, of a scene with no table and no cup. It is the same camera v1
    # authored (`cbd_adapter_groot_g1.write_robot_usd`): parented to
    # `d435_link`, D435 field of view, looking down the sensor's +X.
    if ego:
        d435 = stage.GetPrimAtPath("/World/G1/d435_link")
        if d435 and d435.IsValid():
            cam = UsdGeom.Camera.Define(stage, "/World/G1/d435_link/ego_cam")
            R = np.array([[0.0, 0.0, -1.0], [-1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
            UsdGeom.Xformable(cam).AddOrientOp(
                UsdGeom.XformOp.PrecisionDouble).Set(_quat(R))
            aperture = 20.955
            cam.CreateFocalLengthAttr(
                float(aperture / (2 * np.tan(np.radians(69.4 / 2)))))
            cam.CreateHorizontalApertureAttr(float(aperture))
            cam.CreateVerticalApertureAttr(
                float(aperture * ego_height / ego_width))
            cam.CreateClippingRangeAttr(Gf.Vec2f(0.02, 100.0))

    stage.GetRootLayer().Export(str(out_path))
    return {"links_written": len(links), "samples": written, "frames": n,
            "fps": fps, "camera": bool(camera),
            "ego_camera": bool(ego and stage.GetPrimAtPath(
                "/World/G1/d435_link/ego_cam").IsValid()),
            "angles": "q_actual -- the physics result, not the retarget target"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", required=True, help="motion_v2.usda from robot_stage")
    ap.add_argument("--settle", required=True, help="settle_final.npz (q_actual)")
    ap.add_argument("--stage-report", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    z = np.load(a.settle)
    q = np.asarray(z["joint_angles_rad"], float)
    names = [str(s) for s in z["joint_names"]]
    fps = float(z["fps"][0]) if "fps" in z else 12.0
    rep = json.loads(Path(a.stage_report).read_text("utf-8"))
    root = rep["built"]["robot"]["root_pos"]
    info = bake(Path(a.stage), Path(a.out), q, names, root, fps)
    print(json.dumps(info, indent=1))
    print("baked:", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

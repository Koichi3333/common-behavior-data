#!/usr/bin/env python3
"""Author the v2 stage: the real G1, and a scene it can physically use.

v1 built the robot out of spheres, boxes and capsules at the URDF's link
origins -- a stand-in that answers "did the joint angles come out sane" and
nothing about how the result looks. The asset NVIDIA ships, and that IsaacLab
Arena drove in the demo this VM already ran, is a different object:

    g1_29dof_with_hand_rev_1_0.usd      38 MB
      87 Mesh prims                     real geometry and materials
      43 PhysicsRevoluteJoint           exactly the 43 DoF this adapter writes
      ArticulationRootAPI on /pelvis    drivable, and collidable
      Z-up, metersPerUnit 1.0           the convention this adapter already uses

The 43 joint names in that file and the 43 in `g1_kinematics.json` match
one-for-one, verified -- so `motion.npz` maps onto the articulation with no
remapping at all. That is the whole integration.

**The asset is referenced, never vendored.** It is NVIDIA's, this is a public
repository, and `--asset-root` takes either the public asset server or a local
mirror. Nothing here writes 38 MB into git.

The scene is deliberately thin: a floor and the support surfaces the clip's
invariants require, with collision and mass, at the one scene scale the
decisive invariant fixed. Free-standing props wait for the placement solver --
standing them at a guessed depth would be exactly the kind of fabrication the
provenance ledger exists to prevent, and the physics pass does not need them to
measure penetration against the floor, the seat and the robot's own body.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from pxr import Usd, UsdGeom, UsdPhysics, Gf, Sdf, UsdShade

PUBLIC_ASSET_ROOT = ("https://omniverse-content-production.s3-us-west-2."
                     "amazonaws.com/Assets/Isaac/6.0/Isaac")
G1_ASSET_REL = "Samples/Groot/Robots/g1_29dof_with_hand_rev_1_0.usd"
G1_DEFAULT_PRIM = "g1_29dof_with_hand_rev_1_0"


def resolve_asset(asset_root: str | None) -> str:
    root = (asset_root or PUBLIC_ASSET_ROOT).rstrip("/")
    return f"{root}/{G1_ASSET_REL}"


def _prop_asset(rel: str | None, asset_root: str | None) -> str | None:
    """A catalog asset path against the same root the robot came from."""
    if not rel:
        return None
    if "://" in rel:
        return rel
    return f"{(asset_root or PUBLIC_ASSET_ROOT).rstrip('/')}/{rel}"


def _new_stage(path: Path):
    """CreateNew refuses an existing file; rebuilding a stage is normal here."""
    path = Path(path)
    if path.exists():
        path.unlink()
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    return stage


def _set_translate(prim, vec):
    """Set the translation, reusing the op the referenced asset already has.

    The G1 asset arrives with xformOpOrder [translate, orient, scale] on its
    default prim, so adding another translate op is an error rather than an
    override. Reuse it; only author a new one when the prim is bare.
    """
    xf = UsdGeom.Xformable(prim)
    for op in xf.GetOrderedXformOps():
        if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
            op.Set(Gf.Vec3d(*vec))
            return op
    return xf.AddTranslateOp().Set(Gf.Vec3d(*vec))


def _material(stage, path, rgb, rough=0.6):
    mat = UsdShade.Material.Define(stage, path)
    sh = UsdShade.Shader.Define(stage, path + "/Shader")
    sh.CreateIdAttr("UsdPreviewSurface")
    sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*rgb))
    sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(rough)
    mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    return mat


def _box(stage, path, size, centre, material, dynamic=False, mass=None,
         yaw_deg=0.0, collision=True):
    x = UsdGeom.Cube.Define(stage, path)
    x.CreateSizeAttr(2.0)                       # unit cube, scaled below
    xf = UsdGeom.Xformable(x)
    xf.AddTranslateOp().Set(Gf.Vec3d(*centre))
    if yaw_deg:
        xf.AddRotateZOp(UsdGeom.XformOp.PrecisionDouble).Set(float(yaw_deg))
    xf.AddScaleOp().Set(Gf.Vec3f(size[0] / 2.0, size[1] / 2.0, size[2] / 2.0))
    UsdShade.MaterialBindingAPI(x.GetPrim()).Bind(material)
    if collision:
        UsdPhysics.CollisionAPI.Apply(x.GetPrim())
    if dynamic:
        UsdPhysics.RigidBodyAPI.Apply(x.GetPrim())
        if mass:
            UsdPhysics.MassAPI.Apply(x.GetPrim()).CreateMassAttr(float(mass))
    return x


def _support_surface(stage, root, place, material, solid=True):
    """A top on legs, not a plinth -- the mistake the seat cost four runs on.

    A support surface is drawn as a slab at the solved height with four legs
    inset under it. A solid block from the floor swallows whatever is in front
    of it, which for a seat was the shins and for a table would be the feet.
    """
    cx, cy = place["centre_xy_m"]
    top = float(place["top_z_m"])
    span_x, span_y = float(place["size_m"][0]), float(place["size_m"][1])
    yaw = float(place.get("yaw_deg") or 0.0)
    th = float(place.get("top_thickness_m", 0.035))
    leg = float(place.get("leg_side_m", 0.05))
    inset = float(place.get("leg_inset", 0.08))
    _box(stage, f"{root}/Top", (span_x, span_y, th), (cx, cy, top - th / 2.0),
         material, yaw_deg=yaw, collision=solid)
    # leg centres in the surface's own frame, then rotated into the world
    c, s = np.cos(np.radians(yaw)), np.sin(np.radians(yaw))
    hx, hy = span_x / 2.0 - inset * span_x, span_y / 2.0 - inset * span_y
    height = max(top - th, 0.01)
    for i, (lx, ly) in enumerate(((hx, hy), (hx, -hy), (-hx, hy), (-hx, -hy))):
        wx, wy = cx + c * lx - s * ly, cy + s * lx + c * ly
        _box(stage, f"{root}/Leg_{i}", (leg, leg, height),
             (wx, wy, height / 2.0), material, yaw_deg=yaw, collision=solid)
    return {"top_z": round(top, 4), "size": [round(span_x, 4), round(span_y, 4),
                                             round(th, 4)],
            "centre_xy": [round(cx, 4), round(cy, 4)], "yaw_deg": round(yaw, 2),
            "legs": 4, "leg_side_m": leg,
            "collision": "enabled" if solid else
                         "disabled -- scenery, see the placement report"}


def _carried_prop(stage, path, place, uri, dims, track, fps, mass=None,
                  fallback_material=None):
    """The handled object: the catalog asset if there is one, scaled to the
    catalog's metric height, driven along the track the placement solved.

    It carries **no physics at all** -- not a disabled collider, not a
    kinematic body: an animated Xform. That is a declared approximation rather
    than an oversight. The object is carried because the phase signal says it
    is held, and nothing here closes the fingers on it, so any body driven
    along the hand is a body inside the hand, and PhysX charges for it: the
    same clip measured 0.165 deg of tracking RMSE with the prop absent and
    9.52 deg -- 135 deg on the right wrist alone -- with it present as a
    kinematic body, even with `physics:collisionEnabled` authored false on the
    prim. A grasp controller is what removes the approximation, and it is not
    in this adapter. The catalog's mass and body type are carried into the
    report so the next stage has them.
    """
    import placement as _pl

    xf = UsdGeom.Xform.Define(stage, path)
    prim = xf.GetPrim()
    scale = 1.0
    source = "primitive"
    if uri:
        bounds = _pl.asset_bounds(uri)
        prim.GetReferences().AddReference(uri)
        source = "asset"
        if bounds:
            lo, hi = bounds
            height = max(hi[2] - lo[2], 1e-6)
            scale = float(dims[2]) / height
    t_op = UsdGeom.Xformable(xf).AddTranslateOp()
    UsdGeom.Xformable(xf).AddScaleOp().Set(Gf.Vec3f(scale, scale, scale))
    for t, p in enumerate(track):
        t_op.Set(Gf.Vec3d(float(p[0]), float(p[1]), float(p[2])), Usd.TimeCode(t))
    if source == "primitive":
        c = UsdGeom.Cylinder.Define(stage, path + "/Body")
        c.CreateAxisAttr("Z")
        c.CreateHeightAttr(float(dims[2]))
        c.CreateRadiusAttr(float(dims[0]) / 2.0)
        if fallback_material is not None:
            UsdShade.MaterialBindingAPI(c.GetPrim()).Bind(fallback_material)
    return {"source": source, "asset": uri, "asset_scale": round(scale, 4),
            "samples": len(track), "fps": fps,
            "catalog_body": "dynamic", "catalog_mass_kg": mass,
            "collision": "none -- the object is animated, not simulated. A "
                         "kinematic body here cost 9.52 deg of tracking RMSE "
                         "against 0.165 deg without it, because nothing closes "
                         "the hand on it and the body ends up inside the hand"}


def write_scene(path: Path, objects, invariant_list, fit=None, floor_size=40.0,
                seat=True, placed=None, carried=None, fps=12.0,
                asset_root=None):
    """Floor, the support surfaces the invariants require, and the props.

    v2's first pass wrote a floor and a seat and left it there: "free-standing
    props wait for the placement solver -- standing them at a guessed depth
    would be exactly the kind of fabrication the provenance ledger exists to
    prevent". `placement.py` is that solver, so they no longer wait.
    """
    stage = _new_stage(path)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    # The scene layer carries time samples for anything the placement animates,
    # and USD rescales a sublayer's samples by the ratio of its
    # timeCodesPerSecond to the root layer's. Leaving this at the default 24
    # against a 12 fps root ran every prop at double speed -- the cup was at
    # the robot's mouth on frame 26 and back on the table by frame 50, which
    # is frame 52 and frame 100 of a 96-frame clip.
    stage.SetTimeCodesPerSecond(fps)
    stage.SetStartTimeCode(0)

    scene = UsdPhysics.Scene.Define(stage, "/World/PhysicsScene")
    scene.CreateGravityDirectionAttr(Gf.Vec3f(0.0, 0.0, -1.0))
    scene.CreateGravityMagnitudeAttr(9.81)

    grey = _material(stage, "/World/Looks/Floor", (0.52, 0.52, 0.54), 0.9)
    wood = _material(stage, "/World/Looks/Support", (0.45, 0.33, 0.24), 0.7)
    # Props the catalog has no asset for are drawn in a neutral grey rather than
    # the support surfaces' wood: a primitive stands for a *class*, and giving it
    # a material that suggests a specific object undoes the reason it is a
    # primitive. Lighter than the floor so it separates against it.
    neutral = _material(stage, "/World/Looks/Prop", (0.66, 0.67, 0.69), 0.45)

    # 40 m rather than 6: a small slab ends well inside the frame and its far
    # edge reads as a horizon the robot is floating above, which is how the
    # second render looked even with the geometry correct.
    # A UsdGeom.Plane collides but does not render under RTX -- the first video
    # came out with the robot and its seat floating in white space, which reads
    # as a broken result even though the geometry was right (pelvis underside
    # 0.4454 m, seat top 0.4404 m, sole 0.047 m). A thin slab does both jobs.
    _box(stage, "/World/Floor", (floor_size, floor_size, 0.02),
         (0.0, 0.0, -0.01), grey)

    written = [{"name": "floor", "kind": "plane", "z": 0.0,
                "provenance": "derived -- lowest foot landmark"}]
    if fit is not None and not fit.get("fits", True):
        written.append({"name": "seat", "kind": "omitted",
                        "provenance": "no seat clears the legs in this pose; "
                                      "with the pelvis pinned a box that fights "
                                      "them is worse than none"})
    seated = next((i for i in invariant_list if i["name"] == "seated"), None)
    if seated and seat and (fit is None or fit.get("fits", True)):
        # Height *and footprint* come from the pose the robot was actually asked
        # to hold. Sizing the seat from a textbook sitter put it 0.137 m too low
        # and 0.17 m too far back, so nothing touched it and the robot fell --
        # which is what `invariant.pelvis_holds_height` reported.
        if fit:
            seat_top = float(fit["seat_top_m"])
            cx, cy = fit["centre_xy"]
            w, d = fit["size_xy"]
            thick = float(fit.get("thickness_m", 0.06))
            why = "derived -- fitted to the commanded pose: " + fit["why"]
        else:
            seat_top = float(seated["seat_top_m"])
            cx, cy = 0.0, 0.0
            seat = next((o for o in objects if "sit" in
                         ((o.get("catalog") or {}).get("afford") or [])), None)
            w, d = (seat.get("dims_scaled_m")[:2] if seat else [0.35, 0.35])
            thick = seat_top
            why = "derived -- seated invariant, idealised sitter"
        _box(stage, "/World/Seat", (w, d, thick),
             (cx, cy, seat_top - thick / 2.0), wood)
        written.append({"name": "seat", "kind": "box",
                        "size": [round(w, 4), round(d, 4), round(thick, 4)],
                        "centre_xy": [round(cx, 4), round(cy, 4)],
                        "top_z": round(seat_top, 4), "provenance": why})

    # ---- the placed objects ------------------------------------------
    if carried is not None:
        stage.SetEndTimeCode(max(0, len(carried) - 1))
    for h in (placed or []):
        place = h.get("placement") or {}
        name = "".join(ch if ch.isalnum() else "_" for ch in h["label"]).strip("_")
        root = f"/World/Props/{name}"
        cat = h.get("catalog") or {}
        if place.get("kind") == "support_surface":
            info = _support_surface(stage, root, place, wood,
                                    solid=bool(place.get("solid", True)))
            written.append({"name": h["label"], "kind": "support_surface",
                            **info, "provenance": place.get("tier", "") + " -- "
                            + place.get("why", "")})
        elif place.get("kind") == "carried" and carried is not None:
            uri = _prop_asset(cat.get("asset"), asset_root)
            dims = h.get("dims_scaled_m") or cat.get("dims_m")
            info = _carried_prop(stage, root, place, uri, dims, carried, fps,
                                 mass=cat.get("mass_kg"),
                                 fallback_material=neutral)
            written.append({"name": h["label"], "kind": "carried", **info,
                            "provenance": place.get("tier", "") + " -- "
                            + place.get("why", "")})
        elif place.get("kind") == "free_standing":
            dims = place.get("size_m") or cat.get("dims_m")
            _box(stage, root, dims, place["position_m"], wood,
                 yaw_deg=place.get("yaw_deg", 0.0),
                 dynamic=(cat.get("body") == "dynamic"),
                 mass=cat.get("mass_kg"))
            written.append({"name": h["label"], "kind": "box",
                            "size": [round(float(v), 4) for v in dims],
                            "centre": place["position_m"],
                            "provenance": place.get("tier", "") + " -- "
                            + place.get("why", "")})
    stage.GetRootLayer().Save()
    return written


def write_robot(path: Path, asset_uri: str, root_pos=(0.0, 0.0, 0.0),
                root_yaw_deg: float = 0.0, fix_base: bool = False):
    """A layer that references the real G1 and places its root. No geometry.

    `fix_base` pins the pelvis to the world with a PhysicsFixedJoint. A USD
    articulation is floating-base unless something holds its root, and a
    floating base means the physics pass measures balance -- interesting for a
    standing clip, meaningless for a seated one, where the seat is what holds
    the robot up and the retarget already decided where the pelvis goes.

    Two earlier attempts are worth not repeating: a free root falls off the seat
    (pelvis 0.5929 -> 0.201 m), and teleporting a *dynamic* root onto the
    trajectory each step implies an enormous velocity that PhysX turns into
    energy (pelvis -> 0.834 m, feet 2.09 m up). Pinning it is the third way, and
    on a seated clip it costs almost nothing: this trajectory's pelvis moves
    1.5 cm in z and 4.6 cm in y over 96 frames. That approximation is recorded
    as a deviation rather than assumed away.
    """
    stage = _new_stage(path)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    g1 = UsdGeom.Xform.Define(stage, "/World/G1")
    g1.GetPrim().GetReferences().AddReference(asset_uri)
    _set_translate(g1.GetPrim(), root_pos)
    if root_yaw_deg:
        UsdGeom.Xformable(g1).AddRotateZOp(
            UsdGeom.XformOp.PrecisionDouble, "yaw").Set(float(root_yaw_deg))
    if fix_base:
        j = UsdPhysics.FixedJoint.Define(stage, "/World/G1_base_fix")
        j.CreateBody1Rel().SetTargets(["/World/G1/pelvis"])   # body0 empty = world
        j.CreateLocalPos0Attr(Gf.Vec3f(*[float(v) for v in root_pos]))
        j.CreateLocalPos1Attr(Gf.Vec3f(0.0, 0.0, 0.0))
        j.CreateLocalRot0Attr(Gf.Quatf(1.0))
        j.CreateLocalRot1Attr(Gf.Quatf(1.0))
    stage.GetRootLayer().Save()
    return {"asset": asset_uri, "root_pos": [round(float(v), 4) for v in root_pos],
            "root_yaw_deg": root_yaw_deg, "fixed_base": bool(fix_base)}


def write_motion(path: Path, robot_rel: str, scene_rel: str, fps: float,
                 frames: int):
    """The stage to open: sublayers robot and scene, carries the timeline."""
    stage = _new_stage(path)
    root = stage.GetRootLayer()
    root.subLayerPaths = [scene_rel, robot_rel]
    stage.SetTimeCodesPerSecond(fps)
    stage.SetStartTimeCode(0)
    stage.SetEndTimeCode(max(0, frames - 1))
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    root.Save()
    return {"sublayers": [scene_rel, robot_rel], "fps": fps, "frames": frames}


def _hand_contact(grasp, carried, holds, dev=None):
    """The invariant `invariants.derive` declares for every `hold` frame.

    Deferred through the whole of v2's first pass, because nothing was placed
    to measure against. It is satisfied by construction now -- the object is
    put on the hand rather than the hand brought to the object -- so the number
    it reports is worth exactly what that construction is worth, and the
    deviation that carries real information is `image_vs_hand` next to it.
    """
    if carried is None or not holds:
        return {"status": "deferred",
                "note": "nothing in this clip is held, or nothing graspable "
                        "survived arbitration"}
    d = [float(np.linalg.norm(np.asarray(carried[t]) - np.asarray(grasp[t])))
         for t in holds]
    worst = max(d)
    if dev:
        dev.record("invariant.hand_contact", "scene", 0.0, worst, "m",
                   tolerance=0.02,
                   how="acting hand's grasp centre to the handled object, over "
                       "every hold frame",
                   note="satisfied by construction: the object is placed on the "
                        "hand. What it does not say is whether the hand is "
                        "where the subject's was -- that is "
                        "`scene.<object>.image_vs_hand`")
    return {"status": "ok" if worst <= 0.02 else "FAIL",
            "worst_m": round(worst, 5), "frames": len(holds),
            "by": "construction -- the handled object is placed on the hand"}


def build(out_dir: Path, motion_npz: Path, objects, invariant_list,
          asset_root=None, fix_base=True, fix_feet=True, pose_facts=None,
          phase_labels=None, prov=None, dev=None, seat=True,
          phase_segments=None, dataset=None, scene_scale=1.0, hand="right",
          primary_label=None):
    """Write robot / scene / motion layers next to each other."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    z = np.load(motion_npz)
    fps = float(z["fps"][0]) if "fps" in z else 12.0
    n = int(z["joint_angles_rad"].shape[0])

    # Repair clipped-decomposition discontinuities before anything else reads
    # the angles: a joint pinned to its limit for two frames and an 87 deg step
    # coming out of it is a defect in the command, not in the tracking.
    import continuity
    names0 = [str(v) for v in z["joint_names"]]
    q0, cont = continuity.repair(z["joint_angles_rad"], names0,
                                 z["joint_limits_rad"], prov=prov, dev=dev)
    z = dict(z)
    z["joint_angles_rad"] = q0

    seated = next((i for i in invariant_list if i["name"] == "seated"), None)
    fit, root_z, feet = None, 0.0, None
    if seated:
        from invariants import seat_from_pose
        names = [str(s) for s in z["joint_names"]]
        root_traj = (z["pelvis_position_robot"][:, 2]
                     if "pelvis_position_robot" in z else None)
        fit = seat_from_pose(z["joint_angles_rad"], names, root_traj)
        root_z = float(fit["root_z_m"])

        # The retarget never put the feet on the floor -- the physics pass
        # measured it and filed it under `retarget.`, so this is where it is
        # paid. Solved here rather than inside the retarget so v1 stays intact.
        if fix_feet:
            import foot_contact
            mask, mrep = foot_contact.contact_mask(
                pose_facts or {"seated": bool(seated)},
                phase_labels or [], len(z["joint_angles_rad"]))
            if mask.any():
                q2, feet = foot_contact.solve(
                    z["joint_angles_rad"], names, root_z, mask,
                    z.get("joint_limits_rad"), prov=prov, dev=dev)
                feet["contact"] = mrep
                out = dict(z)
                out["joint_angles_rad"] = q2.astype("float32")
                np.savez_compressed(out_dir / "motion_v2.npz", **out)
                fit = seat_from_pose(q2, names, root_traj)
                root_z = float(fit["root_z_m"])
    root_xy = (0.0, 0.0)
    approx = None
    if fit and "pelvis_position_robot" in z:
        rt = np.asarray(z["pelvis_position_robot"], float)
        root_xy = (float(np.median(rt[:, 0])), float(np.median(rt[:, 1])))
        approx = {"axis_spread_m": [round(float(np.ptp(rt[:, i])), 4) for i in range(3)],
                  "max_offset_m": round(float(np.abs(
                      rt - np.median(rt, axis=0)).max()), 4)}
    robot = write_robot(out_dir / "robot_v2.usda", resolve_asset(asset_root),
                        root_pos=(root_xy[0], root_xy[1], root_z),
                        fix_base=fix_base and seated is not None)

    # ---- where the objects go ----------------------------------------
    placed, carried, place_report = [], None, None
    if dataset is not None:
        import placement
        plane = placement.image_plane(dataset)
        names = [str(v) for v in z["joint_names"]]
        root_pos = (root_xy[0], root_xy[1], root_z)
        boxes, boxes_why = placement.link_boxes(resolve_asset(asset_root))
        grasp, swept = placement.robot_tracks(z["joint_angles_rad"], names,
                                              root_pos, hand, boxes)
        holds = sorted({t for sg in (phase_segments or [])
                        if sg.get("phase") == "hold"
                        for t in range(int(sg["start_frame"]),
                                       int(sg["end_frame"]) + 1)})
        if plane is None:
            place_report = {"skipped": "no paired image/canonical landmarks, "
                                       "so nothing can be projected"}
        else:
            placed, carried, place_report = placement.solve(
                objects, plane, scene_scale,
                float((pose_facts or {}).get("floor_y") or 0.0),
                grasp, holds, swept, hand=hand, primary_label=primary_label,
                prov=prov, dev=dev)
            place_report["hand_contact"] = _hand_contact(grasp, carried, holds,
                                                         dev)
            place_report["image_plane_fit"] = plane
            place_report["link_collision_boxes"] = boxes_why

    scene = write_scene(out_dir / "scene_v2.usda", objects, invariant_list, fit,
                        seat=seat, placed=placed, carried=carried, fps=fps,
                        asset_root=asset_root)
    motion = write_motion(out_dir / "motion_v2.usda", "./robot_v2.usda",
                          "./scene_v2.usda", fps, n)
    return {"robot": robot, "scene": scene, "motion": motion, "seat_fit": fit,
            "fixed_base_approximation": approx, "foot_contact": feet,
            "continuity": cont, "placement": place_report,
            "root_z_m": round(root_z, 4),
            "root_z_why": ("seated invariant: pelvis sits at the seat top with the "
                           "thigh horizontal" if seated else "floor level")}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", required=True,
                    help="directory holding 04_behavior_dataset and 06_groot_g1")
    ap.add_argument("--out", default=None, help="default <dataset>/07_groot_g1_v2")
    ap.add_argument("--motion", default=None,
                    help="the retarget to build on; default "
                         "<dataset>/06_groot_g1/motion.npz. Point it elsewhere "
                         "to rebuild v2 on a corrected retarget without "
                         "rewriting v1, which is the baseline every "
                         "`change_from_v1` number is measured against")
    ap.add_argument("--asset-root", default=None,
                    help=f"default {PUBLIC_ASSET_ROOT}")
    ap.add_argument("--no-fix-feet", action="store_true",
                    help="skip the foot-contact solve and keep the retarget's "
                         "own leg angles, feet in the air and all")
    ap.add_argument("--no-props", action="store_true",
                    help="build the scene with the floor and seat only -- no "
                         "placement solve, no table, no carried object. The "
                         "isolation switch: a tracking regression is either "
                         "the props or it is not, and this answers it in one "
                         "container run")
    ap.add_argument("--no-seat", action="store_true",
                    help="build the scene without the seat -- with a pinned "
                         "pelvis the seat is scenery, so dropping it isolates "
                         "whether a tracking failure is contact or control")
    ap.add_argument("--free-base", action="store_true",
                    help="do not pin the pelvis -- the physics pass then tests "
                         "balance, which a seated clip does not have to pass")
    a = ap.parse_args(argv)

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import v2_preview

    from deviation import Deviations
    from provenance import Provenance

    ds = Path(a.dataset)
    dataset = v2_preview.find_dataset(str(ds))
    r = v2_preview.run(dataset)
    out = Path(a.out) if a.out else ds / "07_groot_g1_v2"
    dev, prov = Deviations(), Provenance()
    summary = json.loads((dataset / "behavior_summary.json").read_text("utf-8"))
    primary = (summary.get("primary_object") or {}).get("label")
    built = build(out, Path(a.motion) if a.motion else ds / "06_groot_g1/motion.npz",
                  r["objects"]["resolved"], r["invariants"], a.asset_root,
                  fix_base=not a.free_base, fix_feet=not a.no_fix_feet,
                  pose_facts=r["pose_facts"],
                  phase_labels=[s["phase"] for s in r["phases"].get("segments", [])],
                  seat=not a.no_seat,
                  phase_segments=r["phases"].get("segments", []),
                  dataset=None if a.no_props else dataset,
                  scene_scale=r["scene_scale"]["scale"],
                  hand=r["primary_hand"], primary_label=primary,
                  prov=prov, dev=dev)
    for i in r["invariants"]:
        if i["name"] == "seated" and built.get("seat_fit"):
            i["root_z_m"] = built["seat_fit"]["root_z_m"]
            i["seat_top_m"] = built["seat_fit"]["seat_top_m"]
            i["seat_why"] = built["seat_fit"]["why"]
    (out / "stage_report.json").write_text(
        json.dumps({"built": built, "invariants": r["invariants"],
                    "scene_scale": r["scene_scale"],
                    "stage_deviations": dev.report(),
                    "stage_provenance": prov.report()}, indent=1), "utf-8")
    print(json.dumps(built, indent=1))
    print("\n".join(dev.table()))
    print(f"\nwritten: {out}/motion_v2.usda  (open this one)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Drive the retargeted trajectory through PhysX and record how far it moved.

The kinematic stages decide what the robot *should* do. Nothing in them can
tell whether a G1 could hold the pose: v1's own report says as much --
"this is a kinematic replay ... nothing here is a dynamically feasible G1
trajectory", `"policy_was_run": false`. So the joint angles go in as drive
targets, PhysX resolves contact, self-collision and gravity, and what comes
back out is the trajectory that is written.

The point is not that physics makes it prettier. The point is that the gap
between what was asked and what came back is **measurable**, per joint and per
frame, and gets recorded that way:

    asked  q_target[t]  from the retarget
    got    q_actual[t]  after the solver had its say
    error  the tracking residual -- large means the retarget asked for a pose
           the robot cannot hold, which is a finding, not noise

The invariants declared upstream are checked here against the simulated state,
because this is the first stage where they can be measured rather than
asserted: soles on the floor, pelvis on the seat, knees inside the seated band.

Runs inside the Isaac Sim container:

    ./run_groot_g1_docker.sh ... (or)
    /isaac-sim/python.sh physics_settle.py --stage <motion_v2.usda> \\
        --motion <motion.npz> --report <out.json>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", required=True)
    ap.add_argument("--motion", required=True, help="motion.npz with joint_angles_rad")
    ap.add_argument("--report", required=True)
    ap.add_argument("--invariants", default=None, help="stage_report.json")
    ap.add_argument("--frames", type=int, default=0, help="0 = all")
    ap.add_argument("--substeps", type=int, default=16,
                    help="physics steps per animation frame")
    ap.add_argument("--stiffness", type=float, default=40000.0)
    ap.add_argument("--damping", type=float, default=1200.0)
    ap.add_argument("--root-mode", choices=("driven", "free"), default="free",
                    help="free (default): the root falls under gravity. "
                         "driven: the root is teleported onto the retarget's "
                         "pelvis trajectory each step -- MEASURED WORSE, see the "
                         "note in the source; a seated clip wants a kinematic "
                         "root, which is not implemented yet")
    ap.add_argument("--settle", type=int, default=240,
                    help="steps held on the first pose before recording")
    return ap.parse_args(argv)


def _make_driver(art, order):
    """Return a callable that sends position targets, whichever API this build has.

    `SingleArticulation` has carried the position-target call under three
    different names across Isaac Sim releases. Probing once and caching the hit
    costs nothing and saves a forty-second container start per guess.
    """
    if hasattr(art, "set_joint_position_targets"):
        return (lambda q: art.set_joint_position_targets(q, joint_indices=order),
                "set_joint_position_targets")
    try:
        from isaacsim.core.utils.types import ArticulationAction
    except Exception:                                        # noqa: BLE001
        from omni.isaac.core.utils.types import ArticulationAction
    if hasattr(art, "apply_action"):
        return (lambda q: art.apply_action(
            ArticulationAction(joint_positions=q, joint_indices=order)),
            "apply_action(ArticulationAction)")
    ctrl = art.get_articulation_controller()
    return (lambda q: ctrl.apply_action(
        ArticulationAction(joint_positions=q, joint_indices=order)),
        "articulation_controller.apply_action")


def _rigid_prim(path, verbose=True):
    """Read one link's world pose -- the class has moved between releases too.

    Failures are printed, not swallowed: a silently empty link set turns the
    seated invariant from "measured" back into "asserted", which is the whole
    thing this pass exists to stop.
    """
    attempts = (("isaacsim.core.prims", "SingleRigidPrim", "prim_path"),
                ("isaacsim.core.prims", "RigidPrim", "prim_paths_expr"),
                ("omni.isaac.core.prims", "RigidPrim", "prim_paths_expr"))
    errs = []
    for mod, name, kw in attempts:
        try:
            cls = getattr(__import__(mod, fromlist=[name]), name)
            return cls(**{kw: path}), f"{mod}.{name}({kw}=)"
        except Exception as e:                               # noqa: BLE001
            errs.append(f"{mod}.{name}: {e.__class__.__name__}: {e}")
    if verbose:
        print(f"could not wrap {path}:\n    " + "\n    ".join(errs))
    return None, None


def _rot(q):
    """wxyz quaternion -> rotation matrix. No scipy in the container image."""
    import numpy as np
    w, x, y, z = (float(v) for v in q)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _import_articulation():
    """Isaac Sim has moved this class between releases; try the known homes."""
    tried = []
    for mod, name in (("isaacsim.core.prims", "SingleArticulation"),
                      ("isaacsim.core.prims", "Articulation"),
                      ("omni.isaac.core.articulations", "Articulation")):
        try:
            m = __import__(mod, fromlist=[name])
            return getattr(m, name), f"{mod}.{name}"
        except Exception as e:                      # noqa: BLE001
            tried.append(f"{mod}.{name}: {e.__class__.__name__}")
    raise SystemExit("no Articulation class found; tried:\n  " + "\n  ".join(tried))


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True})

    import numpy as np
    import omni.usd
    from pxr import UsdPhysics
    from isaacsim.core.api import SimulationContext

    from deviation import Deviations
    dev = Deviations()

    z = np.load(args.motion)
    q_target = np.asarray(z["joint_angles_rad"], dtype=float)
    names = [str(s) for s in z["joint_names"]]
    fps = float(z["fps"][0]) if "fps" in z else 12.0
    n = q_target.shape[0] if not args.frames else min(args.frames, q_target.shape[0])

    inv = []
    if args.invariants and Path(args.invariants).exists():
        inv = json.loads(Path(args.invariants).read_text("utf-8")).get("invariants", [])

    omni.usd.get_context().open_stage(args.stage)
    stage = omni.usd.get_context().get_stage()

    # Gains go through the articulation controller, not UsdPhysics.DriveAPI.
    # Authoring the drive in USD mixes unit systems: USD angular drives are in
    # degrees, while ArticulationAction targets are in radians, and setting both
    # leaves the joint fighting itself -- measured as a 649.8 deg tracking error
    # on right_hip_pitch, a joint that was simply spinning.
    sim = SimulationContext(physics_dt=1.0 / (fps * args.substeps),
                            rendering_dt=1.0 / fps, stage_units_in_meters=1.0)
    ArticulationCls, art_src = _import_articulation()
    # The asset carries ArticulationRootAPI on its own pelvis, not on the Xform
    # that references it, so the path to drive is inside the reference. Finding
    # it beats hard-coding a path that changes with the asset revision.
    roots = [pr.GetPath().pathString for pr in stage.Traverse()
             if pr.HasAPI(UsdPhysics.ArticulationRootAPI)]
    if not roots:
        raise SystemExit("no prim on this stage has ArticulationRootAPI")
    art_path = roots[0]
    print(f"articulation root: {art_path}"
          + (f"  (of {len(roots)}: {roots})" if len(roots) > 1 else ""))
    art = ArticulationCls(art_path)

    # Every prim view has to exist *before* sim.reset(): reset builds the
    # physics view from what is registered, and wrapping a link afterwards
    # invalidates the one the articulation is already holding
    # ("Simulation view object is invalidated ... getDofPositions").
    # the sole is a polygon: the URDF's four foot contact spheres, 0.035 m
    # below the ankle roll frame at heel x = -0.050 and toe x = +0.120. The
    # first version of this check subtracted 0.035 from the ankle's *world* z
    # and called that the sole, which is only true for a level foot -- this
    # clip commanded 27-30 deg of ankle pitch, and the check read 9.7 mm while
    # the toe was 87 mm underground. Measuring the corners is the fix, and it
    # needs the link's orientation as well as its position.
    from invariants import FOOT_CONTACT_LOCAL, FOOT_PENETRATION_TOL_M
    base = art_path.rsplit("/", 1)[0]                       # /World/G1
    links, link_how = {}, {}
    for key, path in (("pelvis", art_path),
                      ("left_sole", base + "/left_ankle_roll_link"),
                      ("right_sole", base + "/right_ankle_roll_link")):
        pr, how = _rigid_prim(path)
        if pr is not None:
            links[key], link_how[key] = pr, how

    sim.reset()
    art.initialize()
    for key, pr in list(links.items()):
        try:
            if hasattr(pr, "initialize"):
                pr.initialize()
            print(f"  {key}: {link_how[key]}")
        except Exception as e:                               # noqa: BLE001
            print(f"  {key}: initialize failed -- {e.__class__.__name__}: {e}")
            links.pop(key)
    print(f"tracked links: {sorted(links)}")

    dof_names = list(art.dof_names)
    # order[k] is the articulation's index for names[k]. Values passed alongside
    # joint_indices=order must therefore stay in *names* order -- indexing them
    # by `order` as well permutes them twice, which silently commands a
    # scrambled pose. That bug cost three container runs: the pelvis held, the
    # knees looked seated, and the feet still ended up 0.74 m in the air.
    order = [dof_names.index(j) for j in names if j in dof_names]
    missing = [j for j in names if j not in dof_names]
    if missing:
        raise SystemExit(f"joints missing from the articulation: {missing[:5]}")

    # A seated clip does not test balance -- the seat holds the robot up and the
    # retarget already computed where the pelvis goes -- so the root ought to
    # follow that trajectory while PhysX resolves the limbs and the contacts.
    #
    # Teleporting the root each step is NOT how to do that, and the ledger said
    # so: setting the world pose every step implies an enormous velocity, which
    # PhysX turns into energy. Measured against a free root on the same stage:
    #
    #     free      pelvis 0.5929 -> 0.201 (rests, wrong pose)  feet 0.74 m up
    #     driven    pelvis 0.5929 -> 0.834 (climbing)           feet 2.09 m up
    #
    # The right implementation is a *kinematic* root -- flag the pelvis kinematic
    # so the solver may not move it, or pin it to the world with a joint whose
    # target follows the trajectory. Not implemented; `driven` is kept only so
    # the measurement above is reproducible.
    root_traj = None
    if args.root_mode == "driven" and "pelvis_position_robot" in z:
        root_traj = np.asarray(z["pelvis_position_robot"], float)
        root_quat = (np.asarray(z["pelvis_orientation_wxyz"], float)
                     if "pelvis_orientation_wxyz" in z else None)
        print(f"root: driven from pelvis_position_robot "
              f"(z {root_traj[:, 2].min():.4f}..{root_traj[:, 2].max():.4f})")
    else:
        root_quat = None
        print(f"root: {args.root_mode}")

    def place_root(t):
        if root_traj is None or "pelvis" not in links:
            return
        p = root_traj[min(t, len(root_traj) - 1)]
        q = (root_quat[min(t, len(root_quat) - 1)]
             if root_quat is not None else np.array([1.0, 0.0, 0.0, 0.0]))
        try:
            links["pelvis"].set_world_pose(position=np.asarray(p, float),
                                           orientation=np.asarray(q, float))
        except Exception as e:                               # noqa: BLE001
            if t == 0:
                print(f"  root placement failed: {e.__class__.__name__}: {e}")

    drive, drive_api = _make_driver(art, order)
    print(f"drive api: {drive_api}")
    try:
        ctrl = art.get_articulation_controller()
        ndof = len(dof_names)
        ctrl.set_gains(kps=np.full(ndof, args.stiffness),
                       kds=np.full(ndof, args.damping))
        print(f"gains: kp={args.stiffness} kd={args.damping} on {ndof} dof")
    except Exception as e:                                   # noqa: BLE001
        print(f"could not set gains: {e.__class__.__name__}: {e}")
    q_sim = np.zeros((n, len(order)))
    link_z = {k: np.zeros(n) for k in links}
    sole_z = {k: np.full((n, len(FOOT_CONTACT_LOCAL)), np.nan)
              for k in ("left_sole", "right_sole")}
    # hold the first pose until the solver stops arguing with it
    art.set_joint_positions(q_target[0], joint_indices=order)
    for _ in range(args.settle):
        place_root(0)
        drive(q_target[0])
        sim.step(render=False)

    for t in range(n):
        place_root(t)
        drive(q_target[t])
        for _ in range(args.substeps):
            sim.step(render=False)
        q_sim[t] = art.get_joint_positions(joint_indices=order)
        for k, pr in links.items():
            try:
                got = (pr.get_world_pose() if hasattr(pr, "get_world_pose")
                       else pr.get_world_poses())
                pos = np.asarray(got[0], float).ravel()[-3:]
                link_z[k][t] = float(pos[-1])
                if k in sole_z:
                    quat = np.asarray(got[1], float).ravel()[-4:]   # w x y z
                    sole_z[k][t] = (pos + FOOT_CONTACT_LOCAL @ _rot(quat).T)[:, 2]
            except Exception as e:                           # noqa: BLE001
                if t == 0:
                    print(f"  {k} pose read failed: {e.__class__.__name__}: {e}")
                link_z[k][t] = np.nan

    # ---- deviations -------------------------------------------------------
    err = np.abs(q_sim - q_target[:n])
    rms = float(np.sqrt((err ** 2).mean()))
    dev.record("physics.tracking_rmse", "physics", 0.0, np.degrees(rms), "deg",
               tolerance=3.0, how="q_actual vs q_target over every joint and frame")
    worst = int(np.argmax(err.max(axis=0)))
    dev.record(f"physics.tracking_max.{names[worst]}", "physics", 0.0,
               float(np.degrees(err[:, worst].max())), "deg", tolerance=10.0,
               how="worst single joint excursion")

    # the decisive invariant, measured rather than asserted
    contact = {}
    if "left_sole" in link_z and "right_sole" in link_z:
        soles = np.concatenate([sole_z["left_sole"].ravel(),
                                sole_z["right_sole"].ravel()])
        soles = soles[~np.isnan(soles)]
        if soles.size:
            contact["sole_above_floor_m"] = {"min": round(float(soles.min()), 4),
                                             "max": round(float(soles.max()), 4),
                                             "measured_on": "the four foot "
                                             "contact spheres of each foot"}
            dev.record("invariant.feet_on_floor", "contact", 0.0,
                       float(np.abs(soles).max()), "m", tolerance=0.02,
                       how="worst sole corner distance from z=0 over the clip")
            dev.record("invariant.feet_not_penetrating", "contact", 0.0,
                       float(max(0.0, -soles.min())), "m",
                       tolerance=FOOT_PENETRATION_TOL_M,
                       how="deepest foot contact sphere below the floor -- the "
                           "toe, which a single point under the ankle cannot see")
    # The root transform addresses the pelvis *origin*, which sits well above
    # the seat -- comparing it against seat_top was a reporting bug of exactly
    # the kind this ledger exists to make visible. Compare against root_z.
    fit = None
    if args.invariants and Path(args.invariants).exists():
        fit = json.loads(Path(args.invariants).read_text("utf-8")).get(
            "built", {}).get("seat_fit")
    if fit and fit.get("commanded_sole_z_m"):
        c = fit["commanded_sole_z_m"]
        dev.record("retarget.commanded_feet_on_floor", "contact", 0.0,
                   max(abs(c["min"]), abs(c["max"])), "m", tolerance=0.02,
                   how="where the *commanded* trajectory puts the soles with the "
                       "pelvis where the retarget asked -- the ceiling on what "
                       "physics can achieve without fixing the retarget",
                   note=f"commanded sole z ranges {c['min']} .. {c['max']} m")

    seated_inv = next((i for i in inv if i["name"] == "seated"), None)
    root_z = float((seated_inv or {}).get("root_z_m") or 0.0) or None
    if root_z is not None and "pelvis" in link_z:
        pz = link_z["pelvis"][~np.isnan(link_z["pelvis"])]
        if pz.size:
            contact["pelvis_z_m"] = {
                "min": round(float(pz.min()), 4), "max": round(float(pz.max()), 4),
                "start": round(float(pz[0]), 4), "end": round(float(pz[-1]), 4),
                "asked_root_z": root_z,
                "seat_top": (seated_inv or {}).get("seat_top_m")}
            dev.record("invariant.pelvis_holds_height", "contact", root_z,
                       float(pz.mean()), "m", tolerance=0.02,
                       how="mean pelvis origin height against the root the "
                           "seated invariant asked for")
            dev.record("invariant.pelvis_not_falling", "contact", 0.0,
                       float(abs(pz[-1] - pz[0])), "m", tolerance=0.02,
                       how="how far the pelvis drifted from first frame to last "
                           "-- a robot resting on something does not move")

    for i in inv:
        if i["name"] == "seated":
            lo, hi = 60.0, 140.0
            kn = [names.index(j) for j in
                  ("left_knee_joint", "right_knee_joint") if j in names]
            if kn:
                knee_deg = np.degrees(np.abs(q_sim[:, kn]))
                # URDF knee is flexion from straight; report the interior angle
                interior = 180.0 - knee_deg
                dev.record("invariant.seated.knee_min", "contact", lo,
                           float(interior.min()), "deg", tolerance=0.0,
                           direction="under", how="knee inside the seated band")
                dev.record("invariant.seated.knee_max", "contact", hi,
                           float(interior.max()), "deg", tolerance=0.0,
                           direction="over", how="knee inside the seated band")

    report = {
        "stage": args.stage, "frames": n, "fps": fps,
        "articulation_class": art_src, "articulation_root": art_path,
        "drive_api": drive_api,
        "dof": len(order),
        "settings": {"substeps": args.substeps, "stiffness": args.stiffness,
                     "damping": args.damping, "settle_steps": args.settle,
                     "root_mode": args.root_mode},
        "tracking": {
            "rmse_deg": round(float(np.degrees(rms)), 4),
            "max_deg": round(float(np.degrees(err.max())), 4),
            "per_joint_max_deg": {names[i]: round(float(np.degrees(err[:, i].max())), 3)
                                  for i in range(len(order))},
        },
        "contact": contact,
        "link_z_m": {k: [round(float(v), 4) for v in link_z[k]] for k in link_z},
        "sole_corner_z_m": {k: [[round(float(v), 4) for v in row]
                                for row in sole_z[k]] for k in sole_z
                            if not np.isnan(sole_z[k]).all()},
        "deviations": dev.report(),
        "q_actual_written": True,
    }
    np.savez_compressed(str(Path(args.report).with_suffix(".npz")),
                        joint_angles_rad=q_sim.astype("float32"),
                        joint_names=np.array(names),
                        joint_angles_target_rad=q_target[:n].astype("float32"),
                        fps=np.array([fps], "float32"))
    Path(args.report).write_text(json.dumps(report, indent=1), "utf-8")
    print(json.dumps({k: report[k] for k in
                      ("frames", "dof", "articulation_class", "tracking")}, indent=1))
    print("\n".join(dev.table()))
    print("\nwritten:", args.report)
    app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

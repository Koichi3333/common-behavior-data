#!/usr/bin/env python3
"""Render a CBD GR00T / Unitree G1 stage to PNG sequences.

The only file in this adapter that needs the Isaac Sim runtime, and
deliberately thin: `cbd_adapter_groot_g1.py` has already decided every joint
angle, the root pose, the set and both cameras, so all that is left here is to
walk the timeline and capture.

Two cameras, because the two outputs want different things:

    /World/Camera .... the film camera, framed like the source clip
    ego_cam .......... the robot's own head camera, on `d435_link`, which is
                       what the GR00T dataset's `observation.images.ego_view`
                       has to be

    /isaac-sim/python.sh groot_g1_render.py --stage motion.usda --out frames/

writes `frames/film/` and `frames/ego/`. Playback is kinematic: the stage
carries time-sampled `xformOp:orient` values and nothing else, so no physics
step is run and no articulation is created.
"""
import argparse
import json
import os
import sys

EGO_CAM = ("/World/G1/pelvis/waist_yaw_link/waist_roll_link/torso_link/"
           "d435_link/ego_cam")


def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", required=True, help="path to motion.usda")
    ap.add_argument("--out", required=True, help="directory for the PNG sequences")
    ap.add_argument("--width", type=int, default=720)
    ap.add_argument("--height", type=int, default=1280)
    ap.add_argument("--ego-width", type=int, default=640)
    ap.add_argument("--ego-height", type=int, default=480)
    ap.add_argument("--camera", default="/World/Camera")
    ap.add_argument("--ego-camera", default=EGO_CAM)
    ap.add_argument("--no-ego", action="store_true",
                    help="skip the ego view (the GR00T dataset then has no video)")
    ap.add_argument("--subframes", type=int, default=16,
                    help="RTX accumulation subframes per captured frame")
    ap.add_argument("--warmup", type=int, default=60,
                    help="app updates before the first capture, to let RTX settle")
    ap.add_argument("--renderer", default="RaytracedLighting",
                    choices=["RaytracedLighting", "PathTracing"])
    ap.add_argument("--start", type=int, default=None)
    ap.add_argument("--end", type=int, default=None)
    return ap.parse_args(argv)


def main(argv):
    args = parse_args(argv)
    stage_path = os.path.abspath(args.stage)
    out_dir = os.path.abspath(args.out)
    film_dir = os.path.join(out_dir, "film")
    ego_dir = os.path.join(out_dir, "ego")
    os.makedirs(film_dir, exist_ok=True)
    os.makedirs(ego_dir, exist_ok=True)

    from isaacsim import SimulationApp
    sim = SimulationApp({"headless": True, "renderer": args.renderer,
                         "width": args.width, "height": args.height})

    import carb
    import omni.usd
    import omni.timeline
    import omni.replicator.core as rep

    settings = carb.settings.get_settings()
    # Wait for textures and materials instead of rendering a half-loaded frame.
    settings.set("/rtx/materialDb/syncLoads", True)
    settings.set("/rtx/hydra/materialSyncLoads", True)
    settings.set("/omni.kit.plugin/syncUsdLoads", True)
    settings.set("/app/asyncRendering", False)
    settings.set("/app/asyncRenderingLowLatency", False)
    settings.set("/rtx/reflections/enabled", True)
    settings.set("/rtx/ambientOcclusion/enabled", True)
    # Fixed exposure: auto-exposure would re-grade every frame and the video
    # would breathe as the robot moves through the frame.
    settings.set("/rtx/post/histogram/enabled", False)
    settings.set("/rtx/post/tonemap/filmIso", 100.0)
    if args.renderer == "PathTracing":
        settings.set("/rtx/pathtracing/spp", 1)
        settings.set("/rtx/pathtracing/totalSpp", 64)
        settings.set("/rtx/pathtracing/optixDenoiser/enabled", 1)

    ctx = omni.usd.get_context()
    # open_stage returns a bool on some builds and a (bool, error) pair on
    # others; normalise before checking.
    result = ctx.open_stage(stage_path)
    ok = result[0] if isinstance(result, tuple) else result
    if not ok:
        print("FAILED to open stage:", result, flush=True)
        sim.close()
        return 1
    stage = ctx.get_stage()
    start = args.start if args.start is not None else int(stage.GetStartTimeCode())
    end = args.end if args.end is not None else int(stage.GetEndTimeCode())
    fps = stage.GetTimeCodesPerSecond() or 24.0
    print(f"stage={stage_path}\nframes={start}..{end} @ {fps} fps", flush=True)

    cameras = [(args.camera, film_dir, args.width, args.height)]
    if not args.no_ego:
        cameras.append((args.ego_camera, ego_dir, args.ego_width, args.ego_height))
    products = []
    for path, directory, width, height in cameras:
        if not stage.GetPrimAtPath(path):
            print(f"FAILED: no camera at {path}", flush=True)
            sim.close()
            return 1
        product = rep.create.render_product(path, (width, height))
        writer = rep.WriterRegistry.get("BasicWriter")
        writer.initialize(output_dir=directory, rgb=True, frame_padding=5)
        writer.attach([product])
        products.append((path, directory))

    timeline = omni.timeline.get_timeline_interface()
    timeline.set_start_time(start / fps)
    timeline.set_end_time(end / fps)
    timeline.set_looping(False)
    timeline.stop()

    for _ in range(args.warmup):
        sim.update()

    for frame in range(start, end + 1):
        timeline.set_current_time(frame / fps)
        sim.update()
        rep.orchestrator.step(rt_subframes=args.subframes, pause_timeline=True,
                              delta_time=0.0)
        if frame % 12 == 0 or frame == end:
            print(f"  frame {frame - start + 1}/{end - start + 1}", flush=True)

    rep.orchestrator.wait_until_complete()
    counts = {}
    for path, directory in products:
        counts[directory] = sorted(f for f in os.listdir(directory)
                                   if f.startswith("rgb_"))
    manifest = {"stage": stage_path, "fps": fps, "start": start, "end": end,
                "renderer": args.renderer,
                "cameras": [{"prim": path, "dir": os.path.basename(directory),
                             "frames": len(counts[directory])}
                            for path, directory in products]}
    with open(os.path.join(out_dir, "render_manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)
    for path, directory in products:
        print(f"RENDERED {len(counts[directory])} frames from {path} -> {directory}",
              flush=True)
    sim.close()
    expected = end - start + 1
    return 0 if all(len(v) == expected for v in counts.values()) else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

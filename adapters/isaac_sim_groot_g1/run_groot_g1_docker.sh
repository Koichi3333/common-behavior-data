#!/usr/bin/env bash
# Run the render step inside the NGC Isaac Sim container.
#
#   ./run_groot_g1_docker.sh <sample_output dir> [extra groot_g1_render.py args...]
#
# Everything the render needs is in the repository, so the container only has
# to see two directories: this repo and a scratch directory for the caches and
# the PNG sequences. Without the cache mounts every run recompiles the RTX
# shaders, which costs about ten minutes.
#
# The image runs as uid 1234 with HOME=/isaac-sim -- not root -- so the caches
# are mounted under that HOME and the host-side directories are made
# world-writable. Files it writes come back owned by 1234; that is why the
# scratch directory is kept out of the repository.
set -uo pipefail

IMAGE="${ISAACSIM_IMAGE:-nvcr.io/nvidia/isaac-sim:6.0.0-dev2}"
SCRATCH="${ISAACSIM_SCRATCH:-$HOME/.cache/cbd-isaacsim}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <sample_output dir> [args for groot_g1_render.py...]" >&2
  echo "example: $0 examples/human-capture/sample_output" >&2
  exit 1
fi
SAMPLE="$(cd "$1" && pwd)"; shift
STAGE_REL="${SAMPLE#$REPO/}/06_groot_g1/motion.usda"
if [[ ! -f "$REPO/$STAGE_REL" ]]; then
  echo "no $STAGE_REL -- run cbd_adapter_groot_g1.py first" >&2
  exit 1
fi

mkdir -p "$SCRATCH"/{kit,ov,pip,warp,matplotlib,glcache,computecache,logs,data,documents}
mkdir -p "$SCRATCH"/g1_frames/{film,ego}
chmod -R a+rwX "$SCRATCH" 2>/dev/null || true

docker run --rm --gpus all \
  -e ACCEPT_EULA=Y -e OMNI_KIT_ACCEPT_EULA=YES -e PRIVACY_CONSENT=Y \
  -v "$SCRATCH/kit:/isaac-sim/kit/cache:rw" \
  -v "$SCRATCH/ov:/isaac-sim/.cache/ov:rw" \
  -v "$SCRATCH/pip:/isaac-sim/.cache/pip:rw" \
  -v "$SCRATCH/warp:/isaac-sim/.cache/warp:rw" \
  -v "$SCRATCH/matplotlib:/isaac-sim/.cache/matplotlib:rw" \
  -v "$SCRATCH/glcache:/isaac-sim/.cache/nvidia/GLCache:rw" \
  -v "$SCRATCH/computecache:/isaac-sim/.nv/ComputeCache:rw" \
  -v "$SCRATCH/logs:/isaac-sim/.nvidia-omniverse/logs:rw" \
  -v "$SCRATCH/data:/isaac-sim/.local/share/ov/data:rw" \
  -v "$SCRATCH/documents:/isaac-sim/Documents:rw" \
  -v "$SCRATCH/g1_frames:/frames:rw" \
  -v "$REPO:/repo:ro" \
  --entrypoint /isaac-sim/python.sh \
  "$IMAGE" /repo/adapters/isaac_sim_groot_g1/groot_g1_render.py \
    --stage "/repo/$STAGE_REL" --out /frames "$@"
RC=$?

echo
echo "PNG sequences: $SCRATCH/g1_frames/{film,ego}"
echo "next:  python adapters/isaac_sim_groot_g1/compose_video.py \\"
echo "         --frames $SCRATCH/g1_frames \\"
echo "         --dataset $SAMPLE/04_behavior_dataset \\"
echo "         --out-dir $SAMPLE/06_groot_g1"
exit $RC

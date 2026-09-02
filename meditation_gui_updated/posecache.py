"""Disk cache for the pose landmarks of the static reference images.

Every stage in the frontback1 sequence opens by running MediaPipe Pose at
model_complexity=2 over its nine reference stills. Those images never change,
but the inference ran again on each launch and cost ~0.95s per stage — a large
part of the black gap the visitor sees between stages.

Landmarks are cached under .pose_cache/, keyed on each image's size and
modification time, so editing or replacing a reference still invalidates its
entry on its own. What is stored is the raw normalised landmark list MediaPipe
returns, which lets every consumer reproduce its own derived values exactly:
Front.py and depth/adjustment_test_updated.py scale them to pixels to measure
angles, while depth/splitSide.py and splitGaze.py use them normalised.

Callers pass a `variant` naming the model that produced the landmarks. A
Pose built with static_image_mode=True does not return the same landmarks as
the streaming model the depth stages reuse, so the two must not share entries.
"""

import json
import os

from paths import BASE_DIR

CACHE_DIR = BASE_DIR / ".pose_cache"

# variant -> {image path: entry}, so a stage that looks up nine images reads
# the JSON once rather than nine times.
_LOADED = {}


def _stamp(path):
    st = os.stat(path)
    return "%d:%d" % (st.st_size, st.st_mtime_ns)


def _cache_file(variant):
    return CACHE_DIR / ("%s.json" % variant)


def _load(variant):
    if variant not in _LOADED:
        try:
            with open(_cache_file(variant)) as fh:
                _LOADED[variant] = json.load(fh)
        except (OSError, ValueError):
            # Missing or corrupt cache is not an error — it just means every
            # image has to be inferred again, exactly as before this cache.
            _LOADED[variant] = {}
    return _LOADED[variant]


def _save(variant, cache):
    try:
        CACHE_DIR.mkdir(exist_ok=True)
        tmp = _cache_file(variant).with_suffix(".tmp")
        with open(tmp, "w") as fh:
            json.dump(cache, fh)
        os.replace(tmp, _cache_file(variant))
    except OSError:
        # A read-only checkout still works; it just recomputes every launch.
        pass


def _infer(paths, build_pose):
    import cv2

    pose = build_pose()
    entries = {}
    for path in paths:
        image = cv2.imread(str(path))
        if image is None:
            # Keep the miss out of the cache so a reference image that is
            # merely absent right now is retried on the next launch.
            entries[path] = {"width": 0, "height": 0, "landmarks": None,
                             "stamp": None}
            continue
        height, width = image.shape[:2]
        results = pose.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        entries[path] = {
            "width": width,
            "height": height,
            "landmarks": ([[lm.x, lm.y, lm.z] for lm in results.pose_landmarks.landmark]
                          if results.pose_landmarks else None),
            "stamp": _stamp(path),
        }
    return entries


def landmarks_for(image_paths, variant, build_pose, recompute_all=False):
    """Cached Pose landmarks for a set of static reference images.

    Returns one entry per path, in the order given, each a dict of `width`,
    `height` and `landmarks` — the raw normalised [x, y, z] triples, or None
    where no pose was detected. build_pose() is called only when something
    actually has to be inferred, so a warm cache also skips building the model.

    Set recompute_all when build_pose returns a *streaming* model. Such a model
    carries tracking state from one image to the next, so its landmarks depend
    on how many images preceded them; inferring only the stale ones would give
    values a full pass never produces.
    """
    paths = [str(p) for p in image_paths]
    cache = _load(variant)

    stale = []
    for path in paths:
        try:
            stamp = _stamp(path)
        except OSError:
            stale.append(path)
            continue
        entry = cache.get(path)
        if not entry or entry.get("stamp") != stamp:
            stale.append(path)

    if stale:
        fresh = _infer(paths if recompute_all else stale, build_pose)
        cache.update({p: e for p, e in fresh.items() if e["stamp"]})
        _save(variant, cache)
        # Anything not inferred this time was already a warm hit above.
        return [fresh.get(path) or cache[path] for path in paths]

    return [cache[path] for path in paths]

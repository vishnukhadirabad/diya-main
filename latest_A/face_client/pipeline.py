import logging 
import os 
import time     
from pathlib import Path
from typing import List, Dict, Tuple, Optional 

import cv2
import numpy as np

from .config import Config 
from .errors import ClientError 
from .detection import FaceDetection, FaceDetector
from .embedders import create_embedder, get_embedder_spec
from .diagnostic_db import DiagnosticDB
from .server_client import ServerClient

logger = logging.getLogger("face_client")

# Model presence check  

def _raise_missing(missing: list, remediation: str) -> None:
    lines = [f"Missing model: {label} ({path})" for label, path in missing]
    lines.append(remediation)
    raise ClientError("\n".join(lines))

def _ensure_models(cfg: Config) -> None:
    spec = get_embedder_spec(cfg)
    embedder_path = getattr(cfg, spec["path_attr"])
    required = [
        ("YuNet face detector", cfg.face_detector_path),
        (spec["label"], embedder_path),
    ]
    missing = [(label, path) for label, path in required if not os.path.exists(path)]
    if missing:
        _raise_missing(
            missing,
            f"Copy the missing .onnx file(s) into {os.path.dirname(missing[0][1])} "
            f"(same files as mock-server/models/).",
        )

# Shared helpers 

def _load_image(path: str) -> np.ndarray:
    frame = cv2.imread(path)
    if frame is None:
        raise ClientError(f"Failed to load image: {path}")
    logger.info("Image: %dx%d <- %s", frame.shape[1], frame.shape[0], path)
    return frame

def _save_face_crop(frame: np.ndarray, bbox: Tuple, name: str, faces_dir: str) -> str:
    os.makedirs(faces_dir, exist_ok = True)
    safe = "".join(c if c.isalnum() else "_" for c in name).lower()
    path = os.path.join(faces_dir, f"{safe}_{int(time.time())}.jpg")
    x1, y1, x2, y2 = bbox
    ih, iw = frame.shape[:2]
    cv2.imwrite(path, frame[max(0, y1):min(ih, y2), max(0, x1):min(iw, x2)])
    return path

def _detect_and_embed(frame: np.ndarray, detector, embedder,) -> Tuple[FaceDetection, np.ndarray]:
    detection = detector.detect(frame)
    if detection is None:
        raise ClientError("No face detected in the image")
    x1, y1, x2, y2 = detection.bbox
    logger.info("Face: bbox = (%d, %d, %d, %d) score = %.3f", x1, y1, x2, y2, detection.score)
    vec = embedder.embed(frame, detection)
    logger.info("Embedding: %d-dim", vec.shape[0])
    return detection, vec 

def _open_opencv_source(device: int):
    cap = cv2.VideoCapture(device)
    if not cap.isOpened():
        raise ClientError(f"Cannot open camera device: {device}")

    def read():
        ret, frame = cap.read()
        return frame if ret else None 
    
    def release():
        cap.release()
    
    return read, release

def _write_person_detail(path: str, content: str) -> None:
    """
    Writes (overwrites -- mode 'w', not 'a') a single line to person_detail.txt.
    Called exactly once per run_camera() invocation, right before it exits,
    with either the confirmed name or "error-person" on a failed/timed-out
    detection -- so every run leaves the file holding only the latest result.
    """
    try:
        with open(path, "w") as f:
            f.write(content + "\n")
        logger.info("person_detail.txt written: %s -> %s", content, path)
    except OSError as e:
        logger.error("Failed to write person_detail.txt at %s: %s", path, e)

def _open_picamera2_source(size=(640, 480)):
    try:
        from picamera2 import Picamera2
    except ImportError as e:
        raise ClientError("camera.backend is 'picamera2' but the picamera2 package is not importable.\n"
              "Install it via apt (not pip): sudo apt install -y python3-picamera2\n"
              "Then run this client with a Python that can see it, which is either the "
              "system Python directly, or a venv created with "
              "'python3 -m venv --system-site-packages .venv'.  NOT the isolated "
              "./run.sh Podman container, which cannot access libcamera."
          ) from e
    picam2 = Picamera2()
    # Despite the name, picamera2's "BGR888" format actually returns frames in
    # R,G,B memory order (confirmed on real hardware — requesting it and
    # skipping conversion produced blue-tinted "Smurf" faces, the classic
    # symptom of swapped R/B channels). So we still request "BGR888" here (the
    # unspecified/default format instead returns a 4-channel XBGR array, which
    # is worse), but explicitly swap channels afterward to get real BGR order
    # matching cv2.imread()'s convention, instead of trusting the format name.
    config = picam2.create_preview_configuration(main = {"format": "BGR888", "size": size})
    picam2.configure(config)
    picam2.start()

    def read():
        frame = picam2.capture_array()
        return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    
    def release():
        picam2.stop()
        picam2.close()
    
    return read, release

# High level client

class FaceRecognitionClient:
    """
    High-level face recognition client.

    Usage:
        client = FaceRecognitionClient()
        client.identify("photo.jpg")
    """

    def __init__(self, config_path: Optional[str] = None):
        self.cfg = Config(config_path) if config_path else Config()
        self._detector = None
        self._embedder = None
    
    def _ensure_backend(self):
        """Lazily build the detector + embedder (list_faces() never needs them)."""

        if self._detector is None or self._embedder is None:
            _ensure_models(self.cfg)
            try:
                self._detector = FaceDetector(self.cfg)
                self._embedder = create_embedder(self.cfg)
                logger.info(
                    "Detector: YuNet  |  Embedder: %s (%d-dim)",
                    self.cfg.embedder_model, self._embedder.DIM,
                )
            except ClientError:
                raise 
            except Exception as e:
                raise ClientError(f"Model init failed: {e}") from e

        return self._detector, self._embedder
    
    def identify(self, image_path: str, mode: Optional[str] = None) -> Optional[str]:
        """Identify a face in image_path. mode overrides cfg.mode ('server'/'diagnostic')."""
        
        if not os.path.isfile(image_path):
            raise ClientError(f"Image not found: {image_path}")
        
        detector, embedder = self._ensure_backend()
        effective_mode = (mode or self.cfg.mode).lower()

        frame = _load_image(image_path)
        _, vec = _detect_and_embed(frame, detector, embedder)

        if effective_mode == "diagnostic":
            return self._identify_diagnostic(vec)
        
        return self._identify_server(vec)
    
    def _identify_server(self, vec:np.ndarray) -> Optional[str]:
        logger.info("MODE: server (%s)", self.cfg.server_url)
        client = ServerClient(self.cfg)
        server_ok = client.health_check()

        if server_ok:
            name = client.identify(vec)
            client.close()
            print()
            print(f">>> Recognised: {name}" if name else ">>> Unknown face  (via server)")
            print()
            return name 
        
        client.close()
        logger.warning("Server unreachable — falling back to diagnostic (local SQLite).")
        
        return self._identify_diagnostic(vec, fallback = True)
    
    def _identify_diagnostic(self, vec: np.ndarray, fallback: bool = False) -> Optional[str]:
        cfg = self.cfg
        db = DiagnosticDB(cfg)

        if fallback and not db.list_all():
            raise ClientError(
                "Server unreachable and no local faces registered. "
                "Register first: client.register(name, image_path)"
            )
        
        t0 = time.time()
        name, img_path, sim = db.search(vec)
        elapsed_ms = (time.time() - t0) * 1000

        topk = db.search_topk(vec)
        topk_str = ", ".join(f"{n}={s:.3f}" for n, s in topk) or "<no compatible embeddings>"
        tag = "[Diagnostic fallback] " if fallback else ""
        logger.info("%sTop-%d: %s  (%.1f ms)", tag, cfg.topk, topk_str, elapsed_ms)

        fb = "diagnostic fallback  " if fallback else ""
        print()
        if name:
            print(f">>> Recognised: {name}  ({fb}sim={sim:.4f})" if fallback else f">>> Recognised: {name}  (cosine sim={sim:.4f})")
            if img_path:
                print(f"Matched: {img_path}")
        else:
            print(f">>> Unknown ({fb}best sim={sim:.4f} threshold={cfg.cosine_threshold})")
            print(f"Nearest: {topk_str}")
        print()
        return name 
    
    def register(self, name: str, image_path: str) -> int:
        detector, embedder = self._ensure_backend()
        logger.info("REGISTER '%s' <- %s", name, image_path)
        frame = _load_image(image_path)
        detection, vec = _detect_and_embed(frame, detector, embedder)
        crop_path = _save_face_crop(frame, detection.bbox, name, self.cfg.diag_faces_dir)
        logger.info("Face crop saved: %s", crop_path)
        db = DiagnosticDB(self.cfg)
        face_id = db.register(name, vec, crop_path)
        print(f"\n>>> Registered '{name}' (face_id={face_id} dim={vec.shape[0]})")
        print(f"Crop: {crop_path}")
        print(f"DB: {self.cfg.diag_db_path}\n")

        return face_id

    def list_faces(self) -> List[Dict]:
        db = DiagnosticDB(self.cfg)
        faces = db.list_all()
        if not faces:
            print("\n(No faces registered yet — use register() first.)\n")
            return faces
        print(f"\n{'ID':>4}  {'Name':<20}  {'Registered':<20}  Image")
        print("-" * 80)
        for f in faces:
            print(f"{f['face_id']:>4}  {f['name']:<20}  {str(f['created_at'])[:19]:<20}  {f['image_path']}")
        print(f"\nTotal: {len(faces)} face(s) in {self.cfg.diag_db_path}\n")

        return faces

    def delete_face(self, face_id: int) -> bool:
        db = DiagnosticDB(self.cfg)
        deleted = db.delete(face_id)
        if deleted:
            print(f"\n>>> Deleted face_id={face_id}\n")
        else:
            print(f"\n>>> No face found with face_id={face_id}\n")
        return deleted

    def run_camera(self) -> Optional[str]:
        detector, embedder = self._ensure_backend()
        cfg = self.cfg
        device = cfg.camera_device
        frame_skip = cfg.camera_frame_skip
        backend = cfg.camera_backend

        # ---- ADD: exit-on-confirmed-match ----
        # Previously run_camera() had no exit path tied to a successful
        # recognition at all -- it looped forever until 'q' was pressed or
        # the camera read failed (visible in the earlier traceback: it only
        # died from a manual Ctrl+C inside read_frame()). This adds a
        # debounced confirmation: the SAME name has to come back on
        # CONFIRM_MATCHES consecutive identification cycles (each cycle
        # already only runs every frame_skip frames) before the loop exits.
        # A single lucky/noisy frame won't trigger it, which matters here
        # since confidence fluctuated ~0.52-0.74 frame to frame in testing.
        #
        # Configurable via cfg.camera_confirm_matches in config.yaml; falls
        # back to 5 if that key isn't present, so this doesn't break setups
        # that haven't added the key yet.
        CONFIRM_MATCHES = getattr(cfg, "camera_confirm_matches", 5)
        match_streak = 0
        last_match_name = None
        confirmed_name = None

        # ---- ADD: overall detection time budget + person_detail.txt result ----
        # Requirement: give the person 5-8 seconds total to be confirmed,
        # then terminate either way -- writing the confirmed name if
        # successful, or "error-person" if the timeout is hit (or the
        # camera fails) before a confirmed match happens. The file is
        # opened in "w" mode via _write_person_detail(), so each run
        # overwrites the previous run's result rather than appending.
        #
        # Configurable via cfg.camera_detect_timeout_s; defaults to 7s
        # (middle of the 5-8s window) if that key isn't in config.yaml.
        # NOTE: with the default frame_skip=10 and CONFIRM_MATCHES=5, the
        # confirmation streak itself needs several identification cycles to
        # complete -- if a 5-8s budget feels too tight to reliably confirm,
        # lower camera_confirm_matches and/or camera_frame_skip in
        # config.yaml so a full streak can finish within the window.
        DETECT_TIMEOUT_S = getattr(cfg, "camera_detect_timeout_s", 7)
        if getattr(cfg, "config_path", None):
            person_detail_path = os.path.join(
                os.path.dirname(os.path.abspath(cfg.config_path)), "person_detail.txt"
            )
        else:
            person_detail_path = os.path.join(os.getcwd(), "person_detail.txt")
        start_time = time.time()
        timed_out = False

        if backend == "picamera2":
            read_frame, release_source = _open_picamera2_source()
            logger.info("Camera backend=picamera2 | frame_skip=%d | embedder=%d-dim", frame_skip, embedder.DIM)
        elif backend == "opencv":
            read_frame, release_source = _open_opencv_source(device)
            logger.info("Camera %d opened | frame_skip=%d | embedder=%d-dim", device, frame_skip, embedder.DIM)
        else:
            raise ClientError(f"Unknown camera.backend '{backend}' (expected 'opencv' or 'picamera2')")

        use_server = False
        server_client = None
        diag_db = None

        if cfg.mode != "diagnostic":
            server_client = ServerClient(cfg)
            if server_client.health_check():
                use_server = True
            else:
                logger.warning("Server unreachable — falling back to diagnostic (local SQLite).")
                server_client.close()
                server_client = None

        if not use_server:
            diag_db = DiagnosticDB(cfg)

        label = ""
        last_bbox = None
        frame_no = 0

        print("Camera running — press 'q' to quit")
        print(f"Will auto-exit after {CONFIRM_MATCHES} consecutive matches on the same face")
        print(f"Detection time budget: {DETECT_TIMEOUT_S}s (writes error-person to "
              f"person_detail.txt if nobody is confirmed in time)")
        
        try:
            while True:
                # ---- ADD: time-budget check, evaluated every raw frame so the
                # cutoff is enforced promptly rather than only at the (slower)
                # identification cadence. ----
                if time.time() - start_time >= DETECT_TIMEOUT_S:
                    timed_out = True
                    logger.warning(
                        "Detection timeout (%ss) reached with no confirmed match — "
                        "writing error-person", DETECT_TIMEOUT_S,
                    )
                    break

                frame = read_frame()
                if frame is None:
                    logger.error("Failed to read frame from camera (backend = %s)", backend)
                    # Treat a dead camera the same as a timeout for the
                    # purposes of person_detail.txt -- no confirmed detection
                    # happened, so the failure result still gets recorded.
                    timed_out = True
                    break

                frame_no += 1

                if frame_no % frame_skip == 0:
                    detection = detector.detect(frame)
                    if detection is not None:
                        last_bbox = detection.bbox
                        vec = embedder.embed(frame, detection)

                        if use_server:
                            name = server_client.identify(vec)
                            label = name if name else "Unknown"
                        else:
                            name, _, sim = diag_db.search(vec)
                            label = f"{name} ({sim:.2f})" if name else f"Unknown ({sim:.2f})"

                        # ---- ADD: update the consecutive-match streak ----
                        # Only a genuinely recognised name (not "Unknown")
                        # counts. A different name breaks the streak instead
                        # of accumulating across identities, so it can't
                        # confirm on a mix of two different people's frames.
                        if name:
                            if name == last_match_name:
                                match_streak += 1
                            else:
                                last_match_name = name
                                match_streak = 1
                        else:
                            last_match_name = None
                            match_streak = 0

                        logger.info(
                            "Match streak: %s x%d/%d",
                            last_match_name or "-", match_streak, CONFIRM_MATCHES,
                        )

                        if last_match_name and match_streak >= CONFIRM_MATCHES:
                            confirmed_name = last_match_name
                            print(f"\n>>> Confirmed: {confirmed_name} "
                                  f"({CONFIRM_MATCHES} consecutive matches) — exiting camera loop\n")
                            break
                    else:
                        last_bbox = None
                        label = ""
                        # A frame with no face detected also breaks the streak --
                        # otherwise someone could walk out of frame mid-streak
                        # and it would still be sitting there ready to resume.
                        last_match_name = None
                        match_streak = 0

                if last_bbox is not None:
                    x1, y1, x2, y2 = last_bbox
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    if label:
                        cv2.putText(frame, label, (x1, max(0, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

                cv2.imshow("Face Recognition", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
        finally:
            release_source()
            cv2.destroyAllWindows()
            if server_client:
                server_client.close()

            # ---- ADD: write the final result to person_detail.txt ----
            # Runs in `finally` so the file is written whichever way the loop
            # exited: confirmed match, timeout, or a camera read failure.
            # Only skipped if the user manually pressed 'q' before either a
            # confirmation or the timeout -- that's a deliberate abort, not a
            # detection result, so nothing is written in that case.
            if confirmed_name:
                _write_person_detail(person_detail_path, confirmed_name)
            elif timed_out:
                _write_person_detail(person_detail_path, "error-person")

        return confirmed_name

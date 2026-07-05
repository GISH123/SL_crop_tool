# -*- coding: utf-8 -*-
"""
Step3_YOLO11_HTTP_Predict.py

Batch-classify cropped card images by calling the same YOLO11 HTTP model API
used by pydealerLight BAC mode.

Workflow:
  cropped_images folder from Step 2
    -> call YOLO11 HTTP API for every image
    -> high-confidence images are copied/moved into original_dataset/0..52 or 99
    -> low-confidence / failed predictions go to original_dataset/confusing_label
    -> write _step3_yolo11_http_predict_report.csv

API request format is matched to pydealerLight's VideoManager._process_frame_bac:
  POST form fields:
    msg: Frame from client
    imgbase64: base64 encoded PNG image
    img_base64N: length of base64 string
    img_w: image width sent to engine
    img_h: image height sent to engine
    img_N: numpy image size

Expected API response fields are the same ones parsed by pydealerLight:
  nClass, nScore, group_text, onebox

Class routing:
  API class 0       -> output folder 0
  API class 1..52   -> output folder 1..52
  API class 53      -> output folder 99
  low confidence    -> confusing_label
  API/parse failure -> confusing_label
"""

from __future__ import annotations

import ast
import base64
import csv
import datetime as _dt
import json
import os
import queue
import re
import shutil
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_TITLE = "Step3 YOLO11 HTTP Predict"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
CLASS_FOLDERS = [str(i) for i in range(0, 53)] + ["99"]
CONFUSING_FOLDER = "confusing_label"
SETTINGS_FILENAME = "step3_yolo11_http_settings.json"
REPORT_FILENAME = "_step3_yolo11_http_predict_report.csv"

# Keep this default editable in the GUI. In most deployments you should paste the exact
# engine_api_url used by pydealerLight's videolist/config.
DEFAULT_API_URL = "http://127.0.0.1:5000/predict"


# ---------------------------------------------------------------------------
# Runtime logging helper: useful when packaged as windowed EXE.
# ---------------------------------------------------------------------------

def app_base_dir() -> Path:
    """Return the folder beside the EXE when packaged, or beside this py file."""
    try:
        import sys
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
    except Exception:
        pass
    return Path(__file__).resolve().parent


def runtime_log_path() -> Path:
    log_dir = app_base_dir() / "runtime_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    return log_dir / f"step3_yolo11_http_error_{ts}.txt"


def write_runtime_error(exc: BaseException) -> None:
    try:
        path = runtime_log_path()
        path.write_text(traceback.format_exc(), encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Image / HTTP / parsing utilities
# ---------------------------------------------------------------------------

@dataclass
class PreprocessResult:
    image_bgr: np.ndarray
    mode: str
    scale: float
    original_wh: Tuple[int, int]
    engine_wh: Tuple[int, int]


@dataclass
class PredictionResult:
    source_path: Path
    output_path: Optional[Path]
    routed_folder: str
    predicted_class: Optional[int]
    score: float
    label_text: str
    status: str
    error: str
    raw_response: str
    preprocess_mode: str
    original_wh: Tuple[int, int]
    engine_wh: Tuple[int, int]


def safe_filename_part(text: str, max_len: int = 160) -> str:
    text = str(text)
    # Keep common useful filename chars including Chinese chars, #, @, parentheses.
    text = re.sub(r'[<>:"/\\|?*\r\n\t]+', "_", text)
    text = text.strip().strip(".")
    if not text:
        text = "unnamed"
    return text[:max_len]


def read_image_bgr(path: Path) -> np.ndarray:
    """Read image using np.fromfile so Windows Chinese paths work."""
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        raise RuntimeError(f"empty image file: {path}")
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None or img.size == 0:
        raise RuntimeError(f"cv2 failed to read image: {path}")
    return img


def keep_ratio_resize_no_pad(roi: np.ndarray, target_w: int, target_h: int) -> Tuple[np.ndarray, float]:
    """Match pydealerLight BAC keep_ratio_no_pad preprocessing."""
    if roi is None or roi.size == 0:
        raise RuntimeError("empty image passed to keep_ratio_resize_no_pad")
    h, w = roi.shape[:2]
    target_w = max(1, int(target_w))
    target_h = max(1, int(target_h))
    scale = min(float(target_w) / float(max(1, w)), float(target_h) / float(max(1, h)))
    resized_w = max(1, int(round(float(w) * scale)))
    resized_h = max(1, int(round(float(h) * scale)))
    if resized_w != w or resized_h != h:
        resized = cv2.resize(roi, (resized_w, resized_h), interpolation=cv2.INTER_LINEAR)
    else:
        resized = roi.copy()
    return resized, float(scale)


def preprocess_for_engine(
    image_bgr: np.ndarray,
    resize_enable: bool,
    min_w: int,
    min_h: int,
    target_w: int,
    target_h: int,
) -> PreprocessResult:
    h, w = image_bgr.shape[:2]
    if resize_enable and (w < int(min_w) or h < int(min_h)):
        resized, scale = keep_ratio_resize_no_pad(image_bgr, int(target_w), int(target_h))
        eh, ew = resized.shape[:2]
        return PreprocessResult(
            image_bgr=resized,
            mode="keep_ratio_no_pad",
            scale=scale,
            original_wh=(int(w), int(h)),
            engine_wh=(int(ew), int(eh)),
        )
    return PreprocessResult(
        image_bgr=image_bgr.copy(),
        mode="identity",
        scale=1.0,
        original_wh=(int(w), int(h)),
        engine_wh=(int(w), int(h)),
    )


def encode_png_base64(image_bgr: np.ndarray) -> str:
    ok, buffer = cv2.imencode(
        ".png",
        image_bgr,
        [int(cv2.IMWRITE_PNG_COMPRESSION), 1],
    )
    if not ok:
        raise RuntimeError("cv2.imencode(.png) failed")
    return base64.b64encode(buffer).decode("utf-8")


def post_engine(api_url: str, image_bgr: np.ndarray, timeout_s: float = 15.0) -> Dict[str, Any]:
    """POST image to YOLO11 engine using stdlib urllib only."""
    b64 = encode_png_base64(image_bgr)
    payload = {
        "msg": "Frame from client",
        "imgbase64": b64,
        "img_base64N": len(b64),
        "img_w": int(image_bgr.shape[1]),
        "img_h": int(image_bgr.shape[0]),
        "img_N": int(image_bgr.size),
    }
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(
        api_url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=float(timeout_s)) as resp:
        raw = resp.read().decode("utf-8", errors="replace").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        try:
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    raise RuntimeError(f"API response is not JSON/dict: {raw[:500]}")


def _as_list(value: Any) -> List[Any]:
    """Parse strings/lists from API fields into a flat-ish list."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        if len(value) == 1 and isinstance(value[0], (list, tuple)):
            return list(value[0])
        return list(value)
    s = str(value).strip()
    if not s:
        return []
    try:
        parsed = ast.literal_eval(s)
        if isinstance(parsed, (list, tuple)):
            if len(parsed) == 1 and isinstance(parsed[0], (list, tuple)):
                return list(parsed[0])
            return list(parsed)
    except Exception:
        pass
    # pydealerLight handles first item separated by ; or ,.
    if ";" in s:
        s = s.split(";")[0].strip()
    if "," in s:
        return [x.strip() for x in s.split(",") if x.strip()]
    return [s]


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(float(str(value).strip()))
    except Exception:
        return None


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(str(value).strip())
    except Exception:
        return None


def _label_text(value: Any) -> str:
    vals = _as_list(value)
    if not vals:
        return ""
    first = vals[0]
    if isinstance(first, (list, tuple)) and first:
        first = first[0]
    s = str(first).strip().strip("[]").replace("'", "").replace('"', "").strip()
    if "," in s:
        s = s.split(",")[0].strip()
    return s


def parse_engine_prediction(api_response: Dict[str, Any]) -> Tuple[Optional[int], float, str]:
    """Return (api_class, score, label_text), matched to pydealerLight BAC parser."""
    if not isinstance(api_response, dict) or not api_response:
        return None, 0.0, ""

    cls_vals = _as_list(api_response.get("nClass"))
    score_vals = _as_list(api_response.get("nScore"))

    # In normal BAC use there is one card. If multiple are returned, use the first
    # model result to match pydealerLight's _first_scalar behavior.
    api_class = _to_int(cls_vals[0]) if cls_vals else None
    score = _to_float(score_vals[0]) if score_vals else None
    label = _label_text(api_response.get("group_text"))

    return api_class, float(score if score is not None else 0.0), label


def api_class_to_dataset_folder(api_class: Optional[int], score: float, threshold: float) -> Tuple[str, str]:
    """Return (folder, status)."""
    if api_class is None:
        return CONFUSING_FOLDER, "parse_failed"
    if score < float(threshold):
        return CONFUSING_FOLDER, "low_confidence"
    if 0 <= int(api_class) <= 52:
        return str(int(api_class)), "ok"
    if int(api_class) == 53:
        return "99", "ok_zero_card_to_99"
    return CONFUSING_FOLDER, "unknown_class"


def api_class_description(api_class: Optional[int]) -> Tuple[Optional[int], str, str]:
    """Return (dealer_id, suit_key, rank_label) for filename, matching pydealerLight naming."""
    if api_class is None:
        return None, "UNK", "UNK"
    try:
        api_class = int(api_class)
    except Exception:
        return None, "UNK", "UNK"
    if api_class in (0, 53):
        return None, "special", str(api_class)
    if not (1 <= api_class <= 52):
        return None, "UNK", str(api_class)

    suit_idx = (api_class - 1) // 13
    rank = ((api_class - 1) % 13) + 1
    suit_key = ["mei", "fang", "hong", "hei"][suit_idx]
    base_off = {"mei": 0, "fang": 16, "hong": 48, "hei": 32}[suit_key]
    dealer_id = base_off + rank
    rank_label_map = {1: "A", 11: "J", 12: "Q", 13: "K"}
    rank_label = rank_label_map.get(rank, str(rank))
    return dealer_id, suit_key, rank_label


def build_output_filename(src: Path, api_class: Optional[int], score: float, status: str) -> str:
    stem = safe_filename_part(src.stem, 120)
    ext = src.suffix.lower() if src.suffix.lower() in IMAGE_EXTENSIONS else ".jpg"
    if api_class is None:
        suffix = f"_pred_ERR_score_{float(score):0.4f}_{status}"
    else:
        dealer_id, suit_key, rank_label = api_class_description(api_class)
        if dealer_id is None:
            suffix = f"_@{int(api_class)}({float(score):0.4f})_{status}"
        else:
            suffix = f"_#{dealer_id}_{suit_key}_{rank_label}@{int(api_class)}({float(score):0.4f})_{status}"
    return safe_filename_part(stem + suffix, 220) + ext


def ensure_unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for i in range(1, 10000):
        candidate = parent / f"{stem}_dup{i}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"cannot create unique destination name for {path}")


def iter_image_files(root: Path, recursive: bool) -> List[Path]:
    if recursive:
        files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS]
    else:
        files = [p for p in root.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS]
    return sorted(files, key=lambda p: str(p).lower())


def ensure_dataset_folders(dataset_root: Path) -> None:
    dataset_root.mkdir(parents=True, exist_ok=True)
    for name in CLASS_FOLDERS:
        (dataset_root / name).mkdir(parents=True, exist_ok=True)
    (dataset_root / CONFUSING_FOLDER).mkdir(parents=True, exist_ok=True)


def write_report_header(report_path: Path) -> None:
    if report_path.exists():
        return
    with report_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp",
            "source_path",
            "output_path",
            "routed_folder",
            "predicted_class",
            "score",
            "label_text",
            "status",
            "error",
            "preprocess_mode",
            "original_w",
            "original_h",
            "engine_w",
            "engine_h",
            "raw_response",
        ])


def append_report(report_path: Path, result: PredictionResult) -> None:
    with report_path.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            str(result.source_path),
            str(result.output_path) if result.output_path else "",
            result.routed_folder,
            "" if result.predicted_class is None else int(result.predicted_class),
            f"{float(result.score):0.6f}",
            result.label_text,
            result.status,
            result.error,
            result.preprocess_mode,
            result.original_wh[0],
            result.original_wh[1],
            result.engine_wh[0],
            result.engine_wh[1],
            result.raw_response,
        ])


@dataclass
class Step3Settings:
    input_dir: Path
    output_dir: Path
    api_url: str
    threshold: float
    mode: str
    recursive: bool
    resize_enable: bool
    min_w: int
    min_h: int
    target_w: int
    target_h: int
    timeout_s: float


class Step3Worker:
    def __init__(self, settings: Step3Settings, event_queue: queue.Queue, stop_event: threading.Event):
        self.settings = settings
        self.event_queue = event_queue
        self.stop_event = stop_event

    def log(self, text: str) -> None:
        self.event_queue.put(("log", text))

    def progress(self, done: int, total: int, saved: int, confusing: int, failed: int, start_ts: float) -> None:
        elapsed = time.time() - start_ts
        eta = None
        if done > 0 and total > done:
            eta = elapsed / done * (total - done)
        self.event_queue.put(("progress", {
            "done": done,
            "total": total,
            "saved": saved,
            "confusing": confusing,
            "failed": failed,
            "elapsed": elapsed,
            "eta": eta,
        }))

    def run(self) -> None:
        s = self.settings
        start_ts = time.time()
        done = saved = confusing = failed = 0
        try:
            ensure_dataset_folders(s.output_dir)
            report_path = s.output_dir / REPORT_FILENAME
            write_report_header(report_path)
            files = iter_image_files(s.input_dir, s.recursive)
            total = len(files)
            self.log(f"Found {total} image(s).")
            if total == 0:
                self.event_queue.put(("done", {"saved": 0, "confusing": 0, "failed": 0}))
                return
            self.progress(0, total, saved, confusing, failed, start_ts)

            for src in files:
                if self.stop_event.is_set():
                    self.log("Stopped by user.")
                    break
                done += 1
                result = self.process_one(src)
                append_report(report_path, result)
                if result.status.startswith("ok"):
                    saved += 1
                elif result.routed_folder == CONFUSING_FOLDER:
                    confusing += 1
                    if result.error:
                        failed += 1
                else:
                    failed += 1
                self.log(f"[{done}/{total}] {src.name} -> {result.routed_folder} | class={result.predicted_class} score={result.score:.4f} status={result.status}")
                self.progress(done, total, saved, confusing, failed, start_ts)

            self.event_queue.put(("done", {"saved": saved, "confusing": confusing, "failed": failed}))
        except Exception as exc:
            write_runtime_error(exc)
            self.event_queue.put(("error", traceback.format_exc()))

    def process_one(self, src: Path) -> PredictionResult:
        s = self.settings
        raw_response_text = ""
        preprocess = PreprocessResult(np.zeros((1, 1, 3), dtype=np.uint8), "unknown", 1.0, (0, 0), (0, 0))
        api_class: Optional[int] = None
        score = 0.0
        label = ""
        error = ""
        try:
            img = read_image_bgr(src)
            preprocess = preprocess_for_engine(
                img,
                resize_enable=s.resize_enable,
                min_w=s.min_w,
                min_h=s.min_h,
                target_w=s.target_w,
                target_h=s.target_h,
            )
            api = post_engine(s.api_url, preprocess.image_bgr, timeout_s=s.timeout_s)
            raw_response_text = json.dumps(api, ensure_ascii=False)
            api_class, score, label = parse_engine_prediction(api)
            folder, status = api_class_to_dataset_folder(api_class, score, s.threshold)
        except Exception as exc:
            error = repr(exc)
            folder = CONFUSING_FOLDER
            status = "api_or_processing_error"
            raw_response_text = raw_response_text or ""

        dest_dir = s.output_dir / folder
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_name = build_output_filename(src, api_class, score, status)
        dest = ensure_unique_path(dest_dir / dest_name)

        try:
            if s.mode == "move":
                shutil.move(str(src), str(dest))
            else:
                shutil.copy2(str(src), str(dest))
        except Exception as copy_exc:
            error = (error + " | " if error else "") + f"copy/move failed: {copy_exc!r}"
            status = "copy_move_failed"
            dest = None

        return PredictionResult(
            source_path=src,
            output_path=dest,
            routed_folder=folder,
            predicted_class=api_class,
            score=float(score),
            label_text=label,
            status=status,
            error=error,
            raw_response=raw_response_text,
            preprocess_mode=preprocess.mode,
            original_wh=preprocess.original_wh,
            engine_wh=preprocess.engine_wh,
        )


# ---------------------------------------------------------------------------
# Tkinter GUI
# ---------------------------------------------------------------------------

class Step3App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("980x720")
        self.event_queue: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker_thread: Optional[threading.Thread] = None

        self.var_input = tk.StringVar(value="")
        self.var_output = tk.StringVar(value=str(app_base_dir() / "original_dataset_yolo11_http"))
        self.var_api_url = tk.StringVar(value=DEFAULT_API_URL)
        self.var_threshold = tk.StringVar(value="0.80")
        self.var_mode = tk.StringVar(value="copy")
        self.var_recursive = tk.BooleanVar(value=False)
        self.var_resize_enable = tk.BooleanVar(value=True)
        self.var_min_w = tk.StringVar(value="320")
        self.var_min_h = tk.StringVar(value="320")
        self.var_target_w = tk.StringVar(value="320")
        self.var_target_h = tk.StringVar(value="320")
        self.var_timeout = tk.StringVar(value="15")

        self.progress_var = tk.DoubleVar(value=0.0)
        self.status_var = tk.StringVar(value="Ready.")
        self.detail_var = tk.StringVar(value="")

        self.load_settings()
        self.build_ui()
        self.root.after(100, self.poll_events)

    def settings_path(self) -> Path:
        return app_base_dir() / SETTINGS_FILENAME

    def load_settings(self) -> None:
        path = self.settings_path()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.var_input.set(data.get("input_dir", self.var_input.get()))
            self.var_output.set(data.get("output_dir", self.var_output.get()))
            self.var_api_url.set(data.get("api_url", self.var_api_url.get()))
            self.var_threshold.set(str(data.get("threshold", self.var_threshold.get())))
            self.var_mode.set(data.get("mode", self.var_mode.get()))
            self.var_recursive.set(bool(data.get("recursive", self.var_recursive.get())))
            self.var_resize_enable.set(bool(data.get("resize_enable", self.var_resize_enable.get())))
            self.var_min_w.set(str(data.get("min_w", self.var_min_w.get())))
            self.var_min_h.set(str(data.get("min_h", self.var_min_h.get())))
            self.var_target_w.set(str(data.get("target_w", self.var_target_w.get())))
            self.var_target_h.set(str(data.get("target_h", self.var_target_h.get())))
            self.var_timeout.set(str(data.get("timeout_s", self.var_timeout.get())))
        except Exception:
            pass

    def save_settings(self) -> None:
        try:
            data = {
                "input_dir": self.var_input.get(),
                "output_dir": self.var_output.get(),
                "api_url": self.var_api_url.get(),
                "threshold": self.var_threshold.get(),
                "mode": self.var_mode.get(),
                "recursive": self.var_recursive.get(),
                "resize_enable": self.var_resize_enable.get(),
                "min_w": self.var_min_w.get(),
                "min_h": self.var_min_h.get(),
                "target_w": self.var_target_w.get(),
                "target_h": self.var_target_h.get(),
                "timeout_s": self.var_timeout.get(),
            }
            self.settings_path().write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(1, weight=1)

        r = 0
        ttk.Label(outer, text="Input cropped image folder:").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(outer, textvariable=self.var_input).grid(row=r, column=1, sticky="ew", pady=4)
        ttk.Button(outer, text="Browse", command=self.browse_input).grid(row=r, column=2, padx=4, pady=4)
        r += 1

        ttk.Label(outer, text="Output original_dataset folder:").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(outer, textvariable=self.var_output).grid(row=r, column=1, sticky="ew", pady=4)
        ttk.Button(outer, text="Browse/Create", command=self.browse_output).grid(row=r, column=2, padx=4, pady=4)
        r += 1

        ttk.Label(outer, text="YOLO11 HTTP API URL:").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(outer, textvariable=self.var_api_url).grid(row=r, column=1, sticky="ew", pady=4)
        ttk.Button(outer, text="Test First Image", command=self.test_first_image).grid(row=r, column=2, padx=4, pady=4)
        r += 1

        options = ttk.LabelFrame(outer, text="Options")
        options.grid(row=r, column=0, columnspan=3, sticky="ew", pady=8)
        for c in range(10):
            options.columnconfigure(c, weight=0)
        options.columnconfigure(9, weight=1)

        ttk.Label(options, text="Score threshold:").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        ttk.Entry(options, textvariable=self.var_threshold, width=8).grid(row=0, column=1, sticky="w", padx=4, pady=4)

        ttk.Radiobutton(options, text="Copy", value="copy", variable=self.var_mode).grid(row=0, column=2, sticky="w", padx=8)
        ttk.Radiobutton(options, text="Move", value="move", variable=self.var_mode).grid(row=0, column=3, sticky="w", padx=8)
        ttk.Checkbutton(options, text="Recursive", variable=self.var_recursive).grid(row=0, column=4, sticky="w", padx=8)

        ttk.Label(options, text="Timeout(s):").grid(row=0, column=5, sticky="w", padx=4)
        ttk.Entry(options, textvariable=self.var_timeout, width=6).grid(row=0, column=6, sticky="w", padx=4)

        ttk.Checkbutton(options, text="BAC keep-ratio resize when image smaller than min", variable=self.var_resize_enable).grid(row=1, column=0, columnspan=4, sticky="w", padx=4, pady=4)
        ttk.Label(options, text="min W/H:").grid(row=1, column=4, sticky="e")
        ttk.Entry(options, textvariable=self.var_min_w, width=6).grid(row=1, column=5, sticky="w", padx=2)
        ttk.Entry(options, textvariable=self.var_min_h, width=6).grid(row=1, column=6, sticky="w", padx=2)
        ttk.Label(options, text="target W/H:").grid(row=1, column=7, sticky="e")
        ttk.Entry(options, textvariable=self.var_target_w, width=6).grid(row=1, column=8, sticky="w", padx=2)
        ttk.Entry(options, textvariable=self.var_target_h, width=6).grid(row=1, column=9, sticky="w", padx=2)
        r += 1

        buttons = ttk.Frame(outer)
        buttons.grid(row=r, column=0, columnspan=3, sticky="ew", pady=6)
        ttk.Button(buttons, text="Start Predict && Classify", command=self.start).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="Stop", command=self.stop).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="Open Output Folder", command=self.open_output_folder).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="Save Settings", command=self.save_settings_clicked).pack(side=tk.LEFT, padx=4)
        r += 1

        ttk.Progressbar(outer, variable=self.progress_var, maximum=100).grid(row=r, column=0, columnspan=3, sticky="ew", pady=4)
        r += 1
        ttk.Label(outer, textvariable=self.status_var).grid(row=r, column=0, columnspan=3, sticky="w", pady=2)
        r += 1
        ttk.Label(outer, textvariable=self.detail_var).grid(row=r, column=0, columnspan=3, sticky="w", pady=2)
        r += 1

        help_text = (
            "Routing rule: class 0 -> folder 0, class 1~52 -> same folder, class 53 -> folder 99, "
            "score below threshold or API failure -> confusing_label."
        )
        ttk.Label(outer, text=help_text, foreground="gray").grid(row=r, column=0, columnspan=3, sticky="w", pady=4)
        r += 1

        log_frame = ttk.LabelFrame(outer, text="Log")
        log_frame.grid(row=r, column=0, columnspan=3, sticky="nsew", pady=6)
        outer.rowconfigure(r, weight=1)
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log_text = tk.Text(log_frame, height=18, wrap="none")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=yscroll.set)

    def browse_input(self) -> None:
        path = filedialog.askdirectory(title="Select Step 2 cropped image folder")
        if path:
            self.var_input.set(path)

    def browse_output(self) -> None:
        path = filedialog.askdirectory(title="Select or create original_dataset output folder")
        if path:
            self.var_output.set(path)

    def get_settings(self) -> Step3Settings:
        input_dir = Path(self.var_input.get().strip()).resolve()
        output_dir = Path(self.var_output.get().strip()).resolve()
        api_url = self.var_api_url.get().strip()
        if not input_dir.exists() or not input_dir.is_dir():
            raise ValueError("Input image folder does not exist.")
        if not api_url:
            raise ValueError("YOLO11 HTTP API URL is empty.")
        threshold = float(self.var_threshold.get().strip())
        if not (0.0 <= threshold <= 1.0):
            raise ValueError("Score threshold must be between 0 and 1.")
        return Step3Settings(
            input_dir=input_dir,
            output_dir=output_dir,
            api_url=api_url,
            threshold=threshold,
            mode=self.var_mode.get().strip(),
            recursive=bool(self.var_recursive.get()),
            resize_enable=bool(self.var_resize_enable.get()),
            min_w=int(self.var_min_w.get().strip()),
            min_h=int(self.var_min_h.get().strip()),
            target_w=int(self.var_target_w.get().strip()),
            target_h=int(self.var_target_h.get().strip()),
            timeout_s=float(self.var_timeout.get().strip()),
        )

    def start(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo(APP_TITLE, "Prediction is already running.")
            return
        try:
            settings = self.get_settings()
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        self.save_settings()
        self.stop_event.clear()
        self.progress_var.set(0)
        self.status_var.set("Starting...")
        self.detail_var.set("")
        self.log_text.delete("1.0", tk.END)
        self.log(f"Input: {settings.input_dir}")
        self.log(f"Output: {settings.output_dir}")
        self.log(f"API: {settings.api_url}")
        self.log(f"Threshold: {settings.threshold:.4f}; mode={settings.mode}; recursive={settings.recursive}")
        worker = Step3Worker(settings, self.event_queue, self.stop_event)
        self.worker_thread = threading.Thread(target=worker.run, daemon=True)
        self.worker_thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.status_var.set("Stopping after current image...")

    def save_settings_clicked(self) -> None:
        self.save_settings()
        messagebox.showinfo(APP_TITLE, f"Settings saved to:\n{self.settings_path()}")

    def open_output_folder(self) -> None:
        path = Path(self.var_output.get().strip())
        path.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def test_first_image(self) -> None:
        try:
            settings = self.get_settings()
            files = iter_image_files(settings.input_dir, settings.recursive)
            if not files:
                messagebox.showwarning(APP_TITLE, "No image found in input folder.")
                return
            src = files[0]
            self.log(f"Testing first image: {src.name}")
            img = read_image_bgr(src)
            prep = preprocess_for_engine(
                img,
                settings.resize_enable,
                settings.min_w,
                settings.min_h,
                settings.target_w,
                settings.target_h,
            )
            api = post_engine(settings.api_url, prep.image_bgr, timeout_s=settings.timeout_s)
            cls, score, label = parse_engine_prediction(api)
            folder, status = api_class_to_dataset_folder(cls, score, settings.threshold)
            msg = (
                f"Image: {src.name}\n"
                f"API class: {cls}\n"
                f"Score: {score:.4f}\n"
                f"Label text: {label}\n"
                f"Route folder: {folder}\n"
                f"Status: {status}\n\n"
                f"Raw response:\n{json.dumps(api, ensure_ascii=False, indent=2)[:2000]}"
            )
            self.log(msg)
            messagebox.showinfo(APP_TITLE, msg[:3500])
        except Exception as exc:
            write_runtime_error(exc)
            self.log(traceback.format_exc())
            messagebox.showerror(APP_TITLE, str(exc))

    def log(self, text: str) -> None:
        ts = _dt.datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"{ts} {text}\n")
        self.log_text.see(tk.END)

    def poll_events(self) -> None:
        try:
            while True:
                kind, payload = self.event_queue.get_nowait()
                if kind == "log":
                    self.log(str(payload))
                elif kind == "progress":
                    total = max(1, int(payload["total"]))
                    done = int(payload["done"])
                    pct = done / total * 100.0
                    self.progress_var.set(pct)
                    self.status_var.set(f"Progress: {done}/{total} ({pct:.1f}%)")
                    eta = payload.get("eta")
                    eta_text = "--" if eta is None else self.format_seconds(float(eta))
                    elapsed_text = self.format_seconds(float(payload.get("elapsed", 0.0)))
                    self.detail_var.set(
                        f"saved={payload['saved']} | confusing={payload['confusing']} | failed={payload['failed']} | elapsed={elapsed_text} | ETA={eta_text}"
                    )
                elif kind == "done":
                    self.status_var.set("Done.")
                    self.log(f"ALL DONE. saved={payload['saved']}, confusing={payload['confusing']}, failed={payload['failed']}")
                    messagebox.showinfo(APP_TITLE, f"Done.\nSaved: {payload['saved']}\nConfusing: {payload['confusing']}\nFailed: {payload['failed']}")
                elif kind == "error":
                    self.status_var.set("Error.")
                    self.log(str(payload))
                    messagebox.showerror(APP_TITLE, str(payload)[:3500])
        except queue.Empty:
            pass
        self.root.after(100, self.poll_events)

    @staticmethod
    def format_seconds(seconds: float) -> str:
        seconds = max(0, int(seconds))
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        if h:
            return f"{h}h {m}m {s}s"
        if m:
            return f"{m}m {s}s"
        return f"{s}s"


def main() -> None:
    root = tk.Tk()
    app = Step3App(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        write_runtime_error(exc)
        raise

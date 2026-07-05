"""
Step2_Crop_by_annotation.py

EXE-friendly version.

Purpose:
    Select a Step 1 XML annotation and a video file, then crop the video regions
    defined by the XML. Each saved crop also gets a same-name LabelMe JSON file.

Main EXE workflow:
    1. Double-click Step2_Crop_By_Annotation.exe.
    2. Select video file.
    3. Select Step 1 XML annotation file.
    4. Select output root folder.
    5. Click Start Crop.

Output:
    output_root/
      cropped_images_<video_stem>_<YYYYMMDD>/
        <date>_card_1_frame_xxx.jpg
        <date>_card_1_frame_xxx.json
        ...

Optional:
    The tool can also create an empty original_dataset folder with 0~52 and 99
    class subfolders, so you can manually classify images into that structure.
"""

from __future__ import annotations

import base64
import json
import os
import threading
import time
import traceback
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import xml.etree.ElementTree as ET

import cv2


# ============================================================
# Default settings
# ============================================================

DEFAULT_LABELME_LABEL = "1"
DEFAULT_INCLUDE_IMAGE_DATA = False
DEFAULT_OUTPUT_IMAGE_WIDTH = 150
DEFAULT_OUTPUT_IMAGE_HEIGHT = 100
DEFAULT_LABELME_BOX_INSET = 10
DEFAULT_LABELME_VERSION = "5.4.0a0"
DEFAULT_CROP_EVERY_SECONDS = 1.0
DEFAULT_FAST_FORWARD_SECONDS = 5

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}



# ============================================================
# EXE runtime error logger
# ============================================================
def _get_runtime_base_dir():
    import sys
    from pathlib import Path
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _write_runtime_log(step_name: str, text: str) -> str:
    import time
    log_dir = _get_runtime_base_dir() / "runtime_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{step_name}_{time.strftime('%Y%m%d_%H%M%S')}.txt"
    log_path.write_text(text, encoding="utf-8")
    return str(log_path)


def _handle_fatal_exception(step_name: str):
    import traceback
    text = traceback.format_exc()
    log_path = _write_runtime_log(step_name, text)
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            f"{step_name} crashed",
            f"{step_name} crashed.\n\n"
            f"Error log saved to:\n{log_path}\n\n"
            "Please send this log to GISH."
        )
        root.destroy()
    except Exception:
        pass
    raise

@dataclass
class CropRegion:
    name: str
    x_min: int
    y_min: int
    x_max: int
    y_max: int


@dataclass
class CropSettings:
    video_path: Path
    xml_path: Path
    output_root: Path
    crop_every_seconds: float
    output_width: int
    output_height: int
    labelme_label: str
    labelme_box_inset: int
    include_image_data: bool
    draw_preview: bool
    threshold_value: float | None
    ref_image_path: Path | None
    create_dataset_folders: bool
    dataset_folder_name: str


def parse_xml_to_crop_regions(xml_file: Path) -> tuple[list[CropRegion], float]:
    tree = ET.parse(str(xml_file))
    root = tree.getroot()

    size_element = root.find("size")
    tilt_angle = 0.0
    if size_element is not None:
        tilt_elem = size_element.find("tilt_angle")
        if tilt_elem is not None and tilt_elem.text not in (None, ""):
            tilt_angle = float(tilt_elem.text)

    crop_regions: list[CropRegion] = []
    for obj in root.findall("object"):
        name_elem = obj.find("name")
        bndbox = obj.find("bndbox")
        if bndbox is None:
            continue

        name = name_elem.text.strip() if name_elem is not None and name_elem.text else f"card_{len(crop_regions) + 1}"
        region = CropRegion(
            name=name,
            x_min=int(float(bndbox.findtext("xmin", "0"))),
            y_min=int(float(bndbox.findtext("ymin", "0"))),
            x_max=int(float(bndbox.findtext("xmax", "0"))),
            y_max=int(float(bndbox.findtext("ymax", "0"))),
        )
        crop_regions.append(region)

    if not crop_regions:
        raise ValueError(f"No crop regions found in XML: {xml_file}")

    return crop_regions, tilt_angle


def rotate_bound(frame, angle: float):
    """Rotate image with expanded canvas, matching Step 1 annotation behavior."""
    if angle == 0:
        return frame

    h, w = frame.shape[:2]
    c_x, c_y = w // 2, h // 2

    rotation_mat = cv2.getRotationMatrix2D((c_x, c_y), angle, 1.0)
    abs_cos = abs(rotation_mat[0, 0])
    abs_sin = abs(rotation_mat[0, 1])

    new_w = int(h * abs_sin + w * abs_cos)
    new_h = int(h * abs_cos + w * abs_sin)

    rotation_mat[0, 2] += (new_w / 2) - c_x
    rotation_mat[1, 2] += (new_h / 2) - c_y

    return cv2.warpAffine(frame, rotation_mat, (new_w, new_h))


def resize_keep_ratio_center_pad(image, target_width: int, target_height: int):
    """Resize with aspect ratio preserved and center padding using edge replication."""
    if image is None or image.size == 0:
        raise ValueError("Invalid empty crop image, cannot resize for LabelMe output.")

    original_height, original_width = image.shape[:2]
    if original_width <= 0 or original_height <= 0:
        raise ValueError(f"Invalid crop image size: {original_width}x{original_height}")

    scale = min(target_width / original_width, target_height / original_height)
    new_width = max(1, min(target_width, int(round(original_width * scale))))
    new_height = max(1, min(target_height, int(round(original_height * scale))))

    interpolation = cv2.INTER_CUBIC if scale >= 1 else cv2.INTER_AREA
    resized = cv2.resize(image, (new_width, new_height), interpolation=interpolation)

    total_pad_x = target_width - new_width
    total_pad_y = target_height - new_height

    pad_left = total_pad_x // 2
    pad_right = total_pad_x - pad_left
    pad_top = total_pad_y // 2
    pad_bottom = total_pad_y - pad_top

    padded = cv2.copyMakeBorder(
        resized,
        pad_top,
        pad_bottom,
        pad_left,
        pad_right,
        borderType=cv2.BORDER_REPLICATE,
    )

    final_height, final_width = padded.shape[:2]
    if final_width != target_width or final_height != target_height:
        raise RuntimeError(
            f"Unexpected padded image size: {final_width}x{final_height}, "
            f"expected {target_width}x{target_height}"
        )

    return padded


def get_labelme_inset_points(image_width: int, image_height: int, inset: int):
    width = int(image_width)
    height = int(image_height)
    inset = int(inset)

    if width <= 1 or height <= 1:
        raise ValueError(f"Invalid image size for LabelMe JSON: {width}x{height}")
    if inset < 0:
        raise ValueError(f"LabelMe inset must be >= 0, got {inset}")

    if width <= inset * 2 or height <= inset * 2:
        # Very small images: use whole image instead of failing.
        return [[0.0, 0.0], [float(width - 1), float(height - 1)]]

    return [[float(inset), float(inset)], [float(width - inset), float(height - inset)]]


def build_labelme_json(
    image_path: Path,
    image_width: int,
    image_height: int,
    label: str,
    inset: int,
    include_image_data: bool,
):
    image_data = None
    if include_image_data:
        image_data = base64.b64encode(image_path.read_bytes()).decode("utf-8")

    return {
        "version": DEFAULT_LABELME_VERSION,
        "flags": {},
        "shapes": [
            {
                "label": str(label),
                "points": get_labelme_inset_points(image_width, image_height, inset),
                "group_id": None,
                "description": "",
                "shape_type": "rectangle",
                "flags": {},
                "mask": None,
            }
        ],
        "imagePath": image_path.name,
        "imageData": image_data,
        "imageHeight": int(image_height),
        "imageWidth": int(image_width),
    }


def save_crop_and_labelme_json(image_path: Path, cropped_image, settings: CropSettings) -> None:
    output_image = resize_keep_ratio_center_pad(
        cropped_image,
        target_width=settings.output_width,
        target_height=settings.output_height,
    )

    image_path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(image_path), output_image)
    if not ok:
        raise RuntimeError(f"Failed to write cropped image: {image_path}")

    image_height, image_width = output_image.shape[:2]
    labelme_json = build_labelme_json(
        image_path=image_path,
        image_width=image_width,
        image_height=image_height,
        label=settings.labelme_label,
        inset=settings.labelme_box_inset,
        include_image_data=settings.include_image_data,
    )

    json_path = image_path.with_suffix(".json")
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(labelme_json, f, ensure_ascii=False, indent=2)


def safe_crop(frame, region: CropRegion):
    h, w = frame.shape[:2]
    x_min = max(0, min(w, region.x_min))
    y_min = max(0, min(h, region.y_min))
    x_max = max(0, min(w, region.x_max))
    y_max = max(0, min(h, region.y_max))

    if x_max <= x_min or y_max <= y_min:
        raise ValueError(
            f"Invalid crop after clamping for {region.name}: "
            f"({region.x_min},{region.y_min})-({region.x_max},{region.y_max}), frame={w}x{h}"
        )

    return frame[y_min:y_max, x_min:x_max]


def create_original_dataset_folders(output_root: Path, dataset_folder_name: str) -> Path:
    dataset_root = output_root / dataset_folder_name
    dataset_root.mkdir(parents=True, exist_ok=True)

    for class_id in list(range(0, 53)) + [99]:
        (dataset_root / str(class_id)).mkdir(parents=True, exist_ok=True)

    return dataset_root


def crop_video(settings: CropSettings, log, progress_callback=None) -> None:
    crop_regions, tilt_angle = parse_xml_to_crop_regions(settings.xml_path)

    log(f"[XML] {settings.xml_path}")
    log(f"[VIDEO] {settings.video_path}")
    log(f"[REGIONS] {len(crop_regions)}")
    log(f"[TILT] {tilt_angle}")

    cap = cv2.VideoCapture(str(settings.video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video file: {settings.video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step_frames = max(1, int(round(settings.crop_every_seconds * fps)))

    timestr = time.strftime("%Y%m%d")
    save_dir = settings.output_root / f"cropped_images_{settings.video_path.stem}_{timestr}"
    save_dir.mkdir(parents=True, exist_ok=True)
    log(f"[OUTPUT] {save_dir}")

    if settings.create_dataset_folders:
        dataset_root = create_original_dataset_folders(settings.output_root, settings.dataset_folder_name)
        log(f"[DATASET FOLDERS] {dataset_root} / 0~52 and 99")

    ref_gray = None
    if settings.threshold_value is not None:
        if settings.ref_image_path is None:
            raise ValueError("threshold_value is set, but ref_image_path is empty.")
        ref_img = cv2.imread(str(settings.ref_image_path))
        if ref_img is None:
            raise ValueError(f"Cannot read reference image: {settings.ref_image_path}")
        ref_gray = cv2.cvtColor(ref_img, cv2.COLOR_BGR2GRAY)
        log(f"[THRESHOLD] enabled, value={settings.threshold_value}, ref={settings.ref_image_path}")
    else:
        log("[THRESHOLD] disabled")

    saved_count = 0
    skipped_count = 0
    frame_index = 0
    processed_steps = 0
    total_steps = 0
    if total_frames > 0:
        total_steps = max(1, (total_frames + step_frames - 1) // step_frames)
    start_time = time.time()

    if progress_callback is not None:
        progress_callback(
            processed_steps=0,
            total_steps=total_steps,
            frame_index=0,
            total_frames=total_frames,
            saved_count=saved_count,
            skipped_count=skipped_count,
            elapsed_seconds=0.0,
        )

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame_index = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
            if tilt_angle != 0:
                frame = rotate_bound(frame, tilt_angle)

            gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            for region in crop_regions:
                try:
                    gray_crop = safe_crop(gray_frame, region)

                    if ref_gray is not None and settings.threshold_value is not None:
                        resized_ref = cv2.resize(ref_gray, (gray_crop.shape[1], gray_crop.shape[0]))
                        diff = cv2.absdiff(gray_crop, resized_ref)
                        mean_intensity_diff = float(diff.mean())
                        if mean_intensity_diff <= settings.threshold_value:
                            skipped_count += 1
                            continue

                    color_crop = safe_crop(frame, region)
                    image_path = save_dir / f"{timestr}_{region.name}_frame_{frame_index}.jpg"
                    save_crop_and_labelme_json(image_path, color_crop, settings)
                    saved_count += 1

                    if settings.draw_preview:
                        cv2.rectangle(
                            frame,
                            (region.x_min - 3, region.y_min - 3),
                            (region.x_max + 3, region.y_max + 3),
                            (0, 255, 0),
                            2,
                        )

                except Exception as exc:
                    skipped_count += 1
                    log(f"[WARN] frame={frame_index}, region={region.name}: {exc}")

            processed_steps += 1
            if progress_callback is not None:
                progress_callback(
                    processed_steps=processed_steps,
                    total_steps=total_steps,
                    frame_index=frame_index,
                    total_frames=total_frames,
                    saved_count=saved_count,
                    skipped_count=skipped_count,
                    elapsed_seconds=time.time() - start_time,
                )

            if settings.draw_preview:
                cv2.imshow("Step2 Preview - press q to stop", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    log("[STOP] user pressed q")
                    break

            if frame_index % max(step_frames * 10, 1) == 0:
                if total_frames > 0:
                    log(f"[PROGRESS] frame={frame_index}/{total_frames}, saved={saved_count}, skipped={skipped_count}")
                else:
                    log(f"[PROGRESS] frame={frame_index}, saved={saved_count}, skipped={skipped_count}")

            next_frame = frame_index + step_frames - 1
            if total_frames > 0 and next_frame >= total_frames:
                break
            cap.set(cv2.CAP_PROP_POS_FRAMES, next_frame)

    finally:
        cap.release()
        cv2.destroyAllWindows()

    if progress_callback is not None:
        progress_callback(
            processed_steps=total_steps if total_steps > 0 else processed_steps,
            total_steps=total_steps,
            frame_index=total_frames if total_frames > 0 else frame_index,
            total_frames=total_frames,
            saved_count=saved_count,
            skipped_count=skipped_count,
            elapsed_seconds=time.time() - start_time,
        )

    log(f"[DONE] saved={saved_count}, skipped={skipped_count}")
    log(f"[DONE] output={save_dir}")


class Step2App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Step 2 - Crop Video by Annotation")
        self.worker_thread: threading.Thread | None = None

        self.video_var = tk.StringVar()
        self.xml_var = tk.StringVar()
        self.output_root_var = tk.StringVar(value=str(Path.cwd()))
        self.crop_every_var = tk.StringVar(value=str(DEFAULT_CROP_EVERY_SECONDS))
        self.width_var = tk.StringVar(value=str(DEFAULT_OUTPUT_IMAGE_WIDTH))
        self.height_var = tk.StringVar(value=str(DEFAULT_OUTPUT_IMAGE_HEIGHT))
        self.label_var = tk.StringVar(value=DEFAULT_LABELME_LABEL)
        self.inset_var = tk.StringVar(value=str(DEFAULT_LABELME_BOX_INSET))
        self.include_image_data_var = tk.BooleanVar(value=DEFAULT_INCLUDE_IMAGE_DATA)
        self.preview_var = tk.BooleanVar(value=False)
        self.threshold_var = tk.StringVar(value="")
        self.ref_image_var = tk.StringVar()
        self.create_dataset_var = tk.BooleanVar(value=True)
        self.dataset_folder_var = tk.StringVar(value=f"original_dataset_{time.strftime('%Y%m%d')}")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_text_var = tk.StringVar(value="Progress: idle")

        self._build_ui()

    def _build_ui(self):
        frame = ttk.Frame(self.root, padding=10)
        frame.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        row = 0
        self._file_row(frame, row, "Video file", self.video_var, self._choose_video, [
            ("Video Files", "*.mp4 *.avi *.flv *.mkv *.mov"),
            ("All Files", "*.*"),
        ])
        row += 1
        self._file_row(frame, row, "Step 1 XML", self.xml_var, self._choose_xml, [
            ("XML Files", "*.xml"),
            ("All Files", "*.*"),
        ])
        row += 1
        self._folder_row(frame, row, "Output root", self.output_root_var, self._choose_output_root)
        row += 1

        options = ttk.LabelFrame(frame, text="Crop / LabelMe settings", padding=8)
        options.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(8, 4))
        row += 1

        ttk.Label(options, text="Crop every seconds").grid(row=0, column=0, sticky="e", padx=4, pady=3)
        ttk.Entry(options, textvariable=self.crop_every_var, width=8).grid(row=0, column=1, sticky="w", padx=4, pady=3)
        ttk.Label(options, text="Output W x H").grid(row=0, column=2, sticky="e", padx=4, pady=3)
        ttk.Entry(options, textvariable=self.width_var, width=8).grid(row=0, column=3, sticky="w", padx=4, pady=3)
        ttk.Entry(options, textvariable=self.height_var, width=8).grid(row=0, column=4, sticky="w", padx=4, pady=3)

        ttk.Label(options, text="Default JSON label").grid(row=1, column=0, sticky="e", padx=4, pady=3)
        ttk.Entry(options, textvariable=self.label_var, width=8).grid(row=1, column=1, sticky="w", padx=4, pady=3)
        ttk.Label(options, text="Box inset").grid(row=1, column=2, sticky="e", padx=4, pady=3)
        ttk.Entry(options, textvariable=self.inset_var, width=8).grid(row=1, column=3, sticky="w", padx=4, pady=3)
        ttk.Checkbutton(options, text="Include imageData base64", variable=self.include_image_data_var).grid(row=1, column=4, sticky="w", padx=4, pady=3)

        ttk.Checkbutton(options, text="Show OpenCV preview", variable=self.preview_var).grid(row=2, column=0, columnspan=2, sticky="w", padx=4, pady=3)
        ttk.Label(options, text="Threshold diff (blank = off)").grid(row=2, column=2, sticky="e", padx=4, pady=3)
        ttk.Entry(options, textvariable=self.threshold_var, width=8).grid(row=2, column=3, sticky="w", padx=4, pady=3)

        self._file_row(options, 3, "Ref image", self.ref_image_var, self._choose_ref_image, [
            ("Image Files", "*.jpg *.jpeg *.png *.bmp *.webp"),
            ("All Files", "*.*"),
        ], columnspan=4)

        dataset = ttk.LabelFrame(frame, text="Manual classification folder helper", padding=8)
        dataset.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(8, 4))
        row += 1
        ttk.Checkbutton(dataset, text="Create original_dataset folders 0~52 and 99", variable=self.create_dataset_var).grid(row=0, column=0, sticky="w", padx=4, pady=3)
        ttk.Entry(dataset, textvariable=self.dataset_folder_var, width=45).grid(row=0, column=1, sticky="ew", padx=4, pady=3)
        dataset.columnconfigure(1, weight=1)

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(8, 4))
        row += 1
        self.start_button = ttk.Button(button_frame, text="Start Crop", command=self.start_crop)
        self.start_button.pack(side=tk.LEFT)
        ttk.Button(button_frame, text="Quit", command=self.root.destroy).pack(side=tk.LEFT, padx=8)

        progress_frame = ttk.LabelFrame(frame, text="Cropping progress", padding=8)
        progress_frame.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(4, 4))
        row += 1
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self.progress_var,
            maximum=100.0,
            mode="determinate",
        )
        self.progress_bar.grid(row=0, column=0, sticky="ew", padx=4, pady=3)
        ttk.Label(progress_frame, textvariable=self.progress_text_var).grid(row=1, column=0, sticky="w", padx=4, pady=3)
        progress_frame.columnconfigure(0, weight=1)

        self.log_text = tk.Text(frame, height=16, width=100)
        self.log_text.grid(row=row, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        frame.rowconfigure(row, weight=1)
        for col in range(3):
            frame.columnconfigure(col, weight=1)

        self.log("Ready. Select video + XML, then click Start Crop.")

    def _file_row(self, parent, row, label, variable, command, filetypes, columnspan=1):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="e", padx=4, pady=3)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, columnspan=columnspan, sticky="ew", padx=4, pady=3)
        ttk.Button(parent, text="Browse", command=command).grid(row=row, column=2 + columnspan - 1, sticky="w", padx=4, pady=3)
        parent.columnconfigure(1, weight=1)

    def _folder_row(self, parent, row, label, variable, command):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="e", padx=4, pady=3)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=4, pady=3)
        ttk.Button(parent, text="Browse", command=command).grid(row=row, column=2, sticky="w", padx=4, pady=3)
        parent.columnconfigure(1, weight=1)

    def _choose_video(self):
        path = filedialog.askopenfilename(
            title="Select video file",
            filetypes=[("Video Files", "*.mp4 *.avi *.flv *.mkv *.mov"), ("All Files", "*.*")],
        )
        if path:
            self.video_var.set(path)
            if not self.dataset_folder_var.get().strip() or self.dataset_folder_var.get().startswith("original_dataset_"):
                stem = Path(path).stem
                self.dataset_folder_var.set(f"original_dataset_{stem}_{time.strftime('%Y%m%d')}")

    def _choose_xml(self):
        path = filedialog.askopenfilename(
            title="Select Step 1 XML annotation",
            filetypes=[("XML Files", "*.xml"), ("All Files", "*.*")],
        )
        if path:
            self.xml_var.set(path)

    def _choose_output_root(self):
        path = filedialog.askdirectory(title="Select output root folder")
        if path:
            self.output_root_var.set(path)

    def _choose_ref_image(self):
        path = filedialog.askopenfilename(
            title="Select reference image",
            filetypes=[("Image Files", "*.jpg *.jpeg *.png *.bmp *.webp"), ("All Files", "*.*")],
        )
        if path:
            self.ref_image_var.set(path)

    def _read_settings(self) -> CropSettings:
        video_path = Path(self.video_var.get().strip())
        xml_path = Path(self.xml_var.get().strip())
        output_root = Path(self.output_root_var.get().strip())

        if not video_path.exists():
            raise FileNotFoundError(f"Video file does not exist: {video_path}")
        if not xml_path.exists():
            raise FileNotFoundError(f"XML file does not exist: {xml_path}")
        if not output_root.exists():
            output_root.mkdir(parents=True, exist_ok=True)

        threshold_text = self.threshold_var.get().strip()
        threshold_value = float(threshold_text) if threshold_text else None
        ref_text = self.ref_image_var.get().strip()
        ref_path = Path(ref_text) if ref_text else None

        return CropSettings(
            video_path=video_path,
            xml_path=xml_path,
            output_root=output_root,
            crop_every_seconds=float(self.crop_every_var.get().strip()),
            output_width=int(self.width_var.get().strip()),
            output_height=int(self.height_var.get().strip()),
            labelme_label=self.label_var.get().strip() or DEFAULT_LABELME_LABEL,
            labelme_box_inset=int(self.inset_var.get().strip()),
            include_image_data=bool(self.include_image_data_var.get()),
            draw_preview=bool(self.preview_var.get()),
            threshold_value=threshold_value,
            ref_image_path=ref_path,
            create_dataset_folders=bool(self.create_dataset_var.get()),
            dataset_folder_name=self.dataset_folder_var.get().strip() or f"original_dataset_{time.strftime('%Y%m%d')}",
        )

    def start_crop(self):
        if self.worker_thread is not None and self.worker_thread.is_alive():
            messagebox.showwarning("Busy", "Cropping is already running.")
            return

        try:
            settings = self._read_settings()
        except Exception as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return

        self.start_button.config(state=tk.DISABLED)
        self.progress_var.set(0.0)
        self.progress_text_var.set("Progress: starting...")
        self.log("[START]")

        def worker():
            try:
                crop_video(settings, self.threadsafe_log, self.threadsafe_progress)
                self.threadsafe_log("[ALL DONE]")
                self.root.after(0, lambda: messagebox.showinfo("Done", "Step 2 cropping finished."))
            except Exception:
                err = traceback.format_exc()
                self.threadsafe_log(err)
                self.root.after(0, lambda: messagebox.showerror("Error", err))
            finally:
                self.root.after(0, lambda: self.start_button.config(state=tk.NORMAL))

        self.worker_thread = threading.Thread(target=worker, daemon=True)
        self.worker_thread.start()

    @staticmethod
    def _format_seconds(seconds: float) -> str:
        seconds = max(0, int(round(seconds)))
        minutes, sec = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours:d}h {minutes:02d}m {sec:02d}s"
        if minutes > 0:
            return f"{minutes:d}m {sec:02d}s"
        return f"{sec:d}s"

    def update_progress(
        self,
        processed_steps: int,
        total_steps: int,
        frame_index: int,
        total_frames: int,
        saved_count: int,
        skipped_count: int,
        elapsed_seconds: float,
    ):
        if total_steps > 0:
            percent = min(100.0, max(0.0, processed_steps / total_steps * 100.0))
            if processed_steps > 0:
                eta_seconds = elapsed_seconds / processed_steps * max(0, total_steps - processed_steps)
            else:
                eta_seconds = 0.0
            text = (
                f"Progress: {percent:5.1f}%  "
                f"steps {processed_steps}/{total_steps}  "
                f"frames {frame_index}/{total_frames}  "
                f"saved={saved_count}, skipped={skipped_count}  "
                f"elapsed={self._format_seconds(elapsed_seconds)}, ETA={self._format_seconds(eta_seconds)}"
            )
            self.progress_bar.stop()
            self.progress_bar.config(mode="determinate")
            self.progress_var.set(percent)
        else:
            text = (
                f"Progress: running...  "
                f"frame={frame_index}  "
                f"saved={saved_count}, skipped={skipped_count}  "
                f"elapsed={self._format_seconds(elapsed_seconds)}"
            )
            self.progress_bar.config(mode="indeterminate")
            self.progress_bar.start(10)
        self.progress_text_var.set(text)
        self.root.update_idletasks()

    def threadsafe_progress(self, **kwargs):
        self.root.after(0, lambda: self.update_progress(**kwargs))

    def log(self, text: str):
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def threadsafe_log(self, text: str):
        self.root.after(0, lambda: self.log(text))


def main() -> None:
    root = tk.Tk()
    root.geometry("960x620")
    Step2App(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _handle_fatal_exception("Step2_Crop_By_Annotation")

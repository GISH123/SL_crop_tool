"""
Step4_build_classified_labels.py

EXE-friendly version.

Purpose:
    After Step 2 generates cropped images/JSON files and you manually classify
    them into original_dataset folders (0~52 and 99), this tool updates or
    creates LabelMe JSON files using each folder name as the label.

Main EXE workflow:
    1. Double-click Step4_Build_Classified_Labels.exe.
    2. Select the original_dataset folder.
    3. Click Build / Update JSON.

Behavior:
    - Creates missing class folders: 0~52 and 99.
    - For every image inside each class folder:
        - If same-name JSON exists, update it in place.
        - If same-name JSON does not exist, create it from the first JSON in
          that folder if available; otherwise create a default LabelMe JSON.
    - Folder name is used as the shape label.
      Example: original_dataset/.../17/*.jpg => JSON label "17".
"""

from __future__ import annotations

import base64
import copy
import json
import threading
import time
import traceback
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import cv2


# ============================================================
# Defaults
# ============================================================

CLASS_IDS = list(range(0, 53)) + [99]
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
LABELME_VERSION = "5.4.0a0"
DEFAULT_BOX_INSET = 10



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
class Step4Settings:
    dataset_root: Path
    update_existing_image_json: bool
    create_missing_json: bool
    update_orphan_json_labels: bool
    set_image_data_to_null: bool
    include_image_data_base64: bool
    create_json_backup: bool
    create_missing_class_folders: bool
    process_99_folder: bool
    default_box_inset: int


def list_class_ids(process_99_folder: bool) -> list[int]:
    ids = list(range(0, 53))
    if process_99_folder:
        ids.append(99)
    return ids


def read_image_size(image_path: Path) -> tuple[int, int]:
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"Cannot read image: {image_path}")
    height, width = image.shape[:2]
    return width, height


def encode_image_base64(image_path: Path) -> str:
    return base64.b64encode(image_path.read_bytes()).decode("utf-8")


def read_json(json_path: Path) -> dict:
    with json_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(json_path: Path, data: dict, create_backup: bool) -> None:
    if create_backup and json_path.exists():
        backup_path = json_path.with_suffix(json_path.suffix + f".{time.strftime('%Y%m%d_%H%M%S')}.bak")
        backup_path.write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def list_images(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(
        [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS],
        key=lambda p: p.name.lower(),
    )


def list_jsons(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(folder.glob("*.json"), key=lambda p: p.name.lower())


def find_template_json(folder: Path) -> Path | None:
    json_files = list_jsons(folder)
    return json_files[0] if json_files else None


def get_inset_points(width: int, height: int, inset: int) -> list[list[float]]:
    width = int(width)
    height = int(height)
    inset = int(inset)

    if width <= 1 or height <= 1:
        raise ValueError(f"Invalid image size for LabelMe JSON: {width}x{height}")

    if width <= inset * 2 or height <= inset * 2:
        return [[0.0, 0.0], [float(width - 1), float(height - 1)]]

    return [[float(inset), float(inset)], [float(width - inset), float(height - inset)]]


def default_shape(label: str, width: int, height: int, inset: int) -> dict:
    return {
        "label": str(label),
        "points": get_inset_points(width, height, inset),
        "group_id": None,
        "description": "",
        "shape_type": "rectangle",
        "flags": {},
        "mask": None,
    }


def default_labelme_json(image_path: Path, label: str, inset: int) -> dict:
    width, height = read_image_size(image_path)
    return {
        "version": LABELME_VERSION,
        "flags": {},
        "shapes": [default_shape(label, width, height, inset)],
        "imagePath": image_path.name,
        "imageData": None,
        "imageHeight": int(height),
        "imageWidth": int(width),
    }


def ensure_labelme_shape_defaults(shape: dict) -> None:
    shape.setdefault("group_id", None)
    shape.setdefault("description", "")
    shape.setdefault("shape_type", "rectangle")
    shape.setdefault("flags", {})
    shape.setdefault("mask", None)


def set_all_shape_labels(labelme_data: dict, label: str, image_path: Path | None, inset: int) -> None:
    shapes = labelme_data.get("shapes")

    if not isinstance(shapes, list) or len(shapes) == 0:
        if image_path is None:
            raise ValueError("LabelMe JSON has no shapes and no image available to create default shape.")
        width, height = read_image_size(image_path)
        labelme_data["shapes"] = [default_shape(label, width, height, inset)]
        return

    for shape in shapes:
        if not isinstance(shape, dict):
            continue
        shape["label"] = str(label)
        ensure_labelme_shape_defaults(shape)


def set_image_data(labelme_data: dict, image_path: Path | None, settings: Step4Settings) -> None:
    if settings.set_image_data_to_null:
        labelme_data["imageData"] = None
        return

    if settings.include_image_data_base64 and image_path is not None:
        labelme_data["imageData"] = encode_image_base64(image_path)
        return

    labelme_data["imageData"] = None


def update_json_for_image(labelme_data: dict, image_path: Path, label: str, settings: Step4Settings) -> dict:
    output_data = copy.deepcopy(labelme_data)
    width, height = read_image_size(image_path)

    output_data.setdefault("version", LABELME_VERSION)
    output_data.setdefault("flags", {})
    output_data["imagePath"] = image_path.name
    output_data["imageWidth"] = int(width)
    output_data["imageHeight"] = int(height)

    set_all_shape_labels(output_data, label, image_path, settings.default_box_inset)
    set_image_data(output_data, image_path, settings)

    return output_data


def update_orphan_json_label(json_path: Path, label: str, settings: Step4Settings) -> None:
    data = read_json(json_path)
    set_all_shape_labels(data, label, None, settings.default_box_inset)

    if settings.set_image_data_to_null:
        data["imageData"] = None

    write_json(json_path, data, settings.create_json_backup)


def process_class_folder(folder: Path, settings: Step4Settings, log) -> dict[str, int]:
    label = folder.name
    stats = {
        "updated_existing": 0,
        "created_missing": 0,
        "skipped_missing": 0,
        "orphan_updated": 0,
        "errors": 0,
    }

    if not folder.exists() or not folder.is_dir():
        log(f"[SKIP] Missing folder: {folder}")
        return stats

    image_files = list_images(folder)
    json_files = list_jsons(folder)

    if not image_files and not json_files:
        log(f"[SKIP] Folder {label}: empty")
        return stats

    template_json_path = find_template_json(folder)
    template_data = None
    if template_json_path is not None:
        try:
            template_data = read_json(template_json_path)
            log(f"[TEMPLATE] Folder {label}: {template_json_path.name}")
        except Exception as exc:
            stats["errors"] += 1
            log(f"[WARN] Folder {label}: cannot read template {template_json_path.name}: {exc}")

    for image_path in image_files:
        json_path = image_path.with_suffix(".json")

        try:
            if json_path.exists():
                if settings.update_existing_image_json:
                    existing_data = read_json(json_path)
                    output_data = update_json_for_image(existing_data, image_path, label, settings)
                    write_json(json_path, output_data, settings.create_json_backup)
                    stats["updated_existing"] += 1
                continue

            if not settings.create_missing_json:
                stats["skipped_missing"] += 1
                continue

            if template_data is not None:
                output_data = update_json_for_image(template_data, image_path, label, settings)
            else:
                output_data = default_labelme_json(image_path, label, settings.default_box_inset)
                set_image_data(output_data, image_path, settings)

            write_json(json_path, output_data, settings.create_json_backup)
            stats["created_missing"] += 1

        except Exception as exc:
            stats["errors"] += 1
            log(f"[ERROR] Folder {label}, image {image_path.name}: {exc}")

    if settings.update_orphan_json_labels:
        image_stems = {image_path.stem.lower() for image_path in image_files}
        for json_path in json_files:
            if json_path.stem.lower() in image_stems:
                continue
            try:
                update_orphan_json_label(json_path, label, settings)
                stats["orphan_updated"] += 1
            except Exception as exc:
                stats["errors"] += 1
                log(f"[ERROR] Folder {label}, orphan json {json_path.name}: {exc}")

    log(
        f"[DONE] Folder {label}: "
        f"updated_existing={stats['updated_existing']}, "
        f"created_missing={stats['created_missing']}, "
        f"skipped_missing={stats['skipped_missing']}, "
        f"orphan_updated={stats['orphan_updated']}, "
        f"errors={stats['errors']}"
    )
    return stats


def build_classified_labels(settings: Step4Settings, log) -> dict[str, int]:
    dataset_root = settings.dataset_root
    if not dataset_root.exists():
        raise FileNotFoundError(f"Dataset folder does not exist: {dataset_root}")
    if not dataset_root.is_dir():
        raise NotADirectoryError(f"Dataset path is not a folder: {dataset_root}")

    class_ids = list_class_ids(settings.process_99_folder)

    if settings.create_missing_class_folders:
        for class_id in class_ids:
            (dataset_root / str(class_id)).mkdir(parents=True, exist_ok=True)
        log(f"[FOLDERS] Ensured class folders exist: 0~52" + (" and 99" if settings.process_99_folder else ""))

    log(f"[DATASET] {dataset_root}")
    log(f"[CLASS COUNT] {len(class_ids)}")
    log(f"[UPDATE_EXISTING_IMAGE_JSON] {settings.update_existing_image_json}")
    log(f"[CREATE_MISSING_JSON] {settings.create_missing_json}")
    log(f"[UPDATE_ORPHAN_JSON_LABELS] {settings.update_orphan_json_labels}")

    total = {
        "updated_existing": 0,
        "created_missing": 0,
        "skipped_missing": 0,
        "orphan_updated": 0,
        "errors": 0,
    }

    for class_id in class_ids:
        stats = process_class_folder(dataset_root / str(class_id), settings, log)
        for key in total:
            total[key] += stats[key]

    log(
        f"[ALL DONE] "
        f"updated_existing={total['updated_existing']}, "
        f"created_missing={total['created_missing']}, "
        f"skipped_missing={total['skipped_missing']}, "
        f"orphan_updated={total['orphan_updated']}, "
        f"errors={total['errors']}"
    )
    return total


class Step4App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Step 4 - Build Classified LabelMe JSON")
        self.worker_thread: threading.Thread | None = None

        self.dataset_var = tk.StringVar()
        self.update_existing_var = tk.BooleanVar(value=True)
        self.create_missing_json_var = tk.BooleanVar(value=True)
        self.update_orphan_var = tk.BooleanVar(value=True)
        self.image_data_null_var = tk.BooleanVar(value=True)
        self.include_base64_var = tk.BooleanVar(value=False)
        self.backup_var = tk.BooleanVar(value=False)
        self.create_folders_var = tk.BooleanVar(value=True)
        self.process_99_var = tk.BooleanVar(value=True)
        self.inset_var = tk.StringVar(value=str(DEFAULT_BOX_INSET))

        self._build_ui()

    def _build_ui(self):
        frame = ttk.Frame(self.root, padding=10)
        frame.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        ttk.Label(frame, text="original_dataset folder").grid(row=0, column=0, sticky="e", padx=4, pady=4)
        ttk.Entry(frame, textvariable=self.dataset_var).grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        ttk.Button(frame, text="Browse", command=self.choose_dataset).grid(row=0, column=2, padx=4, pady=4)
        frame.columnconfigure(1, weight=1)

        options = ttk.LabelFrame(frame, text="Options", padding=8)
        options.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 4))
        options.columnconfigure(1, weight=1)

        ttk.Checkbutton(options, text="Create missing folders 0~52 and 99", variable=self.create_folders_var).grid(row=0, column=0, sticky="w", padx=4, pady=3)
        ttk.Checkbutton(options, text="Process 99 folder", variable=self.process_99_var).grid(row=0, column=1, sticky="w", padx=4, pady=3)
        ttk.Checkbutton(options, text="Update existing image JSON", variable=self.update_existing_var).grid(row=1, column=0, sticky="w", padx=4, pady=3)
        ttk.Checkbutton(options, text="Create missing JSON", variable=self.create_missing_json_var).grid(row=1, column=1, sticky="w", padx=4, pady=3)
        ttk.Checkbutton(options, text="Update orphan JSON labels", variable=self.update_orphan_var).grid(row=2, column=0, sticky="w", padx=4, pady=3)
        ttk.Checkbutton(options, text="Set imageData to null", variable=self.image_data_null_var).grid(row=2, column=1, sticky="w", padx=4, pady=3)
        ttk.Checkbutton(options, text="Include imageData base64", variable=self.include_base64_var).grid(row=3, column=0, sticky="w", padx=4, pady=3)
        ttk.Checkbutton(options, text="Create .bak backup before overwrite", variable=self.backup_var).grid(row=3, column=1, sticky="w", padx=4, pady=3)
        ttk.Label(options, text="Default box inset").grid(row=4, column=0, sticky="e", padx=4, pady=3)
        ttk.Entry(options, textvariable=self.inset_var, width=10).grid(row=4, column=1, sticky="w", padx=4, pady=3)

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 4))
        self.start_button = ttk.Button(button_frame, text="Build / Update JSON", command=self.start)
        self.start_button.pack(side=tk.LEFT)
        ttk.Button(button_frame, text="Quit", command=self.root.destroy).pack(side=tk.LEFT, padx=8)

        self.log_text = tk.Text(frame, height=22, width=100)
        self.log_text.grid(row=3, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        frame.rowconfigure(3, weight=1)

        self.log("Ready. Select your original_dataset folder, then click Build / Update JSON.")

    def choose_dataset(self):
        path = filedialog.askdirectory(title="Select original_dataset folder")
        if path:
            self.dataset_var.set(path)

    def read_settings(self) -> Step4Settings:
        dataset_root = Path(self.dataset_var.get().strip())
        if not dataset_root.exists():
            raise FileNotFoundError(f"Dataset folder does not exist: {dataset_root}")

        return Step4Settings(
            dataset_root=dataset_root,
            update_existing_image_json=bool(self.update_existing_var.get()),
            create_missing_json=bool(self.create_missing_json_var.get()),
            update_orphan_json_labels=bool(self.update_orphan_var.get()),
            set_image_data_to_null=bool(self.image_data_null_var.get()),
            include_image_data_base64=bool(self.include_base64_var.get()),
            create_json_backup=bool(self.backup_var.get()),
            create_missing_class_folders=bool(self.create_folders_var.get()),
            process_99_folder=bool(self.process_99_var.get()),
            default_box_inset=int(self.inset_var.get().strip()),
        )

    def start(self):
        if self.worker_thread is not None and self.worker_thread.is_alive():
            messagebox.showwarning("Busy", "Step 4 is already running.")
            return

        try:
            settings = self.read_settings()
        except Exception as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return

        self.start_button.config(state=tk.DISABLED)
        self.log("[START]")

        def worker():
            try:
                total = build_classified_labels(settings, self.threadsafe_log)
                self.root.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Done",
                        "Step 4 finished.\n"
                        f"updated_existing={total['updated_existing']}\n"
                        f"created_missing={total['created_missing']}\n"
                        f"errors={total['errors']}",
                    ),
                )
            except Exception:
                err = traceback.format_exc()
                self.threadsafe_log(err)
                self.root.after(0, lambda: messagebox.showerror("Error", err))
            finally:
                self.root.after(0, lambda: self.start_button.config(state=tk.NORMAL))

        self.worker_thread = threading.Thread(target=worker, daemon=True)
        self.worker_thread.start()

    def log(self, text: str):
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def threadsafe_log(self, text: str):
        self.root.after(0, lambda: self.log(text))


def main() -> None:
    root = tk.Tk()
    root.geometry("960x620")
    Step4App(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _handle_fatal_exception("Step4_Build_Classified_Labels")

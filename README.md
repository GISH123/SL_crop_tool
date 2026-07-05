# SL_crop_tool

Public handoff repository for the Poker Crop Tool.

This toolset is used to create poker/card ROI annotations, crop images from videos by annotation, optionally classify crops through a YOLO11-style HTTP prediction API, and build/fix LabelMe JSON labels from classified folders.

---

## Current Tool Flow

1. Step1_get_poker_annotation.py

   Tkinter annotation tool.

   Main purpose:

   - Open video / image / stream.
   - Draw poker/card ROI regions.
   - Export XML annotation.
   - Export related JSON annotation.

2. Step2_Crop_by_annotation.py

   Crop tool based on Step 1 annotation.

   Main purpose:

   - Load video and XML annotation.
   - Crop ROI images from video frames.
   - Export cropped images.
   - Export LabelMe-style JSON.
   - Create original_dataset folders for later classification.

3. Step3_YOLO11_HTTP_Predict.py

   Optional auto-classification helper.

   Main purpose:

   - Send cropped images to a YOLO11-style HTTP prediction API.
   - Classify images by predicted label.
   - Supports score threshold, copy/move mode, recursive scan, timeout, and report CSV.

   Default local API example:

       http://127.0.0.1:5000/predict

4. Step4_build_classified_labels.py

   Label rebuilding helper.

   Main purpose:

   - Build or update JSON labels based on classified folder names.
   - Example: images under folder 12 will get label 12.
   - Useful after manually correcting classified image folders.

---

## Recommended Environment

Use a fresh conda environment.

Tested target:

- Python 3.11.13
- Windows
- Tkinter UI
- PyInstaller one-folder build

Create environment:

    conda create -n crop_tool_py31113 python=3.11.13 -y
    conda activate crop_tool_py31113

Install dependencies:

    python -m pip install --upgrade pip setuptools wheel
    python -m pip install -r requirements.txt

Verify imports:

    python -c "import cv2, numpy, skimage, PyInstaller, tkinter; print('imports OK'); print('cv2', cv2.__version__); print('numpy', numpy.__version__); print('PyInstaller', PyInstaller.__version__)"

Compile check:

    python -m compileall -q .

If there is no output from compileall, the source compile check passed.

---

## Run From Source

Activate the environment first:

    conda activate crop_tool_py31113

Run each tool:

    python Step1_get_poker_annotation.py
    python Step2_Crop_by_annotation.py
    python Step3_YOLO11_HTTP_Predict.py
    python Step4_build_classified_labels.py

---

## Build EXE

Activate the environment first:

    conda activate crop_tool_py31113

Build all four GUI tools into one shared PyInstaller folder:

    python -m PyInstaller --clean -y Poker_Crop_Tool_All_In_One_Folder.spec

Or use the helper batch file:

    build_shared_folder_exes_offline.bat

Expected output:

    dist/Poker_Crop_Tool/
      Step1_Annotation_Tool.exe
      Step2_Crop_By_Annotation.exe
      Step3_YOLO11_HTTP_Predict.exe
      Step4_Build_Classified_Labels.exe
      _internal/
      README.md
      README_USAGE.md
      outputs/
      videos/
      datasets/
      runtime_logs/

Send the whole folder:

    dist/Poker_Crop_Tool/

Do not send only the exe files. The exe files share the same PyInstaller runtime folder.

---

## Build Script

The helper script is:

    build_shared_folder_exes_offline.bat

It checks the current Python environment, verifies required packages, cleans old build output, runs PyInstaller, copies README files, creates command-line launchers, and creates suggested working folders.

---

## Runtime / Output Folders

The following folders are runtime or generated output folders:

    outputs/
    cropped_images*/
    original*/
    runtime_logs/
    videos/
    datasets/

These should not be committed.

---

## Git Hygiene

Do not commit:

- build/
- dist/
- output folders
- runtime logs
- input videos
- generated exe/dll/pyd files
- cropped datasets

The current all-in-one build is based on:

    Poker_Crop_Tool_All_In_One_Folder.spec

Legacy note:

    Step3_image_model_predict.py

is the older local-model TensorFlow prediction script. The current handoff flow uses:

    Step3_YOLO11_HTTP_Predict.py

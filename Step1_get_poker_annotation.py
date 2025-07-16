import tkinter as tk
from tkinter import ttk
from tkinter import filedialog, messagebox, simpledialog
import threading
import os
import cv2
import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom
from urllib.parse import urlparse
import json

class VideoCropper:
    def __init__(self, root, video_source, xml_filename):
        self.root = root
        self.video_source = video_source  # can be a URL, file path for video, or an image
        self.xml_filename = xml_filename

        self.is_image = False
        self.video_capture = None
        self.video_playing = False

        # For full resolution frames (rotated or not)
        self.frame = None                   # the original image (if is_image), or the latest video frame
        self.rotated_fullres_frame = None   # full-res after tilt for single-image mode
        self.resized_frame = None           # the displayed (resized) version
        self.stopped_frame = None

        self.fps = 0
        self.tilt_angle = 0

        # Lists for bounding boxes
        self.cropped_regions = []        # rectangles in displayed coords (resized image)
        self.real_cropped_regions = []   # rectangles in the “current” full-resolution (rotated) image
        self.current_label = 0
        self.cropping = False

        # Mouse-callback coords
        self.x_start = self.y_start = self.x_end = self.y_end = 0

        self.version = "1.0.0"  # developer defined version
        self.game_type = 6      # user define (default)

        # If user did not specify input or annotation file, prompt:
        if not self.video_source:
            self.prompt_video_source()

        if not self.xml_filename:
            self.prompt_output_filename()

        # If user cancelled everything, bail out
        if not self.video_source:
            messagebox.showinfo("No Input", "No video/image selected. Exiting.")
            root.quit()
            return

        # Determine if user chose an image, local video, or a stream URL
        self.determine_source_type_and_open()

        # If it's a video, set up width/height from cv2 properties
        # If it's an image, we read it, store the shape, treat it like a single frame
        if not self.is_image:
            self.real_width = int(self.video_capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.real_height = int(self.video_capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.fps = self.video_capture.get(cv2.CAP_PROP_FPS)
            if self.fps == 0:
                self.fps = 30
        else:
            # Single image
            self.real_height, self.real_width = self.frame.shape[:2]
            self.fps = 30  # dummy value

            # Because we are “paused” by default for images, let's immediately
            # apply tilt once so it’s in a valid display state
            self._apply_tilt_and_show()

        self.create_ui()

    def prompt_video_source(self):
        """Prompt user to pick a local file or enter a stream URL."""
        choice = messagebox.askquestion(
            "Choose Input",
            "Do you want to choose a local file?\n(Yes = File dialog, No = Enter URL)",
            icon='question'
        )
        if choice == 'yes':
            file_path = filedialog.askopenfilename(
                title="Select Video or Image File",
                filetypes=[("Media Files", "*.mp4 *.avi *.flv *.mkv *.jpg *.png *.jpeg *.bmp")]
            )
            self.video_source = file_path
        else:
            self.video_source = simpledialog.askstring("Input", "Enter stream URL:")

    def prompt_output_filename(self):
        """Prompt user for the XML output filename (only used for video/stream annotations)."""
        filename = simpledialog.askstring(
            "Output Filename",
            "Enter output annotation XML filename (saved in 'outputs' folder):",
        )
        if filename:
            self.xml_filename = filename
            if not self.xml_filename.endswith(".xml"):
                self.xml_filename += ".xml"
            self.xml_filename = os.path.join("outputs", self.xml_filename)
        else:
            # fallback if user hits cancel
            self.xml_filename = os.path.join("outputs", "default_annotation.xml")

    def determine_source_type_and_open(self):
        """Check if user’s choice is a URL, local video, or an image, and open accordingly."""
        if self.is_url(self.video_source):
            # It's an online stream
            self.video_capture = cv2.VideoCapture(self.video_source)
            if not self.video_capture.isOpened():
                raise Exception("Error: Unable to open stream URL.")
            self.is_image = False
        else:
            # It's a local path
            ext = os.path.splitext(self.video_source)[1].lower()
            if ext in [".jpg", ".jpeg", ".png", ".bmp", ".gif"]:
                # It's an image
                self.is_image = True
                if not os.path.exists(self.video_source):
                    raise Exception("Error: image file not found.")
                self.frame = cv2.imread(self.video_source)
                if self.frame is None:
                    raise Exception("Error reading image file.")
                self.video_playing = False
            else:
                # Assume local video
                self.is_image = False
                self.video_capture = cv2.VideoCapture(self.video_source)
                if not self.video_capture.isOpened():
                    raise Exception("Error: Unable to open video file.")

    def create_ui(self):
        self.root.title("Video/Image Cropper Tool")
        control_frame = ttk.Frame(self.root, padding=(10, 10, 10, 10))
        control_frame.pack(fill=tk.BOTH, expand=True)

        # Tilt Angle Display
        self.angle_label = ttk.Label(
            control_frame, text=f'Tilt Angle: {self.tilt_angle}', font=("Arial", 12)
        )
        self.angle_label.grid(row=0, column=0, columnspan=2, pady=(0, 10))

        # Tilt Controls
        self.tilt_up_button = ttk.Button(control_frame, text="Tilt Up (+1°)", command=self.tilt_up)
        self.tilt_down_button = ttk.Button(control_frame, text="Tilt Down (-1°)", command=self.tilt_down)
        self.tilt_up_button.grid(row=1, column=0, pady=5, sticky='ew')
        self.tilt_down_button.grid(row=1, column=1, pady=5, sticky='ew')

        self.manual_tilt_label = ttk.Label(control_frame, text="Manual Tilt Angle:")
        self.manual_tilt_entry = ttk.Entry(control_frame)
        self.set_tilt_button = ttk.Button(control_frame, text="Set Tilt Angle", command=self.set_manual_tilt)
        self.manual_tilt_label.grid(row=2, column=0, pady=5, sticky='e')
        self.manual_tilt_entry.grid(row=2, column=1, pady=5, sticky='ew')
        self.set_tilt_button.grid(row=2, column=2, pady=5, sticky='ew')

        # Video Controls (hidden if single image)
        self.resume_btn = ttk.Button(control_frame, text="Play/Resume Video", command=self.resume_video)
        self.stop_btn = ttk.Button(control_frame, text="Stop/Pause Video", command=self.stop_video)
        self.forward_button = ttk.Button(control_frame, text="Forward 5s", command=self.forward_video)
        self.reset_button = ttk.Button(control_frame, text="Reset Video to Start", command=self.reset_video)

        if self.is_image:
            # Hide video controls for single image
            self.resume_btn.grid_remove()
            self.stop_btn.grid_remove()
            self.forward_button.grid_remove()
            self.reset_button.grid_remove()
        else:
            # Place them for video
            self.resume_btn.grid(row=3, column=0, columnspan=3, pady=5, sticky='ew')
            self.stop_btn.grid(row=4, column=0, columnspan=3, pady=5, sticky='ew')
            self.forward_button.grid(row=5, column=0, columnspan=3, pady=5, sticky='ew')
            self.reset_button.grid(row=6, column=0, columnspan=3, pady=5, sticky='ew')

        reset_cropped_button = ttk.Button(
            control_frame, text="Reset Cropped Regions", command=self.reset_cropped_regions
        )
        reset_cropped_button.grid(row=7, column=0, columnspan=3, pady=5, sticky='ew')

        save_button = ttk.Button(control_frame, text="Save Annotation", command=self.save_annotation)
        save_button.grid(row=8, column=0, columnspan=3, pady=5, sticky='ew')

        quit_button = ttk.Button(control_frame, text="Quit", command=self.quit)
        quit_button.grid(row=9, column=0, columnspan=3, pady=5, sticky='ew')

        # ----- auto-resize window so all widgets are visible -------------
        for col in range(3):                      # let every column expand
            control_frame.columnconfigure(col, weight=1)

        self.root.update_idletasks()              # ensure geometry info is up-to-date
        w = control_frame.winfo_reqwidth() + 20   # some extra breathing room
        h = control_frame.winfo_reqheight() + 20
        self.root.minsize(w, h)                   # can’t shrink below this
        self.root.geometry(f"{w}x{h}")            # initial size
        
        # Start the periodic update
        self.root.after(10, self.update_video_frame)

    def is_url(self, source):
        try:
            result = urlparse(source)
            return all([result.scheme, result.netloc])
        except ValueError:
            return False

    # ------------------ Tilt logic ------------------ #
    def tilt_up(self):
        self.tilt_angle += 1
        self.angle_label.config(text=f'Tilt Angle: {self.tilt_angle}')
        self.apply_tilt()

    def tilt_down(self):
        self.tilt_angle -= 1
        self.angle_label.config(text=f'Tilt Angle: {self.tilt_angle}')
        self.apply_tilt()

    def set_manual_tilt(self):
        try:
            self.tilt_angle = int(self.manual_tilt_entry.get())
            self.angle_label.config(text=f'Tilt Angle: {self.tilt_angle}')
            self.apply_tilt()
        except ValueError:
            print("Please enter a valid integer for the tilt angle.")

    def apply_tilt(self):
        """If single image or if video is paused, rotate the 'full-res' frame and refresh display."""
        if self.is_image:
            # For single image, always rotate+display
            self._apply_tilt_and_show()
        else:
            # For video, apply tilt only if video_playing == False
            if not self.video_playing and self.stopped_frame is not None:
                self._apply_tilt_and_show()

    def _apply_tilt_and_show(self):
        if self.frame is None:
            return

        # angle in degrees (e.g., self.tilt_angle)
        angle = self.tilt_angle

        # Original width & height of your full-resolution frame
        (h, w) = self.frame.shape[:2]
        (cX, cY) = (w // 2, h // 2)

        # 1) Get the basic rotation matrix around the center
        rotation_mat = cv2.getRotationMatrix2D((cX, cY), angle, 1.0)

        # 2) Compute the absolute values of cosine & sine to find new width & height
        abs_cos = abs(rotation_mat[0, 0])
        abs_sin = abs(rotation_mat[0, 1])

        # 3) Compute the size of the bounding box that fully contains the rotated image
        new_w = int(h * abs_sin + w * abs_cos)
        new_h = int(h * abs_cos + w * abs_sin)

        # 4) Adjust the rotation matrix to account for the translation
        #    (so that the rotated result is centered in that new [new_w x new_h] box)
        rotation_mat[0, 2] += (new_w / 2) - cX
        rotation_mat[1, 2] += (new_h / 2) - cY

        # 5) Finally, warp using the *new* bounding box
        self.rotated_fullres_frame = cv2.warpAffine(self.frame, rotation_mat, (new_w, new_h))

        # 6) Resize for display, then show it
        self.resized_frame = self.resize_frame_for_display(self.rotated_fullres_frame)
        cv2.imshow("poker_crop_tool", self.resized_frame)
        cv2.setMouseCallback("poker_crop_tool", self.draw_rectangle)

    # ------------------ Video controls ------------------ #
    def resume_video(self):
        if self.is_image:
            print("You selected an image. No 'resume' operation available.")
            return

        self.video_playing = True
        # Hide tilt while playing
        self.tilt_up_button.grid_remove()
        self.tilt_down_button.grid_remove()
        self.manual_tilt_label.grid_remove()
        self.manual_tilt_entry.grid_remove()
        self.set_tilt_button.grid_remove()

    def stop_video(self):
        if self.is_image:
            print("You selected an image. No 'stop' operation available.")
            return

        self.video_playing = False
        # Show tilt controls
        self.tilt_up_button.grid()
        self.tilt_down_button.grid()
        self.manual_tilt_label.grid()
        self.manual_tilt_entry.grid()
        self.set_tilt_button.grid()

        if self.resized_frame is not None:
            self.stopped_frame = self.resized_frame.copy()

    def forward_video(self):
        if self.is_image:
            print("You selected an image. No 'forward' operation available.")
            return

        current_frame = int(self.video_capture.get(cv2.CAP_PROP_POS_FRAMES))
        target_frame = min(
            current_frame + 5 * int(self.video_capture.get(cv2.CAP_PROP_FPS)),
            int(self.video_capture.get(cv2.CAP_PROP_FRAME_COUNT)) - 1
        )
        self.video_capture.set(cv2.CAP_PROP_POS_FRAMES, target_frame)

    def reset_video(self):
        if self.is_image:
            print("You selected an image. No 'reset' operation available.")
            return

        self.video_capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
        self.tilt_angle = 0
        self.angle_label.config(text=f'Tilt Angle: {self.tilt_angle}')
        if not self.video_playing:
            self.video_playing = True

        # Hide tilt controls while playing
        self.tilt_up_button.grid_remove()
        self.tilt_down_button.grid_remove()
        self.manual_tilt_label.grid_remove()
        self.manual_tilt_entry.grid_remove()
        self.set_tilt_button.grid_remove()

    # ------------------ Cropping logic ------------------ #
    def draw_rectangle(self, event, x, y, flags, param):
        """Mouse callback for cropping (drag rectangle on resized_frame)."""
        if event == cv2.EVENT_LBUTTONDOWN:
            self.x_start, self.y_start = x, y
            self.cropping = True

        elif event == cv2.EVENT_MOUSEMOVE and self.cropping:
            self.x_end, self.y_end = x, y
            frame_copy = self.resized_frame.copy()
            cv2.rectangle(frame_copy, (self.x_start, self.y_start),
                          (self.x_end, self.y_end), (0, 255, 0), 2)

            # Draw previously cropped
            for region in self.cropped_regions:
                cv2.rectangle(frame_copy,
                              (region['x_min'], region['y_min']),
                              (region['x_max'], region['y_max']),
                              (0, 255, 0), 2)

            cv2.imshow("poker_crop_tool", frame_copy)

        elif event == cv2.EVENT_LBUTTONUP:
            self.x_end, self.y_end = x, y
            self.cropping = False

            # Store bounding box in displayed coordinates
            rect_display = {
                'x_min': min(self.x_start, self.x_end),
                'x_max': max(self.x_start, self.x_end),
                'y_min': min(self.y_start, self.y_end),
                'y_max': max(self.y_start, self.y_end)
            }
            self.cropped_regions.append(rect_display)
            
            # If we haven’t actually rotated (e.g. playing video), use self.frame
            base_frame = self.rotated_fullres_frame
            if base_frame is None:
                base_frame = self.frame

            disp_h, disp_w = self.resized_frame.shape[:2]
            full_h, full_w = base_frame.shape[:2]

            scale_x = full_w / float(disp_w)
            scale_y = full_h / float(disp_h)

            real_rect = {
                'x_min': int(rect_display['x_min'] * scale_x),
                'y_min': int(rect_display['y_min'] * scale_y),
                'x_max': int(rect_display['x_max'] * scale_x),
                'y_max': int(rect_display['y_max'] * scale_y),
            }
            self.real_cropped_regions.append(real_rect)

    def reset_cropped_regions(self):
        self.cropped_regions.clear()
        self.real_cropped_regions.clear()
        print("Cropped regions have been reset.")

    # ------------------ Frame display loop ------------------ #
    def update_video_frame(self):
        """Periodic update for video, or re-show single image if needed."""
        if self.is_image:
            # For single images, re-apply tilt if user changed it
            # But we only do it in apply_tilt() or if cropping. 
            # We'll just keep calling _apply_tilt_and_show so the user sees the final image
            # without flicker. Usually this won't cause big overhead.
            if self.rotated_fullres_frame is not None:
                self.resized_frame = self.resize_frame_for_display(self.rotated_fullres_frame)
                cv2.imshow("poker_crop_tool", self.resized_frame)
                cv2.setMouseCallback("poker_crop_tool", self.draw_rectangle)
        else:
            # Handle video
            if self.video_playing and self.video_capture.isOpened():
                ret, self.frame = self.video_capture.read()
                if ret:
                    # For video, we do no “true rotation” at full-res every frame 
                    # (unless you prefer). Typically we do that if paused.
                    self.resized_frame = self.resize_frame_for_display(self.frame)
                    self.stopped_frame = self.resized_frame.copy()
                    cv2.imshow("poker_crop_tool", self.resized_frame)
                    cv2.setMouseCallback("poker_crop_tool", self.draw_rectangle)

                    delay = int(1000 / self.fps)
                    cv2.waitKey(delay)
                else:
                    print("Reached end of video or error. Resetting to start.")
                    self.video_capture.set(cv2.CAP_PROP_POS_FRAMES, 0)

        self.root.after(20, self.update_video_frame)

    def resize_frame_for_display(self, frame, display_max_width=1920, display_max_height=1080):
        """Resize preserving aspect ratio, store scale for bounding box mapping."""
        height, width = frame.shape[:2]
        aspect_ratio = width / float(height)

        if width > display_max_width or height > display_max_height:
            if (width / display_max_width) > (height / display_max_height):
                new_width = display_max_width
                new_height = int(display_max_width / aspect_ratio)
            else:
                new_height = display_max_height
                new_width = int(display_max_height * aspect_ratio)
        else:
            new_width, new_height = width, height

        # NOTE: We do scale_x, scale_y specifically each time in draw_rectangle instead
        # so no need to store them globally here. 
        return cv2.resize(frame, (new_width, new_height))

    # ------------------ Save logic ------------------ #
    def save_annotation(self):
        if not self.real_cropped_regions:
            print("No regions were cropped. Nothing to save.")
            return

        if self.is_image:
            # For single images, just save out each cropped region as a new file
            image_name = os.path.basename(self.video_source)
            prefix = os.path.splitext(image_name)[0]
            output_dir = "outputs"
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)

            for i, rect in enumerate(self.real_cropped_regions, start=1):
                # Crop from the rotated_fullres_frame
                x_min, x_max = rect['x_min'], rect['x_max']
                y_min, y_max = rect['y_min'], rect['y_max']
                cropped_img = self.rotated_fullres_frame[y_min:y_max, x_min:x_max]
                # Save as prefix_1.jpg, prefix_2.jpg, etc.
                out_filename = os.path.join(output_dir, f"{prefix}_{i}.jpg")
                cv2.imwrite(out_filename, cropped_img)
                print(f"Saved cropped image: {out_filename}")

        else:
            # Original logic: for videos/streams, save annotation to XML/JSON
            height, width = self.frame.shape[:2] if self.frame is not None else (0, 0)
            # Or if you want to store the last known dimension for video
            self.save_annotations_to_xml(width, height, self.game_type, self.version)
            self.save_annotations_to_json(width, height, self.game_type, self.version)
            print(f"Saved to xml file: {self.xml_filename}")
            print(f"Saved to json file: {self.json_filename}")
            self.current_label += 1

    def save_annotations_to_xml(self, width, height, game_type, version):
        header = f'<?xml version="{version}" encoding="utf-8"?>'
        annotation = ET.Element("annotation")

        size = ET.SubElement(annotation, "size")
        width_elem = ET.SubElement(size, "width")
        width_elem.text = str(width)
        height_elem = ET.SubElement(size, "height")
        height_elem.text = str(height)

        gametype_elem = ET.SubElement(annotation, "gametype")
        gametype_elem.text = str(game_type)

        tilt_angle_elem = ET.SubElement(size, "tilt_angle")
        tilt_angle_elem.text = str(self.tilt_angle)

        for i, rect in enumerate(self.real_cropped_regions):
            obj = ET.SubElement(annotation, "object")
            name = ET.SubElement(obj, "name")
            name.text = f"card_{i+1}"

            bndbox = ET.SubElement(obj, "bndbox")
            xmin = ET.SubElement(bndbox, "xmin")
            xmin.text = str(rect['x_min'])
            xmax = ET.SubElement(bndbox, "xmax")
            xmax.text = str(rect['x_max'])
            ymin = ET.SubElement(bndbox, "ymin")
            ymin.text = str(rect['y_min'])
            ymax = ET.SubElement(bndbox, "ymax")
            ymax.text = str(rect['y_max'])

        rough_string = ET.tostring(annotation, 'utf-8')
        reparsed = minidom.parseString(rough_string)
        pretty_xml = reparsed.toprettyxml(indent="\t")

        full_xml_string = header + pretty_xml.split("?>", 1)[1]

        with open(self.xml_filename, "w", encoding="utf-8") as f:
            f.write(full_xml_string)

    def save_annotations_to_json(self, width, height, game_type, version):
        annotation_data = {
            "annotation_cardback": [],
            "resolution_height": height,
            "resolution_width": width,
            "version": version,
            "video_url": self.video_source  # if it’s an image, it’s just the path
        }

        for i, rect in enumerate(self.real_cropped_regions):
            card_data = {
                "card_num": f"card_{i}",
                "fix": 1 if i < self.game_type else 0,
                "h": rect['y_max'] - rect['y_min'],
                "w": rect['x_max'] - rect['x_min'],
                "x": rect['x_min'],
                "y": rect['y_min']
            }
            annotation_data["annotation_cardback"].append(card_data)

        self.json_filename = self.xml_filename.replace(".xml", ".json")

        with open(self.json_filename, "w", encoding="utf-8") as json_file:
            json.dump(annotation_data, json_file, indent=4)

    def quit(self):
        if self.video_capture:
            self.video_capture.release()
        cv2.destroyAllWindows()
        self.root.quit()

if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("300x300")

    if not os.path.exists("outputs"):
        os.makedirs("outputs")

    video_source = None
    xml_filename = None

    cropper = VideoCropper(root, video_source, xml_filename)
    root.mainloop()

import cv2
import os
import xml.etree.ElementTree as ET
from skimage.metrics import structural_similarity
import time

# Step 1 . Load annotation xml file
# =================================

# Specify the region

def parse_xml_to_crop_regions(xml_file):
    tree = ET.parse(xml_file)
    root = tree.getroot()

    # Extract tilt_angle, default to 0 if not found
    size_element = root.find('size')
    tilt_angle = int(size_element.find('tilt_angle').text) if size_element.find('tilt_angle') is not None else 0

    crop_regions = []
    for obj in root.findall('object'):
        name = obj.find('name').text
        bndbox = obj.find('bndbox')
        x_min = int(bndbox.find('xmin').text)
        y_min = int(bndbox.find('ymin').text)
        x_max = int(bndbox.find('xmax').text)
        y_max = int(bndbox.find('ymax').text)
        
        region = {
            "name": name,
            "x_min": x_min,
            "y_min": y_min,
            "x_max": x_max,
            "y_max": y_max
        }
        
        crop_regions.append(region)
    
    return crop_regions, tilt_angle

# Example usage, read xml file for annotation
xml_file = f'outputs/uk_6cards_20241118.xml' # 此地方可能造成一個問題，因目前step1會將如 video_url="rtmp://pull.video-g18.com:1935/mt01/h-4" 放在xml header第一行，這行要拿掉video_url不然ET parse會出錯
crop_regions, tilt_angle = parse_xml_to_crop_regions(xml_file)

# =================================

# Step 2. crop video region based on annotation

# =================================

# Open video file
# video_name = "uk_6_cards"
# video_name = "uk_35m"
video_name = "uk_55m"
video_capture = cv2.VideoCapture(f'{video_name}.mp4')

threshold_value = 50  # Specify the threshold value for detecting intensity change # 通常卡牌都80以上
frame_count = 0
prev_gray = None
cropped_file_name = f"cropped"
crop_no = 1
timestr = time.strftime("%Y%m%d")
save_dir = f"cropped_images_{video_name}_{timestr}"
threshold_flag = 0
draw_crop_region = False

if not os.path.exists(save_dir):
    os.makedirs(save_dir)

# Get total number of frames in the video
total_frames = int(video_capture.get(cv2.CAP_PROP_FRAME_COUNT))

while video_capture.isOpened():
    ret, frame = video_capture.read()

    # Tilt video by tilt_angle read from xml
    if tilt_angle != 0:
        height, width = frame.shape[:2]
        center = (width // 2, height // 2)
        rotation_matrix = cv2.getRotationMatrix2D(center, tilt_angle, 1.0)
        frame = cv2.warpAffine(frame, rotation_matrix, (width, height))

    # If there are no more frames to read, break out of the loop
    if not ret:
        break

    # Increment the frame count
    frame_count += 1

    # Convert frame to grayscale
    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # ver 1. 手動取出背景圖ref_img，將當前frame與ref_img算出差異，如果差異超過一定數值才crop
    ref_img = cv2.imread('ref_img.jpg')
    
    for region in crop_regions:
        # Crop a region around the specified coordinates
        cropped_region = gray_frame[region["y_min"]:region["y_max"], region["x_min"]:region["x_max"]]

        # Get the size of the cropped_region
        frame_height, frame_width = cropped_region.shape[:2]
        # match the ref_img size to original video size
        resized_ref_img = cv2.resize(ref_img, (frame_width, frame_height))

        # Convert ref img to grayscale
        resized_ref_img = cv2.cvtColor(resized_ref_img, cv2.COLOR_BGR2GRAY)

        # show the region, using green rectangle
        if draw_crop_region:
            cv2.rectangle(frame, (region["x_min"] - 3, region["y_min"] - 3), (region["x_max"] + 3, region["y_max"] + 3), (0, 255, 0), 2)

        # =============================================Code for getting background difference=================================================

        # # Compute SSIM between the two images
        # (score, diff) = structural_similarity(cropped_region, resized_ref_img, full=True)
        # print("Image Similarity: {:.4f}%".format(score * 100))

        # Calculate the mean pixel intensity difference between current and ref frame
        diff = cv2.absdiff(cropped_region, resized_ref_img)
        mean_intensity_diff = diff.mean()
        # print(f"mean_intensity_diff : {mean_intensity_diff}")

        # Check if the mean intensity difference is above a certain threshold
        if mean_intensity_diff > threshold_value:
            # If the mean intensity difference exceeds the threshold, save the crop
            color_cropped = frame[region["y_min"]:region["y_max"], region["x_min"]:region["x_max"]]
            cv2.imwrite(f"{save_dir}/{timestr}_{region['name']}_frame_{frame_count}.jpg", color_cropped)
        #=====================================================================================================================================

    # Display the frame
    cv2.imshow('Frame', frame)

    # ver 2. 以下docstring為註解掉之前開發的code，會對比當前frame跟上一frame的差異，如果差異高於某一數值才開始crop
    """
    # initialize prev_grey on the first run
    if prev_gray is None:
        prev_gray = gray_frame
        prev_cropped_regions = [gray_frame[region["y_min"]:region["y_max"], region["x_min"]:region["x_max"]] for region in crop_regions]

    for region in crop_regions:
        # Crop a region around the specified coordinates
        cropped_region = gray_frame[region["y_min"]:region["y_max"], region["x_min"]:region["x_max"]]

        # show the region, using green rectangle
        if draw_crop_region:
            cv2.rectangle(frame, (region["x_min"] - 3, region["y_min"] - 3), (region["x_max"] + 3, region["y_max"] + 3), (0, 255, 0), 2)

        # =============================================Code for getting background difference=================================================
        # Calculate the mean pixel intensity difference between current and previous frame
        diff = cv2.absdiff(cropped_region, prev_cropped_regions[crop_regions.index(region)])
        mean_intensity_diff = diff.mean()

        # Check if the mean intensity difference is above a certain threshold
        if mean_intensity_diff > threshold_value:
            threshold_flag += 1

            # # If the mean intensity difference exceeds the threshold, save the crop
            # print(f"Cropped image : {region['name']} - x_min : {region['x_min']}, y_min : {region['y_min']}, x_max : {region['x_max']}, y_max : {region['y_max']}")
            # color_cropped = frame[region["y_min"]:region["y_max"], region["x_min"]:region["x_max"]]
            # cv2.imwrite(f"{save_dir}/{region['name']}_frame_{frame_count}.jpg", color_cropped)

        # Store the current cropped region for the next iteration
        prev_cropped_regions[crop_regions.index(region)] = cropped_region

        #=====================================================================================================================================

    # Display the frame
    cv2.imshow('Frame', frame)

    # Store the current grayscale frame for the next iteration
    prev_gray = gray_frame

    """

    ###############################  key events ################################
    key = cv2.waitKey(20) & 0xFF

    # fast forward seconds definition
    fast_forward_sec = 5
    sec = 0.2

    # Break out of the loop if 'q' is pressed
    if key == ord('q'):
        break

    # Fast forward "fast_forward_sec" seconds when 'f' is pressed
    elif key == ord('f'):
        # Get current frame number
        current_frame = int(video_capture.get(cv2.CAP_PROP_POS_FRAMES))
        # Calculate target frame number "sec" seconds forward
        target_frame = min(current_frame + fast_forward_sec * int(video_capture.get(cv2.CAP_PROP_FPS)), int(video_capture.get(cv2.CAP_PROP_FRAME_COUNT)) - 1)
        # Set video capture to the target frame
        video_capture.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
    
    # only forward the video every "sec" seconds
    else:
        # ver 1 old code, crop everything
        '''
        # # ======================================= clip part===============================================
        # # clip the frame every "sec" seconds
        # if threshold_flag % 2 == 1:
        #     for region in crop_regions:
        #         color_cropped = frame[region["y_min"]:region["y_max"], region["x_min"]:region["x_max"]]
        #         cv2.imwrite(f"{save_dir}/{region['name']}_frame_{frame_count}.jpg", color_cropped)
        for region in crop_regions:
            color_cropped = frame[region["y_min"]:region["y_max"], region["x_min"]:region["x_max"]]
            cv2.imwrite(f"{save_dir}/{video_name}_{region['name']}_frame_{frame_count}.jpg", color_cropped)
        # # ================================================================================================
        '''

        # Get current frame number
        current_frame = int(video_capture.get(cv2.CAP_PROP_POS_FRAMES))

        # Check if it's the last frame
        if current_frame == total_frames:
            print("Last frame reached.")
            break

        # Calculate target frame number "sec" seconds forward
        target_frame = min(current_frame + sec * int(video_capture.get(cv2.CAP_PROP_FPS)), int(video_capture.get(cv2.CAP_PROP_FRAME_COUNT)) - 1)
        # Set video capture to the target frameq
        video_capture.set(cv2.CAP_PROP_POS_FRAMES, target_frame)

# Release the video capture and video writer objects
video_capture.release()
cv2.destroyAllWindows()

# =================================
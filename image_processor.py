import cv2
import numpy as np

def enhance_lighting(image_path, output_path):
    img = cv2.imread(image_path)
    if img is None: return False

    # 1. Convert to LAB color space to process lightness (L) separately
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l_channel, a, b = cv2.split(lab)

    # 2. Apply CLAHE to the L-channel for adaptive brightening
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    cl = clahe.apply(l_channel)

    # 3. Merge channels back and convert to BGR
    enhanced_img = cv2.merge((cl, a, b))
    final_img = cv2.cvtColor(enhanced_img, cv2.COLOR_LAB2BGR)

    # 4. Save the pre-processed image
    cv2.imwrite(output_path, final_img)
    return True
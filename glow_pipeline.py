import os
import cv2
import base64
import requests
import json
from dotenv import load_dotenv

# Silence MediaPipe/TF logging noise
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' 

try:
    import mediapipe as mp
    mp_face = mp.solutions.face_detection
except Exception as e:
    raise RuntimeError(f"MediaPipe failed to initialize: {e}")

load_dotenv()

def validate_image(image_path):
    """Stage 1: The Bouncer (Local Quality Check)"""
    img = cv2.imread(image_path)
    if img is None:
        return False, f"File not found: {image_path}"

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Blur Check (Laplacian Variance)
    score = cv2.Laplacian(gray, cv2.CV_64F).var()
    if score < 20: 
        return False, f"Image too blurry (Score: {int(score)}). Need more detail!"

    # Lighting Check (Mean Brightness)
    brightness = gray.mean()
    if brightness < 30:
        return False, f"Too dark (Score: {int(brightness)}). Face a window!"

    # Face Detection
    try:
        with mp_face.FaceDetection(model_selection=1, min_detection_confidence=0.5) as detector:
            results = detector.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
            if not results.detections:
                return False, "No face detected. Please center your face."
    except Exception as e:
        return False, f"Detection Error: {str(e)}"

    return True, "Success"

def compare_skin(img1, img2):
    """Stage 2: The Aesthetician (VLM Comparison)"""
    api_key = os.getenv("OPENROUTER_API_KEY")
    
    def b64(path):
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode('utf-8')

    # Re-introducing the strict original plan requirements
    system_prompt = """You are a highly observant cosmetic aesthetician. Analyze a 'Before' and 'After' image.
    
CRITICAL INSTRUCTIONS:
1. Ignore changes in lighting, background, or camera angle.
2. Do NOT diagnose medical conditions (acne, eczema, etc.).
3. Focus EXCLUSIVELY on: Surface Radiance (glow), Texture Smoothness, and Pore Visibility.
4. If you detect significant lighting differences, set 'lighting_variance_warning' to true.
5. Return ONLY a raw JSON object matching the schema below.

REQUIRED SCHEMA:
{
  "compliance_flag": true, 
  "lighting_variance_warning": false,
  "cosmetic_metrics": {
    "radiance_improvement_percentage": 0,
    "texture_smoothness_change": "string",
    "pore_visibility_change": "string"
  },
  "witty_report": "string"
}"""

    payload = {
        "model": "google/gemini-2.0-flash-001",
        "response_format": {"type": "json_object"}, # Forces JSON mode
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": [
                {"type": "text", "text": "Compare these two images (Image 1 = Before, Image 2 = After) and provide the report:"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64(img1)}"}},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64(img2)}"}}
            ]}
        ]
    }
    
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions", 
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, 
        json=payload
    )
    
    return response.json()

if __name__ == "__main__":
    file1, file2 = "test_before.jpeg", "test_after.jpeg"

    if not os.path.exists(file1) or not os.path.exists(file2):
        print("❌ Error: Missing image files in directory.")
    else:
        # Validate both images
        v1, m1 = validate_image(file1)
        v2, m2 = validate_image(file2)

        if v1 and v2:
            print("✅ Stage 1: Quality Check Passed.")
            print("🚀 Stage 2: Analyzing skin changes...")
            
            raw_result = compare_skin(file1, file2)
            
            # Parse and display the "Witty Report" clearly
            try:
                content = json.loads(raw_result['choices'][0]['message']['content'])
                print("\n--- CAFE GLOW AUDIT ---")
                print(f"Radiance Boost: {content['cosmetic_metrics']['radiance_improvement_percentage']}%")
                print(f"Texture: {content['cosmetic_metrics']['texture_smoothness_change']}")
                print(f"Pores: {content['cosmetic_metrics']['pore_visibility_change']}")
                print("-" * 23)
                print(f"REPORT: {content['witty_report']}")
                
                if content['lighting_variance_warning']:
                    print("\n⚠️ Note: Our AI noticed a shift in your lighting which might affect accuracy.")
            except (KeyError, json.JSONDecodeError):
                print("Error parsing the AI report. Raw response:")
                print(json.dumps(raw_result, indent=2))
        else:
            print(f"❌ Bouncer Rejected: {m1 if not v1 else m2}")
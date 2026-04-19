import os
import cv2
import json
import base64
import requests
import logging
import asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler

# 1. SETUP & LOGGING
load_dotenv()
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' 
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Robust MediaPipe Import
try:
    import mediapipe as mp
    mp_face = mp.solutions.face_detection
except Exception as e:
    raise RuntimeError(f"MediaPipe failed: {e}")

# 2. CORE LOGIC (From your working pipeline)
def validate_image(image_path):
    img = cv2.imread(image_path)
    if img is None: return False, "Image read error."
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Blur Check
    score = cv2.Laplacian(gray, cv2.CV_64F).var()
    if score < 20: return False, f"Too blurry (Score: {int(score)}). Try again!"
    
    # Lighting Check
    if gray.mean() < 30: return False, "Too dark! Find a window."

    # Face Detection
    with mp_face.FaceDetection(model_selection=0, min_detection_confidence=0.8) as detector:
        results = detector.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        if not results.detections: return False, "No face detected. Frame your face clearly!"
    
    return True, "Success"

def compare_skin(img1, img2):
    api_key = os.getenv("OPENROUTER_API_KEY")
    def b64(path):
        with open(path, "rb") as f: return base64.b64encode(f.read()).decode('utf-8')

    prompt = """You are a cosmetic aesthetician. Analyze 'Before' (Img 1) vs 'After' (Img 2). 
    Ignore lighting/angle. Focus on: Surface Radiance, Texture, and Pores.
    Return ONLY JSON with: compliance_flag, lighting_variance_warning, 
    cosmetic_metrics (radiance_improvement_percentage, texture_smoothness_change, pore_visibility_change), 
    and witty_report."""

    payload = {
        "model": "google/gemini-2.0-flash-001",
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": [
                {"type": "text", "text": "Compare these:"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64(img1)}"}},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64(img2)}"}}
            ]}
        ]
    }
    res = requests.post("https://openrouter.ai/api/v1/chat/completions", 
                        headers={"Authorization": f"Bearer {api_key}"}, json=payload)
    return res.json()

# 3. TELEGRAM HANDLERS
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # Reset user state
    context.user_data['images'] = []
    await update.message.reply_text("✨ Welcome to Cafe Glow! ✨\n\nSend me your FIRST photo (The Baseline).")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # Ensure list exists in user_data
    if 'images' not in context.user_data:
        context.user_data['images'] = []

    # Get the highest resolution photo
    photo_file = await update.message.photo[-1].get_file()
    
    # Create directory for the user
    user_dir = f"vault/{user_id}"
    os.makedirs(user_dir, exist_ok=True)
    
    img_index = len(context.user_data['images']) + 1
    file_path = f"{user_dir}/img_{img_index}.jpg"
    await photo_file.download_to_drive(file_path)

    # STAGE 1: THE BOUNCER
    is_valid, message = validate_image(file_path)
    
    if not is_valid:
        os.remove(file_path) # Clean up bad image
        await update.message.reply_text(f"❌ {message}")
        return

    # If valid, add to list
    context.user_data['images'].append(file_path)

    if len(context.user_data['images']) == 1:
        await update.message.reply_text("✅ Baseline accepted! Now, send me your SECOND photo (The Audit).")
    
    else:
        await update.message.reply_text("🚀 Both photos accepted. Analyzing your glow...")
        
        # STAGE 2: THE AESTHETICIAN
        img1, img2 = context.user_data['images']
        raw_result = compare_skin(img1, img2)
        
        try:
            content = json.loads(raw_result['choices'][0]['message']['content'])
            metrics = content['cosmetic_metrics']
            
            report = (
                f"--- ☕ CAFE GLOW AUDIT --- \n\n"
                f"✨ Radiance: +{metrics['radiance_improvement_percentage']}%\n"
                f"Smoothness: {metrics['texture_smoothness_change']}\n"
                f"Pores: {metrics['pore_visibility_change']}\n\n"
                f"📝 {content['witty_report']}"
            )
            await update.message.reply_text(report)
        except Exception:
            await update.message.reply_text("Could not parse the report. Gemini might be shy today.")

        # RESET for next test
        context.user_data['images'] = []
        for f in os.listdir(user_dir): os.remove(f"{user_dir}/{f}")

# 4. START THE BOT
if __name__ == '__main__':
    application = ApplicationBuilder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    print("Glow Bot is running... Press Ctrl+C to stop.")
    application.run_polling()
import os
from database import init_db, save_audit, get_user_history
import cv2
import json
import base64
import requests
import logging
import asyncio
import datetime
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

# Helper: Non-blocking API wrapper (ADDED CONTENT-TYPE HEADER)
async def call_gemini_async(payload):
    headers = {
        "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
        "Content-Type": "application/json"
    }
    return await asyncio.to_thread(requests.post, 
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=payload
    )

# 2. CORE LOGIC
def validate_image(image_path):
    img = cv2.imread(image_path)
    if img is None: return False, "Image read error."
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Blur Check
    score = cv2.Laplacian(gray, cv2.CV_64F).var()
    if score < 20: return False, f"Too blurry (Score: {int(score)}). Try again!"

    # Lighting Check
    if gray.mean() < 30: return False, "Too dark! Find a window."

    # Face Detection (HARDENED)
    with mp_face.FaceDetection(model_selection=0, min_detection_confidence=0.8) as detector:
        results = detector.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        if not results.detections: return False, "No face detected. Frame your face clearly!"

    return True, "Success"

def b64(path):
    with open(path, "rb") as f: return base64.b64encode(f.read()).decode('utf-8')

# FEATURE: Lighting Normalization
async def get_lighting_guidance(image_path):
    prompt = "Analyze this photo. Describe the lighting conditions, direction, and background in exactly ONE concise sentence. Focus on actionable details the user must replicate for an accurate before/after comparison."
    payload = {
        "model": "google/gemini-2.0-flash-001",
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64(image_path)}"}}
        ]}]
    }
    res = await call_gemini_async(payload)
    if res.status_code == 200:
        return res.json()['choices'][0]['message']['content'].strip()
    return "Find bright, even lighting and avoid harsh shadows."

# FEATURE: Prompt Engineering 2.0 + Comparison
async def compare_skin(img1, img2, history_text=""):
    prompt = f"""You are a cosmetic aesthetician. Analyze 'Before' (Img 1) vs 'After' (Img 2). 
    Ignore minor lighting/angle differences. Focus strictly on dermatological metrics.
    Return ONLY a valid JSON object matching this exact schema:
    {{
      "compliance_flag": true,
      "lighting_variance_warning": null,
      "cosmetic_metrics": {{
        "radiance_improvement_percentage": 0,
        "texture_smoothness_change": "string",
        "pore_visibility_change": "string",
        "under_eye_brightness": "string",
        "redness_reduction": "string",
        "fine_line_smoothness": "string"
      }},
      "witty_report": "string"
    }}
    {history_text}
    """
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
    res = await call_gemini_async(payload)
    return res.json()

# FEATURE: Progress Tracking & Trend Summary
def generate_trend_summary(history, current_metrics):
    if not history or len(history) < 1:
        return "Baseline established. Great start! Keep tracking your progress."
    
    try:
        # Use .get() to prevent KeyErrors if the AI missed a field
        last_radiance = history[-1]['metrics'].get('radiance_improvement_percentage', 0)
        current_radiance = current_metrics.get('radiance_improvement_percentage', 0)
        diff = current_radiance - last_radiance
        
        if diff > 2:
            trend = f"📈 You've seen a {int(abs(diff))}% radiance jump since your last audit! Your hydration/routine is clearly paying off."
        elif diff < -2:
            trend = "📉 Radiance dipped slightly since last time. Check sleep, hydration, or lighting consistency!"
        else:
            trend = "📊 Radiance remains stable. Consistency is key in skincare!"
            
        return f"{trend}\n💡 Tip: Track these metrics weekly to spot long-term patterns."
    except Exception as e:
        logging.error(f"Trend generation error: {e}")
        return "Keep tracking your progress to see trends!"

# 3. TELEGRAM HANDLERS
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['images'] = []
    await update.message.reply_text("✨ Welcome to Cafe Glow! ✨\n\nSend me your FIRST photo (The Baseline).")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # SAFETY: Ensure state exists even if user skipped /start
    if 'images' not in context.user_data:
        context.user_data['images'] = []
        
    photo_file = await update.message.photo[-1].get_file()
    user_dir = f"vault/{update.effective_user.id}"
    os.makedirs(user_dir, exist_ok=True)
    
    img_index = len(context.user_data['images']) + 1
    file_path = f"{user_dir}/img_{img_index}.jpg"
    await photo_file.download_to_drive(file_path)
    
    # STAGE 1: THE BOUNCER
    is_valid, message = validate_image(file_path)
    if not is_valid:
        os.remove(file_path)
        await update.message.reply_text(f"❌ {message}")
        return
        
    context.user_data['images'].append(file_path)
    
    if len(context.user_data['images']) == 1:
        # FEATURE: Lighting Normalization
        await update.message.reply_text("✅ Baseline accepted! Analyzing your lighting setup...")
        lighting_tip = await get_lighting_guidance(file_path)
        await update.message.reply_text(
            f"💡 **Lighting Match Guide:**\n{lighting_tip}\n\n"
            f"Please take your SECOND photo (The Audit) matching these exact conditions for maximum accuracy."
        )
    else:
        await update.message.reply_text("🚀 Both photos accepted. Analyzing your glow...")
        img1, img2 = context.user_data['images']
        
        # Prepare history context for trend-aware prompting
        db_history = get_user_history(update.effective_user.id, limit=3)
        history_context = ""
        if db_history:
            history_context = f"\nUser History (Last {len(db_history)} audits): {json.dumps(db_history, indent=2)}"
            
        try:
            raw_result = await compare_skin(img1, img2, history_context)
            
            # Catch API errors
            if 'choices' not in raw_result:
                raise ValueError(f"Invalid API response: {raw_result}")
            
            # Clean LLM markdown if present
            content_raw = raw_result['choices'][0]['message']['content']
            content_clean = content_raw.strip().replace("```json", "").replace("```", "").strip()
            content = json.loads(content_clean)
            
            # Safely extract metrics using .get()
            metrics = content.get('cosmetic_metrics', {})
            
            # Fetch history from DB for the trend summary (BEFORE saving current)
            db_history = get_user_history(update.effective_user.id)
            trend_msg = generate_trend_summary(db_history, metrics)

            # NEW: Save current audit to permanent database
            save_audit(update.effective_user.id, metrics, content.get('witty_report'))
            
            report = (
                f"--- ☕ CAFE GLOW AUDIT ---\n\n"
                f"✨ Radiance: +{metrics.get('radiance_improvement_percentage', 0)}%\n"
                f"🧴 Smoothness: {metrics.get('texture_smoothness_change', 'N/A')}\n"
                f"🔍 Pores: {metrics.get('pore_visibility_change', 'N/A')}\n"
                f"👁️ Under-Eyes: {metrics.get('under_eye_brightness', 'N/A')}\n"
                f"🌹 Redness: {metrics.get('redness_reduction', 'N/A')}\n"
                f"📉 Fine Lines: {metrics.get('fine_line_smoothness', 'N/A')}\n\n"
                f"📝 {content.get('witty_report', 'Looking glowing!')}\n\n"
                f"📈 {trend_msg}"
            )
            
            if content.get('lighting_variance_warning'):
                report += f"\n\n⚠️ Note: {content['lighting_variance_warning']}"
                
            await update.message.reply_text(report)
            

            
        except Exception as e:
            # Explicit logging so we see EXACTLY why it failed in the terminal
            logging.error(f"Error during analysis: {e}", exc_info=True)
            await update.message.reply_text("Could not parse the report. Our aesthetician ran into an issue. Please try again!")
            
        finally:
            # GUARANTEED CLEANUP: Always runs, even if the API throws an error
            context.user_data['images'] = []
            if os.path.exists(user_dir):
                for f in os.listdir(user_dir): 
                    try:
                        os.remove(os.path.join(user_dir, f))
                    except Exception as cleanup_err:
                        logging.error(f"Failed to delete {f}: {cleanup_err}")

# 4. START THE BOT
if __name__ == '__main__':
    # Initialize DB
    init_db()

    application = ApplicationBuilder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("Glow Bot v2.0 is running... Press Ctrl+C to stop.")
    application.run_polling()
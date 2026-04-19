import asyncio
import json
import os
from database import init_db, log_test_result
from glow_bot import compare_skin, validate_image

async def run_benchmark():
    init_db()
    
    # Define your "Gold Standard" tests here
    test_cases = [
        {"name": "Standard Glow Test", "img1": "test_before.jpeg", "img2": "test_after.jpeg"},
        # Add more pairs as you collect them
    ]

    print(f"🧪 Starting Benchmark for {len(test_cases)} cases...")

    for case in test_cases:
        print(f"Running: {case['name']}...")
        
        # 1. Run Bouncer
        v1, _ = validate_image(case['img1'])
        v2, _ = validate_image(case['img2'])
        
        if not (v1 and v2):
            print(f"❌ Test Failed: Images didn't pass local validation.")
            continue

        # 2. Run Aesthetician
        try:
            raw_res = await compare_skin(case['img1'], case['img2'], history_text="TEST RUN")
            
            # 3. Store the result properly
            log_test_result(case['name'], case['img1'], case['img2'], raw_res)
            print(f"✅ Results stored in test_bench table.")
            
        except Exception as e:
            print(f"❌ API Error: {e}")

if __name__ == "__main__":
    asyncio.run(run_benchmark())
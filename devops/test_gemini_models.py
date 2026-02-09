#!/usr/bin/env python3
"""
Quick test to list available Gemini models for your API key.
"""

import os
import sys

# Add parent to path
sys.path.insert(0, ".")

try:
    import google.generativeai as genai
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY not set!")
        sys.exit(1)
    
    print(f"🔑 API Key: ***{api_key[-4:]}")
    print("\n📋 Listing available models...")
    print("="*60)
    
    genai.configure(api_key=api_key)
    
    for model in genai.list_models():
        if 'generateContent' in model.supported_generation_methods:
            print(f"✅ {model.name}")
            print(f"   Display name: {model.display_name}")
            print(f"   Description: {model.description[:80]}...")
            print()
    
    print("="*60)
    print("\n🧪 Testing a simple API call with gemini-pro...")
    
    try:
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content("Say hello in one word")
        print(f"✅ SUCCESS! Response: {response.text}")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        
        # Try alternative
        print("\n🧪 Trying models/gemini-pro...")
        try:
            model = genai.GenerativeModel('models/gemini-pro')
            response = model.generate_content("Say hello in one word")
            print(f"✅ SUCCESS with models/gemini-pro! Response: {response.text}")
        except Exception as e2:
            print(f"❌ Also failed: {e2}")
    
except ImportError:
    print("❌ google-generativeai not installed")
    print("   Install: pip install google-generativeai")
except Exception as e:
    print(f"❌ Error: {e}")

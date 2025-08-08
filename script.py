#!/usr/bin/env python3
"""
🚀 MCP Chatbot Startup Script
Checks dependencies and starts all components
"""

import os
import sys
import subprocess
import time
from pathlib import Path

def print_banner():
    print("=" * 60)
    print("🤖 MCP CHATBOT STARTUP")
    print("=" * 60)

def check_file_exists(filepath, description):
    """Check if a required file exists"""
    if os.path.exists(filepath):
        print(f"✅ {description}: {filepath}")
        return True
    else:
        print(f"❌ {description} MISSING: {filepath}")
        return False

def check_env_file():
    """Check if .env file exists and has required variables"""
    env_paths = ['.env', 'api/.env']
    
    for env_path in env_paths:
        if os.path.exists(env_path):
            print(f"✅ Environment file found: {env_path}")
            
            # Check for required variables
            with open(env_path, 'r') as f:
                content = f.read()
                
            required_vars = ['GEMINI_API_KEY', 'GOOGLE_API_KEY']
            has_api_key = any(var in content for var in required_vars)
            
            if has_api_key:
                print("✅ Gemini API key configured")
                return True
            else:
                print("⚠️ No Gemini API key found in .env file")
                return False
    
    print("❌ No .env file found!")
    print("📝 Create .env file with your GEMINI_API_KEY")
    return False

def check_python_packages():
    """Check if required Python packages are installed"""
    required_packages = [
        'fastapi',
        'uvicorn',
        'redis',
        'streamlit',
        'httpx',
        'python-dotenv',
        'google-generativeai',
        'mcp'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
            print(f"✅ {package}")
        except ImportError:
            print(f"❌ {package}")
            missing_packages.append(package)
    
    if missing_packages:
        print(f"\n📦 Install missing packages:")
        print(f"pip install {' '.join(missing_packages)}")
        return False
    
    return True

def check_redis():
    """Check if Redis is available"""
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, decode_responses=True)
        r.ping()
        print("✅ Redis connection successful")
        return True
    except Exception as e:
        print(f"❌ Redis not available: {e}")
        print("🐳 Start Redis with: docker run -d -p 6379:6379 redis:alpine")
        return False

def start_api_server():
    """Start the FastAPI server"""
    print("\n🚀 Starting API Server...")
    
    try:
        os.chdir('api')
        process = subprocess.Popen([
            sys.executable, '-m', 'uvicorn', 
            'main:app', 
            '--host', '0.0.0.0', 
            '--port', '8000',
            '--reload'
        ])
        print("✅ API Server started on http://localhost:8000")
        return process
    except Exception as e:
        print(f"❌ Failed to start API server: {e}")
        return None

def start_frontend():
    """Start the Streamlit frontend"""
    print("\n🎨 Starting Frontend...")
    
    try:
        os.chdir('../frontend')
        process = subprocess.Popen([
            sys.executable, '-m', 'streamlit', 'run', 'main.py',
            '--server.port', '8501'
        ])
        print("✅ Frontend started on http://localhost:8501")
        return process
    except Exception as e:
        print(f"❌ Failed to start frontend: {e}")
        return None

def main():
    print_banner()
    
    # Check all requirements
    all_good = True
    
    print("📋 CHECKING REQUIREMENTS...")
    print("-" * 40)
    
    # Check files
    required_files = [
        ('api/main.py', 'API Main File'),
        ('api/memory/redis_memory.py', 'Redis Memory'),
        ('api/utils/simple_router.py', 'Simple Router'),
        ('api/mcp_client.py', 'MCP Client'),
        ('server/server.py', 'MCP Server'),
        ('frontend/main.py', 'Frontend Main'),
        ('frontend/chatbot.py', 'Frontend Chatbot')
    ]
    
    for filepath, description in required_files:
        if not check_file_exists(filepath, description):
            all_good = False
    
    print()
    
    # Check environment
    if not check_env_file():
        all_good = False
    
    print()
    
    # Check packages
    print("📦 CHECKING PYTHON PACKAGES...")
    print("-" * 40)
    if not check_python_packages():
        all_good = False
    
    print()
    
    # Check Redis
    print("🔴 CHECKING REDIS...")
    print("-" * 40)
    redis_ok = check_redis()
    
    if not all_good:
        print("\n❌ SETUP INCOMPLETE!")
        print("Fix the issues above before starting the bot.")
        return
    
    print("\n✅ ALL CHECKS PASSED!")
    
    if not redis_ok:
        print("⚠️ Redis not available - will use SQLite fallback")
    
    print("\n🚀 STARTING SERVICES...")
    print("-" * 40)
    
    processes = []
    
    # Start API server
    api_process = start_api_server()
    if api_process:
        processes.append(('API Server', api_process))
        time.sleep(3)  # Give API time to start
    
    # Start frontend
    frontend_process = start_frontend()
    if frontend_process:
        processes.append(('Frontend', frontend_process))
    
    if processes:
        print("\n🎉 CHATBOT STARTED!")
        print("-" * 40)
        print("📍 API: http://localhost:8000")
        print("📍 API Docs: http://localhost:8000/docs")
        print("🎨 Frontend: http://localhost:8501")
        print("\nPress Ctrl+C to stop all services")
        
        try:
            # Keep running until interrupted
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\n🛑 Stopping services...")
            for name, process in processes:
                try:
                    process.terminate()
                    print(f"✅ Stopped {name}")
                except:
                    print(f"⚠️ Could not stop {name}")
    else:
        print("\n❌ Failed to start services!")

if __name__ == "__main__":
    main()
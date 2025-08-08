# debug_redis.py - Simple Redis test (FIXED)
from dotenv import load_dotenv
import os

print("🔍 SIMPLE REDIS TEST")
print("=" * 30)

# Step 1: Find and load .env file
print("1. Looking for .env file...")

# Try multiple locations
env_locations = [
    '.env',                    # Current directory
    '../.env',                 # Parent directory  
    '../../.env',              # Two levels up
    'api/.env',                # In api subfolder
]

env_found = False
env_path = None

for location in env_locations:
    if os.path.exists(location):
        env_path = os.path.abspath(location)
        print(f"✅ Found .env at: {env_path}")
        load_dotenv(dotenv_path=location)
        env_found = True
        break

if not env_found:
    print("❌ .env file NOT found in any of these locations:")
    for loc in env_locations:
        abs_path = os.path.abspath(loc)
        print(f"   {abs_path}")
    print("\nCreate .env file with:")
    print("REDIS_HOST=localhost")
    print("REDIS_PORT=6379") 
    print("REDIS_PASSWORD=")
    print("REDIS_DB=0")
    exit(1)

# Step 2: Check if redis is installed
print("\n2. Checking if redis package is installed...")
try:
    import redis
    print(f"✅ Redis installed: {redis.__version__}")
except ImportError:
    print("❌ Redis NOT installed")
    print("Fix: pip install redis")
    exit(1)

# Step 3: Show environment variables
print("\n3. Checking environment variables...")
env_vars = {
    'REDIS_HOST': os.getenv('REDIS_HOST'),
    'REDIS_PORT': os.getenv('REDIS_PORT'),
    'REDIS_PASSWORD': os.getenv('REDIS_PASSWORD'), 
    'REDIS_DB': os.getenv('REDIS_DB')
}

for key, value in env_vars.items():
    if value is not None:
        if 'PASSWORD' in key and value:
            masked = '*' * len(value) if len(value) > 0 else '(empty)'
            print(f"✅ {key}: {masked}")
        else:
            print(f"✅ {key}: {value}")
    else:
        print(f"❌ {key}: NOT SET")

# Step 4: Test Redis connection
print("\n4. Testing Redis connection...")

# Get connection details
host = os.getenv('REDIS_HOST', 'localhost')
port = int(os.getenv('REDIS_PORT', 6379))
password = os.getenv('REDIS_PASSWORD') or None  # Convert empty string to None
db = int(os.getenv('REDIS_DB', 0))

print(f"📡 Connecting to {host}:{port} (db={db})...")

try:
    r = redis.Redis(
        host=host,
        port=port, 
        password=password,
        db=db,
        decode_responses=True,
        socket_timeout=5,
        socket_connect_timeout=5
    )
    
    # Test connection
    response = r.ping()
    print("✅ Connection successful!")
    
    # Test basic operations
    r.set('test_key', 'Hello Redis!')
    value = r.get('test_key')
    r.delete('test_key')
    print(f"✅ Read/Write test successful: {value}")
    
except redis.ConnectionError as e:
    print(f"❌ Connection failed: {e}")
    print("\n🔧 Possible fixes:")
    print("   - Start Redis server: docker run -d -p 6379:6379 redis:alpine")
    print("   - Check if Redis is running on the specified host/port")
    print("   - Verify firewall settings")
    
except redis.AuthenticationError as e:
    print(f"❌ Authentication failed: {e}")
    print("\n🔧 Possible fixes:")
    print("   - Check REDIS_PASSWORD in .env file")
    print("   - Try leaving REDIS_PASSWORD empty for local Redis")
    
except redis.TimeoutError as e:
    print(f"❌ Connection timeout: {e}")
    print("\n🔧 Possible fixes:")
    print("   - Redis server might be slow to respond")
    print("   - Check network connectivity")
    
except Exception as e:
    print(f"❌ Unexpected error: {e}")
    print(f"   Error type: {type(e).__name__}")

print(f"\n📁 Current directory: {os.getcwd()}")
print(f"📄 .env file used: {env_path}")
print("\nDone! ✨")
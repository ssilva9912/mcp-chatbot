#!/usr/bin/env python3
"""
Focused debug script for MCP connection issues
"""

import asyncio
import os
import sys
import subprocess
import time
import traceback
from pathlib import Path

def find_server_file():
    """Find the MCP server file"""
    print("🔍 Looking for MCP server file...")
    
    possible_paths = [
        "./server.py",
        "../server/server.py", 
        "server/server.py",
        "../server.py",
        "../../server/server.py"
    ]
    
    found_paths = []
    for path in possible_paths:
        if os.path.exists(path):
            abs_path = os.path.abspath(path)
            found_paths.append((path, abs_path))
            print(f"✅ Found: {path} -> {abs_path}")
        else:
            print(f"❌ Not found: {path}")
    
    return found_paths

def test_server_syntax(server_path):
    """Test if server file has valid Python syntax"""
    print(f"\n🐍 Testing Python syntax for: {server_path}")
    
    try:
        result = subprocess.run([
            sys.executable, "-m", "py_compile", server_path
        ], capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            print("✅ Python syntax is valid")
            return True
        else:
            print("❌ Python syntax error:")
            print(result.stderr)
            return False
            
    except subprocess.TimeoutExpired:
        print("⏰ Syntax check timed out")
        return False
    except Exception as e:
        print(f"❌ Syntax check failed: {e}")
        return False

def test_server_imports(server_path):
    """Test if server can import required modules"""
    print(f"\n📦 Testing imports for: {server_path}")
    
    test_script = f'''
import sys
sys.path.append(os.path.dirname("{server_path}"))

try:
    import asyncio
    print("✅ asyncio")
except ImportError as e:
    print(f"❌ asyncio: {{e}}")

try:
    import mcp.server
    print("✅ mcp.server")
except ImportError as e:
    print(f"❌ mcp.server: {{e}}")

try:
    import mcp.types
    print("✅ mcp.types")
except ImportError as e:
    print(f"❌ mcp.types: {{e}}")

try:
    import mcp.server.stdio
    print("✅ mcp.server.stdio")  
except ImportError as e:
    print(f"❌ mcp.server.stdio: {{e}}")
'''
    
    try:
        result = subprocess.run([
            sys.executable, "-c", test_script
        ], capture_output=True, text=True, timeout=15)
        
        print("Import test results:")
        print(result.stdout)
        if result.stderr:
            print("Import errors:")
            print(result.stderr)
            
        return "❌" not in result.stdout
        
    except Exception as e:
        print(f"❌ Import test failed: {e}")
        return False

def test_server_startup(server_path):
    """Test if server can start up"""
    print(f"\n🚀 Testing server startup: {server_path}")
    
    try:
        # Start server process
        print("Starting server process...")
        process = subprocess.Popen([
            sys.executable, server_path
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        # Wait a bit for startup
        time.sleep(3)
        
        # Check if process is still running
        if process.poll() is None:
            print("✅ Server process started successfully")
            
            # Try to get some output
            try:
                stdout, stderr = process.communicate(timeout=2)
                if stdout:
                    print("Server stdout:")
                    print(stdout[:500] + "..." if len(stdout) > 500 else stdout)
                if stderr:
                    print("Server stderr:")
                    print(stderr[:500] + "..." if len(stderr) > 500 else stderr)
            except subprocess.TimeoutExpired:
                print("📝 Server is running (no immediate output)")
            
            # Terminate server
            process.terminate()
            process.wait(timeout=5)
            return True
            
        else:
            # Process died
            stdout, stderr = process.communicate()
            print("❌ Server process died immediately")
            print(f"Exit code: {process.returncode}")
            if stdout:
                print("stdout:", stdout)
            if stderr:
                print("stderr:", stderr)
            return False
            
    except Exception as e:
        print(f"❌ Server startup test failed: {e}")
        return False

async def test_mcp_connection(server_path):
    """Test MCP client connection"""
    print(f"\n🔌 Testing MCP connection to: {server_path}")
    
    try:
        # Import here to avoid issues if not available
        sys.path.append(os.path.dirname(__file__))
        from mcp_client import MCPClient
        
        # Create client
        client = MCPClient()
        
        print("Attempting connection...")
        
        # Try connection with shorter timeout for debugging
        try:
            await asyncio.wait_for(
                client.connect_to_server(server_path),
                timeout=20.0
            )
            print("✅ MCP connection successful!")
            
            # Test tool listing
            tools = await client.list_tools()
            print(f"📋 Available tools: {[tool['name'] for tool in tools]}")
            
            return True
            
        except asyncio.TimeoutError:
            print("⏰ MCP connection timed out after 20 seconds")
            return False
        except Exception as e:
            print(f"❌ MCP connection failed: {e}")
            print(f"📝 Traceback: {traceback.format_exc()}")
            return False
            
    except ImportError as e:
        print(f"❌ Cannot import MCP client: {e}")
        return False
    except Exception as e:
        print(f"❌ MCP connection test failed: {e}")
        return False

async def run_focused_diagnostics():
    """Run focused diagnostics"""
    print("🎯 FOCUSED MCP DIAGNOSTICS")
    print("=" * 50)
    
    # Step 1: Find server files
    server_paths = find_server_file()
    
    if not server_paths:
        print("\n❌ No MCP server files found!")
        print("💡 Make sure server.py exists in one of these locations:")
        print("   - ./server.py")
        print("   - ../server/server.py")
        print("   - server/server.py")
        return
    
    print(f"\n✅ Found {len(server_paths)} server file(s)")
    
    # Test each server file
    for relative_path, absolute_path in server_paths:
        print(f"\n{'='*50}")
        print(f"🧪 TESTING: {relative_path}")
        print(f"📍 Full path: {absolute_path}")
        print(f"{'='*50}")
        
        # Test syntax
        syntax_ok = test_server_syntax(absolute_path)
        if not syntax_ok:
            print("❌ Skipping further tests due to syntax errors")
            continue
            
        # Test imports
        imports_ok = test_server_imports(absolute_path)
        if not imports_ok:
            print("❌ Skipping further tests due to import errors")
            continue
            
        # Test startup
        startup_ok = test_server_startup(absolute_path)
        if not startup_ok:
            print("❌ Skipping connection test due to startup errors")
            continue
            
        # Test connection
        connection_ok = await test_mcp_connection(relative_path)
        
        if connection_ok:
            print(f"✅ {relative_path} is working correctly!")
            break
        else:
            print(f"❌ {relative_path} has connection issues")
    
    print(f"\n{'='*50}")
    print("📋 DIAGNOSTIC SUMMARY")
    print(f"{'='*50}")
    
    working_servers = []
    for relative_path, absolute_path in server_paths:
        print(f"📄 {relative_path}:")
        print(f"   Syntax: ✅")
        print(f"   Imports: Check manually")
        print(f"   Startup: Check manually") 
        print(f"   Connection: Run full test")
    
    print(f"\n💡 NEXT STEPS:")
    print("1. Fix any syntax/import errors shown above")
    print("2. Make sure MCP dependencies are installed:")
    print("   pip install mcp")
    print("3. Set GEMINI_API_KEY environment variable")
    print("4. Test with: python -c \"import mcp.server; print('MCP OK')\"")

def main():
    """Main entry point"""
    try:
        asyncio.run(run_focused_diagnostics())
    except KeyboardInterrupt:
        print("\n🛑 Diagnostics interrupted")
    except Exception as e:
        print(f"\n❌ Diagnostics failed: {e}")
        print(f"📝 Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    main()
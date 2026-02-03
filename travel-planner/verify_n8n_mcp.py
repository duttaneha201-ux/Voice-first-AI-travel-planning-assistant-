#!/usr/bin/env python3
"""
Verification script for n8n MCP server setup in Cursor.

This script checks:
1. MCP configuration file exists
2. Environment variables are set
3. Node.js is available
4. n8n API connectivity (optional)
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def check_mcp_config() -> tuple[bool, str]:
    """Check if .cursor/mcp.json exists and is valid."""
    project_root = Path(__file__).parent
    mcp_config_path = project_root / ".cursor" / "mcp.json"
    
    if not mcp_config_path.exists():
        return False, f"[X] MCP config file not found at: {mcp_config_path}"
    
    try:
        with open(mcp_config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        
        if "mcpServers" not in config:
            return False, "[X] MCP config missing 'mcpServers' key"
        
        if "n8n-workflow-builder" not in config["mcpServers"]:
            return False, "[X] MCP config missing 'n8n-workflow-builder' server"
        
        server_config = config["mcpServers"]["n8n-workflow-builder"]
        if "@makafeli/n8n-workflow-builder" not in str(server_config.get("args", [])):
            return False, "[X] MCP config doesn't use @makafeli/n8n-workflow-builder"
        
        return True, f"[OK] MCP config file found and valid: {mcp_config_path}"
    except json.JSONDecodeError as e:
        return False, f"[X] MCP config file has invalid JSON: {e}"
    except Exception as e:
        return False, f"[X] Error reading MCP config: {e}"


def check_nodejs() -> tuple[bool, str]:
    """Check if Node.js is installed."""
    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            return True, f"[OK] Node.js installed: {version}"
        return False, "[X] Node.js not found (node command failed)"
    except FileNotFoundError:
        return False, "[X] Node.js not installed (node command not found)"
    except Exception as e:
        return False, f"[X] Error checking Node.js: {e}"


def check_env_vars() -> tuple[bool, list[str]]:
    """Check if required environment variables are set."""
    results = []
    all_ok = True
    
    n8n_url = os.getenv("N8N_API_URL", "").strip()
    n8n_key = os.getenv("N8N_API_KEY", "").strip()
    
    if n8n_url:
        results.append(f"[OK] N8N_API_URL is set: {n8n_url[:30]}...")
    else:
        results.append("[X] N8N_API_URL is not set")
        all_ok = False
    
    if n8n_key:
        results.append(f"[OK] N8N_API_KEY is set: {n8n_key[:10]}...")
    else:
        results.append("[X] N8N_API_KEY is not set")
        all_ok = False
    
    return all_ok, results


def check_n8n_connectivity() -> tuple[bool, str]:
    """Optionally test n8n API connectivity."""
    n8n_url = os.getenv("N8N_API_URL", "").strip()
    n8n_key = os.getenv("N8N_API_KEY", "").strip()
    
    if not n8n_url or not n8n_key:
        return False, "[!] Skipping connectivity test (env vars not set)"
    
    try:
        import requests
        api_url = f"{n8n_url.rstrip('/')}/api/v1/workflows"
        response = requests.get(
            api_url,
            headers={"X-N8N-API-KEY": n8n_key},
            timeout=10
        )
        
        if response.status_code == 200:
            return True, f"[OK] n8n API is accessible at {n8n_url}"
        elif response.status_code == 401:
            return False, f"[X] n8n API authentication failed (invalid API key?)"
        else:
            return False, f"[X] n8n API returned status {response.status_code}"
    except ImportError:
        return False, "[!] Skipping connectivity test (requests library not installed)"
    except Exception as e:
        return False, f"[X] Error connecting to n8n API: {e}"


def main():
    """Run all verification checks."""
    # Set UTF-8 encoding for Windows compatibility
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    
    print("Verifying n8n MCP Server Setup for Cursor\n")
    print("=" * 60)
    
    all_checks_passed = True
    
    # Check MCP config
    print("\n1. Checking MCP Configuration File...")
    ok, msg = check_mcp_config()
    print(f"   {msg}")
    if not ok:
        all_checks_passed = False
    
    # Check Node.js
    print("\n2. Checking Node.js Installation...")
    ok, msg = check_nodejs()
    print(f"   {msg}")
    if not ok:
        all_checks_passed = False
    
    # Check environment variables
    print("\n3. Checking Environment Variables...")
    ok, msgs = check_env_vars()
    for msg in msgs:
        print(f"   {msg}")
    if not ok:
        all_checks_passed = False
    
    # Optional connectivity check
    print("\n4. Testing n8n API Connectivity (Optional)...")
    ok, msg = check_n8n_connectivity()
    print(f"   {msg}")
    # Don't fail overall if connectivity check fails (might be network issue)
    
    print("\n" + "=" * 60)
    
    if all_checks_passed:
        print("\n[OK] All critical checks passed!")
        print("\nNext steps:")
        print("   1. Restart Cursor IDE completely")
        print("   2. Open Cursor Chat (Ctrl+L)")
        print("   3. Try: 'List my n8n workflows'")
        print("   4. Try: 'Create a new n8n workflow'")
        return 0
    else:
        print("\n[X] Some checks failed. Please fix the issues above.")
        print("\nSee CURSOR_MCP_SETUP.md for detailed setup instructions.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Quick test runner for auto-captcha-solver integration test.
Usage: python run_integration_test.py
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).parent
print(f"Working in: {REPO}")

# 1. Ensure virtualenv
venv = REPO / ".venv"
if not venv.exists():
    print("Creating virtualenv...")
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)

pip = str(venv / "bin" / "pip")
python = str(venv / "bin" / "python")

# 2. Install deps (editable + dev)
print("Installing package + dev deps...")
subprocess.run([pip, "install", "-e", ".", "--quiet"], check=True)
subprocess.run([pip, "install", "pytest", "pytest-asyncio", "playwright", "--quiet"], check=True)

# 3. Install Playwright browsers
print("Installing Playwright browsers...")
subprocess.run([python, "-m", "playwright", "install", "chromium"], check=True)

# 4. Run the integration test
print("\n=== Running integration_browser_test.py ===")
result = subprocess.run(
    [python, "-m", "pytest",
     "tests/integration_browser_test.py",
     "-v", "--tb=short"],
    cwd=REPO
)
sys.exit(result.returncode)

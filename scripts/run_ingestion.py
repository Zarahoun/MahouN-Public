#!/usr/bin/env python3
"""
Simple ingestion runner
"""

import subprocess
import sys
import os

def main():
    # Change to project directory
    os.chdir('/home/haji/Desktop/KingMahouN')
    
    # Activate venv and run
    cmd = [
        'bash', '-c',
        'source venv/bin/activate && python scripts/build_judgment_kg.py --file data/ara_top_333/judgments_top_333.json --batch-size 50'
    ]
    
    print("🚀 Starting judgment ingestion...")
    print("Command:", ' '.join(cmd))
    print()
    
    # Run with real-time output
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    
    for line in iter(process.stdout.readline, ''):
        print(line.rstrip())
        sys.stdout.flush()
    
    process.wait()
    
    print()
    print(f"✅ Process completed with exit code: {process.returncode}")
    
    return process.returncode

if __name__ == '__main__':
    sys.exit(main())
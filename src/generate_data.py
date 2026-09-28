import os
import sys

# Ensure backend and workspace directories are on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(BASE_DIR, "backend") not in sys.path:
    sys.path.append(os.path.join(BASE_DIR, "backend"))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from scripts.generate_data import generate_all

if __name__ == "__main__":
    print("=" * 60)
    print("Hospital Accountability System: Synthetic Data Generator")
    print("=" * 60)
    generate_all()

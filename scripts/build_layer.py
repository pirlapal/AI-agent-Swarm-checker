"""Prepare the Python 3.12 x86_64 presigner layer; installs packages, never deploys."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
LAYER = ROOT / 'backend' / 'lambda-layer-agentcore'
TARGET = LAYER / 'python'
TARGET.mkdir(exist_ok=True)
if any(TARGET.iterdir()):
    sys.exit('Layer target is not empty. Use a fresh checkout or clear generated layer files before rebuilding.')
subprocess.run([sys.executable, '-m', 'pip', 'install', '--platform', 'manylinux2014_x86_64', '--implementation', 'cp', '--python-version', '3.12', '--only-binary=:all:', '--target', str(TARGET), '-r', str(LAYER / 'requirements.txt')], check=True)

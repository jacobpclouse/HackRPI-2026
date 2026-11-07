#!/usr/bin/env python3
"""Set up the virtual environment and start DarkWatch.

    python run.py               # install if needed, then serve on :8741
    python run.py --dev         # also install job + dev dependencies (tests, lint)
    python run.py --port 9000 --no-anim

Works on macOS, Linux, and Windows. The venv is rebuilt only when the
requirements or constraints files change.
"""

import argparse
import hashlib
import os
import platform
import subprocess
import sys
import time
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
APP = BACKEND / "app.py"
DEFAULT_VENV = ".venv"
DEFAULT_PORT = 8741
STAMP = ".darkwatch-requirements.sha256"
ANIMATION_S = 1.5

FRAMES = [
    r'''
 /$$   /$$                     /$$       /$$$$$$$  /$$$$$$$  /$$$$$$
| $$  | $$                    | $$      | $$__  $$| $$__  $$|_  $$_/
| $$  | $$  /$$$$$$   /$$$$$$$| $$   /$$| $$  \ $$| $$  \ $$  | $$  
| $$$$$$$$ |____  $$ /$$_____/| $$  /$$/| $$$$$$$/| $$$$$$$/  | $$  
| $$__  $$  /$$$$$$$| $$      | $$$$$$/ | $$__  $$| $$____/   | $$  
| $$  | $$ /$$__  $$| $$      | $$_  $$ | $$  \ $$| $$        | $$  
| $$  | $$|  $$$$$$$|  $$$$$$$| $$ \  $$| $$  | $$| $$       /$$$$$$
|__/  |__/ \_______/ \_______/|__/  \__/|__/  |__/|__/      |______/

''',  # top right
    r'''
 __    __                      __        _______   _______  ______ 
|  \  |  \                    |  \      |       \ |       \|      \
| $$  | $$  ______    _______ | $$   __ | $$$$$$$\| $$$$$$$\$$$$$$
| $$__| $$ |      \  /       \| $$  /  \| $$__| $$| $$__/ $$ | $$  
| $$    $$  \$$$$$$\|  $$$$$$$| $$_/  $$| $$    $$| $$    $$ | $$  
| $$$$$$$$ /      $$| $$      | $$   $$ | $$$$$$$\| $$$$$$$  | $$  
| $$  | $$|  $$$$$$$| $$_____ | $$$$$$\ | $$  | $$| $$      _| $$_ 
| $$  | $$ \$$    $$ \$$     \| $$  \$$\| $$  | $$| $$     |   $$ \
 \$$   \$$  \$$$$$$$  \$$$$$$$ \$$   \$$ \$$   \$$ \$$      \$$$$$$
                                                                   
''',  # bottom right
    r'''
 __    __                      __        _______   _______   ______ 
/  |  /  |                    /  |      /       \ /       \ /      |
$$ |  $$ |  ______    _______ $$ |   __ $$$$$$$  |$$$$$$$  |$$$$$$/ 
$$ |__$$ | /      \  /       |$$ |  /  |$$ |__$$ |$$ |__$$ |  $$ |  
$$    $$ | $$$$$$  |/$$$$$$$/ $$ |_/$$/ $$    $$< $$    $$/   $$ |  
$$$$$$$$ | /    $$ |$$ |      $$   $$<  $$$$$$$  |$$$$$$$/    $$ |  
$$ |  $$ |/$$$$$$$ |$$ \_____ $$$$$$  \ $$ |  $$ |$$ |       _$$ |_ 
$$ |  $$ |$$    $$ |$$       |$$ | $$  |$$ |  $$ |$$ |      / $$   |
$$/   $$/  $$$$$$$/  $$$$$$$/ $$/   $$/ $$/   $$/ $$/       $$$$$$/ 
                                                                    
''',  # bottom left
    r'''
$$\   $$\                     $$\       $$$$$$$\  $$$$$$$\ $$$$$$\ 
$$ |  $$ |                    $$ |      $$  __$$\ $$  __$$\_$$  _|
$$ |  $$ | $$$$$$\   $$$$$$$\ $$ |  $$\ $$ |  $$ |$$ |  $$ | $$ |  
$$$$$$$$ | \____$$\ $$  _____|$$ | $$  |$$$$$$$  |$$$$$$$  | $$ |  
$$  __$$ | $$$$$$$ |$$ /      $$$$$$  / $$  __$$< $$  ____/  $$ |  
$$ |  $$ |$$  __$$ |$$ |      $$  _$$<  $$ |  $$ |$$ |       $$ |  
$$ |  $$ |\$$$$$$$ |\$$$$$$$\ $$ | \$$\ $$ |  $$ |$$ |     $$$$$$\ 
\__|  \__| \_______| \_______|\__|  \__|\__|  \__|\__|     \______|
                                                                   
''',  # top left
]


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def logo_animation(text="LOADING", seconds=ANIMATION_S):
    """The HackRPI logo, rotating through its four corners. Capped at `seconds`."""
    start = time.time()
    while time.time() - start < seconds:
        for frame in FRAMES:
            if time.time() - start >= seconds:
                break
            clear_screen()
            print("Designed and Built for HackRPI 2026 - In the Clouds!\n")
            print(frame)
            time.sleep(0.2)
    clear_screen()
    print(text)


def venv_python(venv_dir):
    if platform.system() == "Windows":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def activate_hint(venv_dir):
    if platform.system() == "Windows":
        return str(venv_dir / "Scripts" / "Activate.ps1")
    return f"source {venv_dir / 'bin' / 'activate'}"


def requirement_files(dev):
    names = ["requirements.txt", "constraints.txt"]
    if dev:
        names += ["requirements-job.txt", "requirements-dev.txt"]
    return [BACKEND / name for name in names]


def requirements_hash(dev):
    digest = hashlib.sha256()
    digest.update(b"dev" if dev else b"app")
    digest.update(sys.version.encode())
    for path in requirement_files(dev):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def create_venv(venv_dir):
    """Create the venv if missing and return its interpreter path."""
    python = venv_python(venv_dir)
    if not python.exists():
        print(f"> Creating virtual environment at {venv_dir}")
        venv.create(venv_dir, with_pip=True)
        print(f"    ... to activate manually: {activate_hint(venv_dir)}")
    return python


def install_requirements(venv_dir, dev=False, verbose=False):
    python = create_venv(venv_dir)
    stamp = venv_dir / STAMP
    wanted = requirements_hash(dev)
    if stamp.exists() and stamp.read_text().strip() == wanted:
        print("> Dependencies already installed")
        return python
    # A full dev install also satisfies the app-only check.
    if not dev and stamp.exists() and stamp.read_text().strip() == requirements_hash(True):
        print("> Dependencies already installed")
        return python
    req = BACKEND / ("requirements-dev.txt" if dev else "requirements.txt")
    print(f"> Installing {req.relative_to(ROOT)} into {venv_dir.name}, please be patient")
    quiet = [] if verbose else ["-q"]
    subprocess.run([str(python), "-m", "pip", "install", *quiet, "-U", "pip"], check=True)
    result = subprocess.run([str(python), "-m", "pip", "install", *quiet, "-r", str(req)])
    if result.returncode != 0:
        sys.exit("pip install failed. Re-run with --verbose to see the full output.")
    stamp.write_text(wanted)
    return python


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="port to serve on (default 8741)")
    parser.add_argument("--dev", action="store_true", help="also install job and dev dependencies")
    parser.add_argument("--venv", default=DEFAULT_VENV, help="virtual environment directory")
    parser.add_argument("--no-anim", action="store_true", help="skip the logo animation")
    parser.add_argument("--install-only", action="store_true", help="set up the venv and exit")
    parser.add_argument("--verbose", action="store_true", help="show pip output")
    args = parser.parse_args()

    if not args.no_anim and sys.stdout.isatty():
        logo_animation("--- === --- START DARKWATCH --- === ---")

    venv_dir = (ROOT / args.venv).resolve()
    print(f"> {platform.system()} · Python {platform.python_version()}")
    python = install_requirements(venv_dir, dev=args.dev, verbose=args.verbose)
    if args.install_only:
        return
    print(f"> Serving DarkWatch on http://127.0.0.1:{args.port}")
    env = dict(os.environ, PORT=str(args.port))
    env.pop("DATABRICKS_APP_PORT", None)
    try:
        subprocess.run([str(python), str(APP)], cwd=ROOT, env=env)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

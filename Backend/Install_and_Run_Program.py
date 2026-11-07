import argparse
import platform
import subprocess
import os
import venv
import time

NAME_OF_SCRIPT_TO_RUN = "mainBackend.py"
VIRT_ENV_NAME = ".venv"
PACKAGES_TO_INSTALL_ARRAY = ["pandas"]# you can just keep adding to this like "pandas==2.1", "PIL==1.01", etc


def clear_screen():
    # Clears the terminal screen
    os.system('cls' if os.name == 'nt' else 'clear')

# --- Function to print out my Logo ---
def LogoAnimation(inputText='LOADING'):
    frames = [
        '''
 /$$   /$$                     /$$       /$$$$$$$  /$$$$$$$  /$$$$$$
| $$  | $$                    | $$      | $$__  $$| $$__  $$|_  $$_/
| $$  | $$  /$$$$$$   /$$$$$$$| $$   /$$| $$  \ $$| $$  \ $$  | $$  
| $$$$$$$$ |____  $$ /$$_____/| $$  /$$/| $$$$$$$/| $$$$$$$/  | $$  
| $$__  $$  /$$$$$$$| $$      | $$$$$$/ | $$__  $$| $$____/   | $$  
| $$  | $$ /$$__  $$| $$      | $$_  $$ | $$  \ $$| $$        | $$  
| $$  | $$|  $$$$$$$|  $$$$$$$| $$ \  $$| $$  | $$| $$       /$$$$$$
|__/  |__/ \_______/ \_______/|__/  \__/|__/  |__/|__/      |______/

''',  # top right

        '''
 __    __                      __        _______   _______  ______ 
|  \  |  \                    |  \      |       \ |       \|      \\
| $$  | $$  ______    _______ | $$   __ | $$$$$$$\| $$$$$$$\\$$$$$$
| $$__| $$ |      \  /       \| $$  /  \| $$__| $$| $$__/ $$ | $$  
| $$    $$  \$$$$$$\|  $$$$$$$| $$_/  $$| $$    $$| $$    $$ | $$  
| $$$$$$$$ /      $$| $$      | $$   $$ | $$$$$$$\| $$$$$$$  | $$  
| $$  | $$|  $$$$$$$| $$_____ | $$$$$$\ | $$  | $$| $$      _| $$_ 
| $$  | $$ \$$    $$ \$$     \| $$  \$$\| $$  | $$| $$     |   $$ \\
 \$$   \$$  \$$$$$$$  \$$$$$$$ \$$   \$$ \$$   \$$ \$$      \$$$$$$
                                                                   
''',  # bottom right

        '''
 __    __                      __        _______   _______   ______ 
/  |  /  |                    /  |      /       \ /       \ /      |
$$ |  $$ |  ______    _______ $$ |   __ $$$$$$$  |$$$$$$$  |$$$$$$/ 
$$ |__$$ | /      \  /       |$$ |  /  |$$ |__$$ |$$ |__$$ |  $$ |  
$$    $$ | $$$$$$  |/$$$$$$$/ $$ |_/$$/ $$    $$< $$    $$/   $$ |  
$$$$$$$$ | /    $$ |$$ |      $$   $$<  $$$$$$$  |$$$$$$$/    $$ |  
$$ |  $$ |/$$$$$$$ |$$ \_____ $$$$$$  \ $$ |  $$ |$$ |       _$$ |_ 
$$ |  $$ |$$    $$ |$$       |$$ | $$  |$$ |  $$ |$$ |      / $$   |
$$/   $$/  $$$$$$$/  $$$$$$$/ $$/   $$/ $$/   $$/ $$/       $$$$$$/ 
                                                                    
''', # bottom left 

        '''
$$\   $$\                     $$\       $$$$$$$\  $$$$$$$\ $$$$$$\ 
$$ |  $$ |                    $$ |      $$  __$$\ $$  __$$\\_$$  _|
$$ |  $$ | $$$$$$\   $$$$$$$\ $$ |  $$\ $$ |  $$ |$$ |  $$ | $$ |  
$$$$$$$$ | \____$$\ $$  _____|$$ | $$  |$$$$$$$  |$$$$$$$  | $$ |  
$$  __$$ | $$$$$$$ |$$ /      $$$$$$  / $$  __$$< $$  ____/  $$ |  
$$ |  $$ |$$  __$$ |$$ |      $$  _$$<  $$ |  $$ |$$ |       $$ |  
$$ |  $$ |\$$$$$$$ |\$$$$$$$\ $$ | \$$\ $$ |  $$ |$$ |     $$$$$$\ 
\__|  \__| \_______| \_______|\__|  \__|\__|  \__|\__|     \______|
                                                                   
''' # top left

    ]

    start_time = time.time()
    while time.time() - start_time < 2:
        for frame in frames:
            clear_screen()
            print("Designed and Built for HackRPI 2026 - In the Clouds!\n")
            print(frame)
            time.sleep(0.2)

    # After the animation, clear the screen and show "LOADING"
    clear_screen()
    print(inputText)



# Create a virtual environment, don't activate it
def create_venv(venv_dir=VIRT_ENV_NAME):
    venv.create(venv_dir, with_pip=True)
    print("===========--------===========--------===========")
    print(f"> Virtual Environment Created at {venv_dir}")

    # Determine the activation script path (for user info only)
    if platform.system() == "Windows":
        activate_script = os.path.join(venv_dir, "Scripts", "Activate.ps1")
        python_path = os.path.join(venv_dir, "Scripts", "python.exe")
    else:
        activate_script = os.path.join("source ", venv_dir, "bin", "activate")
        python_path = os.path.join(venv_dir, "bin", "activate")

    print(f"    ... to activate manually in terminal, use: {activate_script}")
    print("===========--------===========--------===========")

    return python_path


# Get path to the virtual environments pip -- might not need this
def get_venv_pip(venv_dir=VIRT_ENV_NAME):
    if platform.system() == "Windows":
        return os.path.join(venv_dir, "Scripts", "pip.exe")
    else:
        return os.path.join(venv_dir, "bin", "pip")
    

# Install Packages using the virtual environment's pip with trusted hosts
def pip_install_packages(venv_dir,packages,extra_index_url=None, verbose=True, pre=False):
    print(f"Install Packages in {VIRT_ENV_NAME}'s pip using trusted hosts, please be patient:")

    pip_path = get_venv_pip(venv_dir)

    # Define Trusted Hosts:
    trusted_hosts = [
        "--trusted-host", "pypi.org",
        "--trusted-host", "pypi.python.org",
        "--trusted-host", "files.pythonhosted.org",
        "--trusted-host", "download.pytorch.org"
    ]
    
    for package in packages:
        try:
            print(f"    ... installing {package}")

            # base command
            cmd = [pip_path, "install"]

            # add trusted hosts
            cmd.extend(trusted_hosts)

            if pre:
                cmd.append("--pre")
            
            # add '-q' if not verbose
            if not verbose:
                cmd.append("-q")

            # add package name
            cmd.append(package)

            # add extra_index_url if it exists
            if extra_index_url:
                cmd.extend(["--extra-index-url",extra_index_url])

            if verbose:
                print(cmd)
            
            # run the command and capture the output
            result = subprocess.run(cmd, capture_output=not verbose, text=True)

            if result.returncode != 0:
                print(f"Error installing {package}:")
                print(result.stderr)

        except Exception as e:
            print(f"failed to install {package}: {e}")

    return

def install_requirements(venv_dir=VIRT_ENV_NAME,verbose=True):
    # Detect System
    os_system = platform.system()
    print("===========--------===========--------===========")
    print(f"> Operating System detected: {os_system}")
    print(f"> Creating / Updating {VIRT_ENV_NAME} virtual environment, might take a sec...")

    # Create virtual environment
    create_venv(venv_dir)

    pip_install_packages(venv_dir, PACKAGES_TO_INSTALL_ARRAY, verbose=verbose)
    print("===========--------===========--------===========")


# run a python script using the virtual environment's interpreter
def run_script_in_venv(venv_dir,script_path, *args):
    if platform.system() == "Windows":
        python_path = os.path.join(venv_dir, "Scripts", "python.exe")
    else:
        python_path = os.path.join(venv_dir, "bin", "python")

    cmd = [python_path, script_path] + list(args)
    subprocess.run(cmd)

if __name__ == "__main__":
    LogoAnimation("--- === --- START BACKEND --- === ---")

    parser = argparse.ArgumentParser()
    parser.add_argument('--verbose', action='store_true',
                        help='print pip install stuff')
    
    parser.add_argument('--venv', default=VIRT_ENV_NAME,
                        help='virtual environment directory name')
    args = parser.parse_args()

    # Setup Virt environment
    install_requirements(venv_dir=args.venv, verbose=args.verbose)

    # Run the target script if requested
    print(f" Running Target Script: {NAME_OF_SCRIPT_TO_RUN}")
    print("===========--------===========--------===========")

    run_script_in_venv(args.venv,NAME_OF_SCRIPT_TO_RUN)

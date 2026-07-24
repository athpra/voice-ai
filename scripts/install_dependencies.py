"""Bootstrap task: installs requirements.txt into the CML session/application
environment before the seed-data and start_application tasks run."""

import subprocess
import sys

if __name__ == "__main__":
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)

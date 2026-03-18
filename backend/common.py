"""Modal environment config for backend workers.

This project does not currently execute via Modal in local dev, but this file keeps
runtime package requirements explicit for deployment parity.
"""

import modal

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("potrace")
    .pip_install_from_requirements("requirements.txt")
)

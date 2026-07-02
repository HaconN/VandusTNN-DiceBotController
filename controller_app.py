"""Entry point for the packaged desktop controller (see build/controller.spec).
Run directly with `python controller_app.py`, or build into DiceBotController.exe
with PyInstaller — see README.md for the exact build command.
"""

from gui.controller import main

if __name__ == "__main__":
    main()

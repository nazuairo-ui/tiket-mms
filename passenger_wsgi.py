import sys
import os

# Add the application directory to the Python path
INTERP = os.path.expanduser("~/virtualenv/tiket-mms/3.10/bin/python3")
if sys.executable != INTERP:
    try:
        os.execl(INTERP, INTERP, *sys.argv)
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(__file__))

from app import app as application

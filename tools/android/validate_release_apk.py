#!/usr/bin/env python3
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.android.apk.validate_release_apk import *

if __name__ == '__main__':
    from tools.android.apk.validate_release_apk import main
    main()

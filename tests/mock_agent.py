#!/usr/bin/env python3
from pathlib import Path
p=Path("app.py")
if p.exists(): p.write_text(p.read_text().replace("return a - b", "return a + b"))
else:
    p=Path("greet.sh"); p.write_text(p.read_text().replace("goodbye", "hello"))

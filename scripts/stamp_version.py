#!/usr/bin/env python3
"""Copy version.json into the page so the running code and the cache-bust match.

Edit version.json (version, date, Traditional Chinese notes), then run this.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def main() -> None:
    manifest = json.loads((ROOT / "version.json").read_text(encoding="utf-8"))
    version = manifest.get("version")
    if not isinstance(version, str) or not SEMVER.fullmatch(version):
        sys.exit("version.json version must be major.minor.patch")
    app = ROOT / "assets" / "app.js"
    text = app.read_text(encoding="utf-8")
    updated, count = re.subn(
        r'const APP_VERSION = "[^"]*";',
        f'const APP_VERSION = "{version}";',
        text,
        count=1,
    )
    if count != 1:
        sys.exit("assets/app.js is missing const APP_VERSION")
    if updated != text:
        app.write_text(updated, encoding="utf-8")
    html_path = ROOT / "index.html"
    html = html_path.read_text(encoding="utf-8")
    html2 = re.sub(r"assets/app\.css(?:\?v=[^\"']*)?", f"assets/app.css?v={version}", html)
    html2 = re.sub(r"assets/app\.js(?:\?v=[^\"']*)?", f"assets/app.js?v={version}", html2)
    if html2 != html:
        html_path.write_text(html2, encoding="utf-8")
    print(version)


if __name__ == "__main__":
    main()

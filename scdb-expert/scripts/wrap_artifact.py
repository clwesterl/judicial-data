#!/usr/bin/env python3
"""Wrap an artifact source file as a standalone HTML page.

Pages published through Claude's Artifact tool are written WITHOUT a document
skeleton: the publisher wraps them at publish time in a doctype, a charset and
viewport meta, and a small reset. The same file opened from disk or served from
GitHub Pages gets none of that, so it renders in quirks mode, ignores the phone
viewport, and keeps the browser's default body margin.

This adds the skeleton back, byte for byte what the publisher supplies, so one
source file can be both published as an artifact and served as a static page.

    python scripts/wrap_artifact.py in.html ../docs/out.html
    python scripts/wrap_artifact.py in.html ../docs/           # keeps the name

Re-running is safe: a file that already has a doctype is copied unchanged.
"""
import sys
import os
import re

SKELETON = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<style>
:root {
  color-scheme: light;
  padding-top: env(safe-area-inset-top, 0px);
  padding-bottom: env(safe-area-inset-bottom, 0px);
}
body { margin: 0; font: 14px system-ui, -apple-system, sans-serif; }
img { max-width: 100%%; }
[hidden] { display: none !important; }
</style>
%(head)s</head>
<body>
%(body)s</body>
</html>
"""

# the publisher hoists these out of the file and into <head>
HEAD_TAGS = re.compile(
    r"""^[ \t]*(<title>.*?</title>
         |<meta\b[^>]*>
         |<link\b[^>]*>
         |<style>.*?</style>)[ \t]*\n?""",
    re.VERBOSE | re.DOTALL | re.IGNORECASE | re.MULTILINE,
)


def wrap(src: str) -> str:
    if re.match(r"\s*<!DOCTYPE", src, re.IGNORECASE):
        return src
    head = []

    # pull the leading run of head-level tags off the top of the file
    while True:
        m = HEAD_TAGS.match(src)
        if not m:
            break
        head.append(m.group(1))
        src = src[m.end():]

    if not any(t.lower().startswith("<title") for t in head):
        sys.stderr.write("warning: no <title> found; the tab will show the filename\n")
    return SKELETON % {
        "head": "".join(t + "\n" for t in head),
        "body": src if src.endswith("\n") else src + "\n",
    }


def main(argv):
    if len(argv) != 3:
        sys.stderr.write(__doc__)
        return 2
    src_path, out_path = argv[1], argv[2]
    if os.path.isdir(out_path):
        out_path = os.path.join(out_path, os.path.basename(src_path))
    with open(src_path, encoding="utf-8") as fh:
        out = wrap(fh.read())
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(out)
    print("%s  (%.1f KB)" % (out_path, len(out.encode()) / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

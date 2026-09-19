#!/usr/bin/env python3
"""
Turn the official SCDB codebook PDF into two skill references:
    references/value_labels.csv  (variable, code, label, table)  -- every numeric code
    references/codebook_text.md  (cleaned text of codebook sections 1-63, grep-able)

Usage:
    python parse_codebook.py path/to/SCDB_YYYY_RR_codebook.pdf
Requires `pdftotext` (poppler-utils). Only needed when a new codebook is released.
"""
import csv, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(os.path.dirname(HERE), "references")
# chief and justiceName are stored as text in the data, so they need no labels
SKIP_VARS = {"chief", "justiceName"}


def furniture(line):
    s = line.replace("\f", "")
    return re.match(r"^\s*\d+ of \d+\s*$", s) or s.strip() == "The Supreme Court Database Codebook"


def main(pdf):
    txt = subprocess.run(["pdftotext", "-layout", pdf, "-"], capture_output=True,
                         text=True, check=True).stdout
    lines = [l.replace("\f", "") for l in txt.split("\n") if not furniture(l)]
    m = re.search(r"brick_(\d{4}_\d+)", txt)
    version = m.group(1) if m else "unknown"

    intro = next(i for i, l in enumerate(lines)
                 if re.match(r"^\s+1\s+Introduction\s*$", l) and "Prefatory" in lines[i + 1])
    appx = next(i for i, l in enumerate(lines)
                if re.match(r"^\s+A1\s+varAdminAction\s*$", l) and i > intro)

    # ---- value labels from the appendix tables
    rows, cur, mode = [], None, None
    for l in lines[appx:]:
        mm = re.match(r"^\s+(A\d+)\s+(var\w+)\s*$", l)
        if mm:
            cur = {"table": mm.group(2), "used": [], "vals": []}
            rows.append(cur); mode = None; continue
        if cur is None:
            continue
        s = l.strip()
        if "is used in conjunction with" in s: mode = "used"; continue
        if s == "Values:": mode = "vals"; continue
        if not s: continue
        if mode == "used":
            cur["used"].append(s)
        elif mode == "vals":
            mm = re.match(r"^\s*(-?\d+)\s+(.*)$", l)
            if mm:
                cur["vals"].append([mm.group(1), mm.group(2).strip()])
            elif cur["vals"]:
                cur["vals"][-1][1] += " " + s
    out = os.path.join(REF, "value_labels.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["variable", "code", "label", "table"])
        for t in rows:
            for v in t["used"]:
                if v in SKIP_VARS:
                    continue
                for code, lab in t["vals"]:
                    w.writerow([v, code, re.sub(r"\s+", " ", lab), t["table"]])
    print(f"{out}: {sum(len(t['vals']) for t in rows)} codes in {len(rows)} tables")

    # ---- cleaned narrative text for sections 1-63
    body, prev = [], None
    for l in lines[intro:appx]:
        s = l.replace('!"', "- ").replace('#"', "- ")
        mm = re.match(r"^\s{8,14}(\d{1,2})\s{2,}([A-Z].*)$", s)
        if mm and int(mm.group(1)) <= 63:
            head = f"## {mm.group(1)}. {mm.group(2).strip()}"
            if head != prev:
                body += ["", head]
            prev = head
            continue
        if "- End of Content for Variable" in s:
            continue
        body.append(s.strip())
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(body)).strip()
    toc = [l for l in text.split("\n") if l.startswith("## ")]
    header = (f"# SCDB Codebook (release {version}) -- variable narratives\n\n"
              "Extracted from the official codebook PDF. Value labels are in value_labels.csv, "
              "not here. Search this file by section header (e.g. `## 37. Decision Direction`) "
              "or by variable name.\n\n## Contents\n" + "\n".join(f"- {h[3:]}" for h in toc) + "\n\n---\n\n")
    with open(os.path.join(REF, "codebook_text.md"), "w", encoding="utf-8") as f:
        f.write(header + text + "\n")
    print(f"codebook_text.md: {len(toc)} sections")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])

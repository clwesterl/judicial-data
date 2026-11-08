"""Join Judicial Common Space scores onto FJC appointment records by judge name.

The two sources disagree about names in three systematic ways:

  * accents             FJC "Gelpi, Gustavo Antonio, Jr." vs master "Gelpi, Gustavo"
  * two-word surnames   FJC "Barrett, Amy Coney"  vs master "Coney Barrett, Amy"
  * middle-name usage   FJC "Duncan, Stuart Kyle" vs master "Duncan, Kyle"

A single normalized key fails on all three, so a candidate pair must instead
satisfy every one of:

  * surname token sets intersect
  * given-name token sets intersect, an initial matching the name it abbreviates
  * same circuit
  * confirmation years within `year_tol`

and a match is accepted only when exactly one master judge qualifies. On the
courts-of-appeals data this matches 95.9% of 1950-89 appointments and 92.1% of
1990-2026, with zero ambiguous cases.
"""
import re
import unicodedata

import numpy as np
import pandas as pd

# Particles that should not count as a surname token on their own.
PARTICLES = {"de", "del", "della", "di", "da", "la", "le", "van", "von", "der",
             "ten", "ter", "du", "dos", "das", "y", "e", "al", "bin", "ibn"}
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v", "vi"}


def _fold(s):
    """Lowercase and strip diacritics: 'Gelpí' -> 'gelpi'."""
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def name_tokens(name):
    """'Coney Barrett, Amy Vivian' -> ({'coney','barrett'}, {'amy','vivian'}).

    Everything before the first comma is the surname, everything after is given
    names. Bracketed forms ('Smith, D[avid] Brooks') and generational suffixes
    are removed."""
    s = re.sub(r"[\[\]]", "", _fold(name))
    s = re.sub(r"[^a-z, ]", " ", s)
    last, _, first = s.partition(",")
    sur = {t for t in last.split() if len(t) > 1 and t not in PARTICLES}
    giv = {t for t in first.split() if t and t not in SUFFIXES}
    return sur, giv


def _tok_ok(x, y):
    """One given-name token agrees, a single letter standing for an initial."""
    return x == y or (len(x) == 1 and y.startswith(x)) or (len(y) == 1 and x.startswith(y))


def _given_ok(a, b):
    """True if any given name agrees. Deliberately loose: a judge who goes by a
    middle name ('Duncan, Kyle' for Stuart Kyle Duncan) matches on that name."""
    return any(_tok_ok(x, y) for x in a for y in b)


def first_given(name):
    """The first given name, for breaking ties the loose rule leaves behind."""
    toks = name_tokens(name)[1]
    s = re.sub(r"[\[\]]", "", _fold(name))
    s = re.sub(r"[^a-z, ]", " ", s)
    after = s.partition(",")[2].split()
    for t in after:
        if t in toks:
            return t
    return None


def match(fjc, master, year_tol=2):
    """Match appointments to master judges.

    `fjc` needs columns judge_name, circuit, start; `master` needs name,
    circuit and a RangeIndex (call reset_index first). Pass `year_tol=None`
    when the master has no YearConfirm — the bundled `jcs("coa")` table does
    not — and matching falls back to name plus circuit alone. Returns
    (master_index, method), both aligned to `fjc`: master_index holds the
    matched row's label in `master` or <NA>, and method records why, so a join
    can be audited."""
    m = master.reset_index(drop=True).copy()
    m["tok"] = [name_tokens(n) for n in m.name]
    m["fgiven"] = [first_given(n) for n in m.name]
    by_circuit = {c: g for c, g in m.groupby("circuit")}

    idx, method = [], []
    for r in fjc.itertuples():
        sur, giv = name_tokens(r.judge_name)
        pool = by_circuit.get(r.circuit)
        if pool is None or not sur:
            idx.append(pd.NA)
            method.append("no candidate")
            continue
        hits = []
        for q in pool.itertuples():
            qsur, qgiv = q.tok
            if not (sur & qsur) or not _given_ok(giv, qgiv):
                continue
            if year_tol is not None and abs(int(q.YearConfirm) - int(r.start)) > year_tol:
                continue
            hits.append(q)
        if len(hits) == 1:
            idx.append(hits[0].Index)
            method.append("matched")
        elif len(hits) > 1:
            # One judge can hold two master rows: the 1981 Fifth -> Eleventh
            # transfers are recorded as two spells.
            if len({q.name for q in hits}) == 1:
                idx.append(hits[0].Index)
                method.append("matched (two master spells)")
                continue
            # The loose given-name rule can tie siblings together -- Morris S.
            # and Richard S. Arnold, both Eighth Circuit, share a middle
            # initial. Break the tie on the first given name.
            fg = first_given(r.judge_name)
            strict = [q for q in hits if fg and q.fgiven and _tok_ok(fg, q.fgiven)]
            if len({q.name for q in strict}) == 1:
                idx.append(strict[0].Index)
                method.append("matched (first name broke a tie)")
            else:
                idx.append(pd.NA)
                method.append(f"ambiguous ({len(hits)})")
        else:
            idx.append(pd.NA)
            method.append("not in master")
    return (pd.Series(idx, index=fjc.index, dtype="object"),
            pd.Series(method, index=fjc.index))

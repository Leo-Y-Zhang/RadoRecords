#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""oeis_lint.py -- mechanical pre-paste linter for OEIS one-term DATA+EXTENSIONS edits.

Stdlib-only. Importable and a CLI.

Usage:
    python oeis_lint.py SPEC.json          lint a paste spec, exit 0 all-pass / 1 failures / 2 input error
    python oeis_lint.py SPEC.json --json   machine-readable result on stdout
    python oeis_lint.py --selftest         run the embedded fixture suite
    python oeis_lint.py --emit-fixtures D  write the scenario fixture spec JSONs into directory D

Paste spec (JSON object):
    seq                     "A250026"
    current_entry_text      the entry's CURRENT internal format (%-lines), fetched fresh
    new_data                full post-edit Data field, comma+space separated ("1, 2, 3"), or null if untouched
    new_extensions_lines    list of EXTENSIONS lines being ADDED (content only, no %E prefix)
    post_edit_extensions    optional: FULL post-edit EXTENSIONS section (use to prove existing lines survive)
    new_references          FULL post-edit References section (list, content only), or null if untouched
    new_links               FULL post-edit Links section (list, content only), or null if untouched
    new_comments            FULL post-edit Comments section, or null (only legal with scope "full")
    discussion_note         the one-sentence pink-box note, or null
    paste_date              "Aug 14 2026" -- the real date the paste will be made
    scope                   "data-extensions-only" (default, the maths-family rule) or "full"
    certificate_gate_passed true/false -- upstream certificate gate (e.g. DRAT verify) result for appended terms
    note_may_reference_url  true if the discussion note legitimately replies about a URL

Import API:
    from oeis_lint import lint_spec, lint_file
    findings, statuses, ok = lint_spec(spec_dict)
"""
from __future__ import annotations

import calendar
import json
import re
import sys
import unicodedata
import datetime

__all__ = ["lint_spec", "lint_file", "selftest", "RULES", "LintInputError"]

# --------------------------------------------------------------------------- #
# rule registry
# --------------------------------------------------------------------------- #

RULES = [
    ("data-integers-only", "every DATA term is a base-10 integer"),
    ("data-comma-space-separated", "DATA terms separated by comma+space, no stray spacing"),
    ("data-no-trailing-separator", "no trailing comma/whitespace, no empty terms"),
    ("data-append-only", "new DATA preserves the existing terms byte-for-byte as a prefix"),
    ("data-min-terms", "DATA has at least 4 terms"),
    ("data-length-soft-limit", "DATA length ~260 target / <500 hard guidance (warn only)"),
    ("data-sign-keyword-consistency", "negative terms require keyword 'sign', never 'nonn'"),
    ("data-terms-not-conjectured", "appended terms passed the certificate gate"),
    ("ext-line-format", "new EXTENSIONS line matches the exact credit format"),
    ("ext-date-is-paste-date", "EXTENSIONS date equals the spec paste_date (warn if != system date)"),
    ("ext-date-format", "all new dates are 'Mon DD YYYY', valid calendar dates"),
    ("ext-term-range-matches-data", "a(N)/a(N)-a(M) claimed equals the indices actually appended"),
    ("ext-appended-at-end", "new EXTENSIONS line(s) appended after all existing ones"),
    ("ext-preserve-existing-lines", "existing EXTENSIONS lines reproduced byte-for-byte"),
    ("ext-no-housekeeping-notes", "no 'Added a comment'-style housekeeping in EXTENSIONS"),
    ("preserve-all-existing-lines", "total diff = appended term(s) + new EXTENSIONS line(s) only"),
    ("no-deletions", "no existing reference/link/comment line deleted"),
    ("scope-data-extensions-only", "maths-family edits touch only DATA and EXTENSIONS"),
    ("no-b-file", "no b-file/a-file reference for these families"),
    ("ref-alpha-by-first-author-surname", "References alphabetized by first author's surname"),
    ("link-order-alpha", "Links alphabetized by first author's surname"),
    ("link-order-bfile-first", "b-file/a-file links come first in Links"),
    ("link-order-index-last", "Index entries come last in Links"),
    ("link-anchor-format", "Links are 'Author, <a href=..>Title</a>', no bare URLs"),
    ("link-broken-marker", "broken links carry the literal '[broken link]' marker"),
    ("ref-initials-spacing", "author initials spaced: 'J. S. Bach' not 'J.S. Bach'"),
    ("sign-name-underscore-markup", "signature is always _Leo Y. Zhang_, underscored, exact"),
    ("sign-comment-format", "signed additions end '. - _Leo Y. Zhang_, Mon DD YYYY'"),
    ("sign-multiparagraph-wrapper", "multi-paragraph contributions use From ...: (Start) ... (End)"),
    ("no-email-address", "no email address anywhere in the paste"),
    ("us-spelling-denylist", "US spelling everywhere (no colour/relabelling/programme/...)"),
    ("hyphenation-closed-forms", "closed forms: nonnegative, squarefree, ... (no hyphens)"),
    ("notation-ascii-operators", "ASCII math notation (^, *, a(n), n-th, Pi, ...)"),
    ("no-non-ascii", "no non-ASCII in math text (names flagged for human confirmation)"),
    ("no-ambiguous-division", "no ambiguous a/b*c, a/b/c, 1/6x (flag for human)"),
    ("no-tabs-or-trailing-whitespace", "no tabs, no trailing whitespace"),
    ("discussion-one-sentence", "discussion note is exactly one sentence ending in a period"),
    ("discussion-no-open-question", "discussion note contains no question mark"),
    ("discussion-no-url", "no URL in the discussion note unless replying about one"),
]
RULE_IDS = [r for r, _ in RULES]

MON = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
MONTHS = MON.split("|")
EXT_RE = re.compile(
    r"^a\((\d+)\)(?:-a\((\d+)\))? (?:from|added by) _Leo Y\. Zhang_, "
    r"(" + MON + r") ([0-3][0-9]) ([12][0-9]{3})$"
)
INT_RE = re.compile(r"-?\d+")
DATE_RE = re.compile(r"^(" + MON + r") ([0-3][0-9]) ([12][0-9]{3})$")

US_SPELLING_DENYLIST = [
    # -our / -re / -ise Britishisms
    "behaviour", "behaviours", "colour", "colours", "coloured", "colouring", "colourings",
    "neighbour", "neighbours", "neighbouring", "neighbourhood", "neighbourhoods",
    "favourite", "favourites", "favour", "favours", "favourable",
    "honour", "honours", "honoured", "flavour", "flavours",
    "centre", "centres", "centred", "fibre", "fibres", "litre", "litres",
    "metre", "metres", "kilometre", "kilometres",
    "generalise", "generalises", "generalised", "generalising",
    "generalisation", "generalisations",
    "specialise", "specialised", "specialisation",
    "minimise", "minimises", "minimised", "minimising", "minimisation",
    "maximise", "maximises", "maximised", "maximising", "maximisation",
    "optimise", "optimises", "optimised", "optimising", "optimisation",
    "normalise", "normalises", "normalised", "normalising", "normalisation",
    "factorise", "factorises", "factorised", "factorisation",
    "initialise", "initialised", "initialisation",
    "randomise", "randomised", "randomisation",
    "summarise", "summarised", "summarising",
    "analyse", "analysed", "analysing",
    "organise", "organised", "organisation",
    "recognise", "recognised", "recognising",
    "emphasise", "emphasised", "utilise", "utilised",
    "parametrise", "parametrised", "parametrisation",
    "programme", "programmes",
    "labelled", "labelling", "relabelled", "relabelling",
    "modelled", "modelling", "travelled", "travelling",
    "defence", "offence", "practise", "practising",
    "whilst", "amongst", "grey", "artefact", "artefacts",
    # style-sheet misspellings
    "cancelation", "dependant", "independant", "proven",
    "zeroes", "zeroeth", "occuring", "recurence", "dissectable",
]
_SPELL_RE = re.compile(r"\b(" + "|".join(US_SPELLING_DENYLIST) + r")\b", re.IGNORECASE)

HYPHEN_FORMS = [
    "non-negative", "non-zero", "non-empty", "non-trivial", "non-decreasing",
    "non-increasing", "non-positive", "non-prime", "non-square", "non-squarefree",
    "non-composite", "non-unit", "square-free", "cube-free", "semi-prime",
    "sub-matrix", "nil-potent",
]
_HYPHEN_RE = re.compile(r"\b(" + "|".join(HYPHEN_FORMS) + r")\b", re.IGNORECASE)
_PRIME_INDEX_RE = re.compile(r"\bprime-index prime\b", re.IGNORECASE)

_NOTATION_CHECKS = [
    (re.compile(r"\*\*"), "use ^ for powers, not **"),
    (re.compile(r"\+/-"), "use +- not +/-"),
    (re.compile(r"\b(Sqrt|Sin|Cos|Tan|Log|Exp)\["), "use lowercase sqrt(x)/sin(x)/... not Mathematica Sqrt[..]"),
    (re.compile(r"\ba\[(?:n|\d+)\]"), "use a(n), not a[n]"),
    (re.compile(r"\ba_\{?(?:n|\d)"), "use a(n), not a_n"),
    (re.compile(r"\b[nN]th\b"), "write n-th, not nth"),
    (re.compile(r"\b\d+-(?:th|st|nd|rd)\b"), "write 0th/1st/2nd, not 0-th/1-st/2-nd"),
    (re.compile(r"\b\d+ x \d+\b"), "grid dimensions use capital X: 'n X n'"),
    (re.compile(r"(?<![A-Za-z])pi(?![A-Za-z])"), "write Pi, not pi"),
]
_DIV_CHECKS = [
    re.compile(r"\b\w+/\w+\*\w+"),
    re.compile(r"\b\w+/\w+/\w+"),
    re.compile(r"\b1/\d+[a-zA-Z]"),
]
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b|mailto:")
_URL_RE = re.compile(r"https?://|\bwww\.")
_BFILE_TXT_RE = re.compile(r"\b[ab]\d{6}\.txt\b")
# b-file / bfile / b file / a-file / afile ('a file' with a space is left
# alone: it is ordinary English and would false-positive).
_BFILE_WORD_RE = re.compile(r"\bb[- ]?files?\b|\ba-?files?\b", re.IGNORECASE)
_INITIALS_RE = re.compile(r"[A-Z]\.[A-Z]\.")
_ANCHOR_RE = re.compile(r'<a href="[^"]+">[^<]+</a>')
_ANCHOR_STRIP_RE = re.compile(r'<a href="[^"]*">([^<]*)</a>')
_FULL_MONTH_RE = re.compile(
    r"\b(January|February|March|April|June|July|August|September|October|November|December)\b"
)
_DATE_IN_TEXT_RE = re.compile(r"\b(" + MON + r")\b\.?,? +(\d{1,2})(?:st|nd|rd|th)?,? +(\d{4})")
_DAY_FIRST_RE = re.compile(r"\b\d{1,2} (" + MON + r") \d{4}\b")
_HOUSEKEEPING_RE = re.compile(
    r"\badded (a|an|the)? ?(comment|link|reference|formula|program|crossref|cross-reference|b-file)",
    re.IGNORECASE,
)
_NAME_UNWRAPPED_RE = re.compile(r"(?<!_)Leo Y\. Zhang(?!_)")
# Wrong renderings of the registered name, wrapped in underscores or not:
# 'Leo Zhang', '_Leo Zhang_', 'Leo Y Zhang', '_Leo Y Zhang_' (correct form
# '_Leo Y. Zhang_' does not match either branch).  \b is useless next to '_'
# (underscore is a word character), so use explicit letter lookarounds.
_NAME_VARIANT_RE = re.compile(r"(?<![A-Za-z])_?Leo (?:Zhang|Y Zhang)_?(?![A-Za-z])")

_PARTICLES = {"van", "von", "de", "del", "della", "der", "den", "da", "di",
              "la", "le", "ten", "ter", "dos", "du", "al", "el", "bin", "ibn"}
# Capitalized particles that are still part of the surname (De Loera, Van Lint).
# Kept narrower than _PARTICLES: 'Al'/'El'/'Bin' capitalized are usually given names.
_CAP_PARTICLES = {"Van", "Von", "De", "Del", "Della", "Der", "Den", "Da", "Di",
                  "La", "Le", "Ten", "Ter", "Dos", "Du"}
_ET_AL_RE = re.compile(r",?\s+et\.?\s+al\.?$", re.IGNORECASE)
_INST_WORDS = {"department", "university", "institute", "project", "committee",
               "contributors", "wikipedia", "mathoverflow", "oeis", "foundation",
               "society", "laboratory", "group", "database", "center", "centre",
               "team", "consortium", "press", "inc", "college", "school",
               "association", "encyclopedia", "archive", "sequence", "fandom"}
_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "jr.", "sr."}


class LintInputError(Exception):
    """The spec itself is unusable (bad JSON shape, unparseable entry text)."""


# --------------------------------------------------------------------------- #
# parsing helpers
# --------------------------------------------------------------------------- #

def parse_internal(text):
    """Parse OEIS internal format (%-lines) into fields/terms/offset/keywords."""
    if not text or not text.strip():
        raise LintInputError("current_entry_text is empty")
    fields, seq = {}, None
    for raw in text.splitlines():
        if not raw.strip():
            continue
        m = re.match(r"^%(\w)\s+(A\d{6})(?:\s(.*))?$", raw)
        if not m:
            raise LintInputError("unparseable internal-format line: %r" % raw)
        code, anum, content = m.group(1), m.group(2), m.group(3) or ""
        seq = seq or anum
        fields.setdefault(code, []).append(content)
    if not fields:
        raise LintInputError("no %-lines found in current_entry_text")
    data = ""
    for c in fields.get("S", []) + fields.get("T", []) + fields.get("U", []):
        c = c.strip()
        if data and not data.endswith(","):
            data += ","
        data += c
    terms = [t.strip() for t in data.split(",") if t.strip()]
    offset = None
    if "O" in fields:
        mo = re.match(r"^\s*(-?\d+)", fields["O"][0])
        offset = int(mo.group(1)) if mo else None
    keywords = []
    if "K" in fields:
        keywords = [k.strip() for k in fields["K"][0].split(",") if k.strip()]
    return {"seq": seq, "fields": fields, "terms": terms, "offset": offset,
            "keywords": keywords, "D": fields.get("D", []), "H": fields.get("H", []),
            "E": fields.get("E", []), "C": fields.get("C", [])}


def _norm(s):
    """Diacritic-stripped casefold for ordering comparisons (Erdős -> erdos)."""
    return "".join(ch for ch in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(ch)).casefold()


def _is_institutional(name):
    toks = name.replace(",", " ").split()
    for t in toks:
        tl = t.strip(".,()").lower()
        if tl in _INST_WORDS:
            return True
        if len(t.strip(".,()")) >= 2 and t.strip(".,()").isupper() and t.strip(".,()").isalpha():
            return True  # UCSD, MIT, ...
        if t[:1].islower() and tl not in _PARTICLES and not t[:1].isdigit():
            return True  # 'problems', 'database', ...
    return False


def _personal_surname(name):
    toks = name.replace(",", " ").split()
    flags = []
    while toks and toks[-1].strip(".,()").lower() in _SUFFIXES | {"et", "al", "al."}:
        toks.pop()
    if not toks:
        return name, ["unparseable"]
    parts = [toks[-1].strip(",.")]
    j = len(toks) - 2
    while j >= 0:
        tj = toks[j].strip(",.")
        if (tj.lower() in _PARTICLES and tj[:1].islower()) or tj in _CAP_PARTICLES:
            parts.insert(0, toks[j])
            j -= 1
        else:
            break
    if len(parts) > 1:
        flags.append("particle-surname")
    if len(toks) == 1:
        flags.append("mononym")
    return " ".join(parts), flags


def author_sort_key(line, kind):
    """(sort_key, display_author, flags) for a %D or %H content line."""
    flags = []
    if kind == "link":
        if line.lstrip().startswith("<a"):
            return None, None, ["no-author"]
        author_part = line.split(", <a")[0] if ", <a" in line else line.split("<a")[0].rstrip(", ")
    else:
        author_part = line
    seg = author_part.split(", ")[0].strip()
    first = re.split(r"\s+and\s+|\s*&\s*", seg)[0].strip().rstrip(",.")
    first = _ET_AL_RE.sub("", first).strip().rstrip(",.")
    if not first:
        return None, None, ["unparseable"]
    if _is_institutional(first):
        flags.append("institutional")
        return _norm(first), first, flags
    surname, f2 = _personal_surname(first)
    flags.extend(f2)
    return _norm(surname), first, flags


def _year_of(line):
    m = re.search(r"\b(1[6-9]\d\d|20\d\d)\b", line)
    return int(m.group(1)) if m else None


def classify_link(line):
    if _BFILE_TXT_RE.search(line) or "Table of n, a(n) for n" in line:
        return "bfile"
    if re.search(r'href="[^"]*(/index/|/wiki/Index)', line):
        return "index"
    return "normal"


def _valid_date(mon, day, year):
    if mon not in MONTHS:
        return False
    m = MONTHS.index(mon) + 1
    try:
        return 1 <= day <= calendar.monthrange(year, m)[1]
    except (calendar.IllegalMonthError, ValueError):
        return False


def _multiset_lost(old_lines, post_lines):
    """First old line missing from post (multiset membership), or None."""
    remaining = list(post_lines)
    for o in old_lines:
        if o in remaining:
            remaining.remove(o)
        else:
            return o
    return None


def _new_lines(old_lines, post_lines):
    remaining = list(old_lines)
    out = []
    for line in post_lines:
        if line in remaining:
            remaining.remove(line)
        else:
            out.append(line)
    return out


# --------------------------------------------------------------------------- #
# the linter
# --------------------------------------------------------------------------- #

def lint_spec(spec, today=None):
    """Lint a paste spec. Returns (findings, statuses, ok).

    findings: list of (level, rule_id, message)   level in {"FAIL","WARN"}
    statuses: dict rule_id -> "PASS"|"FAIL"|"WARN"|"skip"
    ok:       True iff no FAIL findings
    """
    if not isinstance(spec, dict):
        raise LintInputError("spec must be a JSON object")
    F = []
    na = set()

    def fail(rule, msg):
        F.append(("FAIL", rule, msg))

    def warn(rule, msg):
        F.append(("WARN", rule, msg))

    today = today or datetime.date.today()
    entry = parse_internal(spec.get("current_entry_text") or "")
    scope = spec.get("scope", "data-extensions-only")
    if scope not in ("data-extensions-only", "full"):
        raise LintInputError("scope must be 'data-extensions-only' or 'full'")

    old_D, old_H, old_E, old_C = entry["D"], entry["H"], entry["E"], entry["C"]
    refs_edited = spec.get("new_references") is not None
    links_edited = spec.get("new_links") is not None
    comments_edited = spec.get("new_comments") is not None
    post_D = list(spec["new_references"]) if refs_edited else list(old_D)
    post_H = list(spec["new_links"]) if links_edited else list(old_H)
    post_C = list(spec["new_comments"]) if comments_edited else list(old_C)
    new_ext_declared = list(spec.get("new_extensions_lines") or [])
    post_E = spec.get("post_edit_extensions")
    post_E = list(post_E) if post_E is not None else old_E + new_ext_declared

    # ---- scope --------------------------------------------------------------
    if scope == "data-extensions-only":
        if refs_edited and post_D != old_D:
            fail("scope-data-extensions-only", "new_references modifies the References section")
        if links_edited and post_H != old_H:
            fail("scope-data-extensions-only", "new_links modifies the Links section")
        if comments_edited and post_C != old_C:
            fail("scope-data-extensions-only", "new_comments modifies the Comments section")
        for k in ("new_name", "new_offset", "new_keywords", "new_formulas",
                  "new_programs", "new_crossrefs"):
            if spec.get(k):
                fail("scope-data-extensions-only", "out-of-scope field present: %s" % k)
    else:
        na.add("scope-data-extensions-only")

    # ---- DATA ---------------------------------------------------------------
    old_terms = entry["terms"]
    nd = spec.get("new_data")
    data_edited = nd is not None
    prefix_ok = True
    appended = []
    if data_edited:
        if "\t" in nd:
            fail("no-tabs-or-trailing-whitespace", "tab character in new_data")
        if nd != nd.strip():
            fail("data-no-trailing-separator",
                 "leading/trailing whitespace in new_data | offending: %r" % nd)
        body = nd.strip()
        if body.endswith(","):
            fail("data-no-trailing-separator",
                 "new_data ends with a comma | offending: %r" % body[-40:])
        if re.search(r",(?!\s)", body.rstrip(",")):
            fail("data-comma-space-separated",
                 "comma not followed by a space | offending: %r" % nd)
        tokens = body.split(", ")
        for t in tokens:
            if t == "" or t == ",":
                fail("data-no-trailing-separator", "empty term (doubled comma?) in new_data")
            elif t != t.strip():
                fail("data-comma-space-separated",
                     "stray whitespace around term %r" % t)
            elif not INT_RE.fullmatch(t):
                fail("data-integers-only", "non-integer DATA term %r" % t)
            elif re.fullmatch(r"-?0\d+", t) or t == "-0":
                fail("data-integers-only",
                     "DATA term %r has a leading zero / negative zero" % t)
        post_terms = [t.strip() for t in tokens if t.strip()]
        if post_terms[:len(old_terms)] != old_terms:
            k = next((i for i, (a, b) in enumerate(zip(old_terms, post_terms)) if a != b),
                     min(len(old_terms), len(post_terms)))
            oldv = old_terms[k] if k < len(old_terms) else "<missing>"
            newv = post_terms[k] if k < len(post_terms) else "<missing>"
            fail("data-append-only",
                 "existing terms not preserved: term %d was %r, paste has %r"
                 % (k + 1, oldv, newv))
            prefix_ok = False
        else:
            appended = post_terms[len(old_terms):]
            if not appended:
                warn("data-append-only", "new_data provided but appends no terms")
    else:
        post_terms = list(old_terms)
        na.update({"data-comma-space-separated", "data-no-trailing-separator",
                   "data-append-only"})

    if len(post_terms) < 4:
        fail("data-min-terms", "only %d DATA term(s); minimum is 4" % len(post_terms))
    data_str = ", ".join(post_terms)
    if len(data_str) >= 500:
        warn("data-length-soft-limit",
             "DATA is %d chars (>=500); stay under 500 -- and no b-file overflow for these families"
             % len(data_str))
    elif len(data_str) > 260:
        warn("data-length-soft-limit",
             "DATA is %d chars (>260 target); prefer not to add further terms" % len(data_str))

    kw = entry["keywords"]
    negs = [t for t in appended if t.startswith("-")]
    if negs:
        if "nonn" in kw:
            fail("data-sign-keyword-consistency",
                 "appended negative term %r but entry keyword is 'nonn'" % negs[0])
        if "sign" not in kw:
            fail("data-sign-keyword-consistency",
                 "appended negative term %r but keyword 'sign' absent" % negs[0])
    if not kw:
        warn("data-sign-keyword-consistency", "entry has no %K line; cannot cross-check sign/nonn")

    if appended:
        gate = spec.get("certificate_gate_passed", None)
        if gate is False:
            fail("data-terms-not-conjectured",
                 "certificate_gate_passed is false -- conjectured terms never go in DATA")
        elif gate is None:
            warn("data-terms-not-conjectured",
                 "certificate_gate_passed missing -- human must confirm the gate ran on exactly these term(s)")
    else:
        na.add("data-terms-not-conjectured")

    # ---- paste_date ---------------------------------------------------------
    pd = spec.get("paste_date") or ""
    pd_ok = False
    m = DATE_RE.match(pd)
    if not m:
        fail("ext-date-format", "paste_date %r is not 'Mon DD YYYY'" % pd)
    elif not _valid_date(m.group(1), int(m.group(2)), int(m.group(3))):
        fail("ext-date-format", "paste_date %r is not a real calendar date" % pd)
    else:
        pd_ok = True
        d = datetime.date(int(m.group(3)), MONTHS.index(m.group(1)) + 1, int(m.group(2)))
        if d != today:
            warn("ext-date-is-paste-date",
                 "paste_date %s differs from system date %s -- confirm you are pasting on that day"
                 % (pd, today.strftime("%b %d %Y")))

    # ---- EXTENSIONS ---------------------------------------------------------
    ext_prefix_ok = post_E[:len(old_E)] == old_E
    if not ext_prefix_ok:
        fail("ext-appended-at-end",
             "existing EXTENSIONS lines are not an unmodified prefix of the post-edit section")
    lost_E = _multiset_lost(old_E, post_E)
    if lost_E is not None:
        fail("ext-preserve-existing-lines",
             "existing EXTENSIONS line lost or altered | offending (original): %r" % lost_E)
    actual_new_ext = post_E[len(old_E):] if ext_prefix_ok else _new_lines(old_E, post_E)
    if spec.get("post_edit_extensions") is not None and new_ext_declared:
        if ext_prefix_ok and actual_new_ext != new_ext_declared:
            fail("ext-appended-at-end",
                 "declared new_extensions_lines do not equal the appended tail: %r vs %r"
                 % (new_ext_declared, actual_new_ext))

    claimed_ranges = []
    for line in actual_new_ext:
        mm = EXT_RE.match(line)
        if not mm:
            fail("ext-line-format",
                 "EXTENSIONS line does not match "
                 "'a(N)[-a(M)] from _Leo Y. Zhang_, Mon DD YYYY' | offending: %r" % line)
        else:
            n1 = int(mm.group(1))
            n2 = int(mm.group(2)) if mm.group(2) else n1
            if mm.group(2) is not None and n1 == n2:
                fail("ext-line-format",
                     "single-term credit must be written a(%d), not a(%d)-a(%d)"
                     % (n1, n1, n1) + " | offending: %r" % line)
            claimed_ranges.append((n1, n2, line))
            mon, day, year = mm.group(3), int(mm.group(4)), int(mm.group(5))
            if not _valid_date(mon, day, year):
                fail("ext-date-format",
                     "EXTENSIONS date is not a real calendar date | offending: %r" % line)
            dstr = "%s %02d %d" % (mon, day, year)
            if pd_ok and dstr != pd:
                fail("ext-date-is-paste-date",
                     "EXTENSIONS date %r != paste_date %r | offending: %r" % (dstr, pd, line))
        if _HOUSEKEEPING_RE.search(line):
            fail("ext-no-housekeeping-notes",
                 "housekeeping note in EXTENSIONS | offending: %r" % line)

    offset = entry["offset"]
    if offset is None:
        warn("ext-term-range-matches-data", "entry has no %O line; assuming offset 1")
        offset = 1
    if appended:
        start = offset + len(old_terms)
        end = offset + len(post_terms) - 1
        want = "a(%d)" % start if start == end else "a(%d)-a(%d)" % (start, end)
        if not claimed_ranges:
            fail("ext-term-range-matches-data",
                 "%d term(s) appended but no valid EXTENSIONS line credits them (expected %s)"
                 % (len(appended), want))
        elif len(claimed_ranges) > 1:
            fail("ext-term-range-matches-data",
                 "multiple EXTENSIONS credit lines for one append; expected exactly one (%s)" % want)
        else:
            n1, n2, line = claimed_ranges[0]
            if (n1, n2) != (start, end):
                fail("ext-term-range-matches-data",
                     "EXTENSIONS claims a(%d)%s but the appended indices are %s (offset %d, %d old terms)"
                     % (n1, "" if n1 == n2 else "-a(%d)" % n2, want, offset, len(old_terms))
                     + " | offending: %r" % line)
    else:
        if claimed_ranges:
            fail("ext-term-range-matches-data",
                 "EXTENSIONS line claims new terms but no terms were appended | offending: %r"
                 % claimed_ranges[0][2])
        elif not actual_new_ext:
            na.update({"ext-term-range-matches-data", "ext-line-format",
                       "ext-date-is-paste-date", "ext-no-housekeeping-notes"})

    # ---- References / Links / Comments preservation and order ---------------
    if refs_edited:
        lost = _multiset_lost(old_D, post_D)
        if lost is not None:
            fail("no-deletions",
                 "existing REFERENCES line deleted or altered | offending (original): %r" % lost)
        _check_order(F, warn, post_D, "ref", "ref-alpha-by-first-author-surname")
    else:
        na.add("ref-alpha-by-first-author-surname")

    if links_edited:
        lost = _multiset_lost(old_H, post_H)
        if lost is not None:
            fail("no-deletions",
                 "existing LINKS line deleted or altered | offending (original): %r" % lost)
        _check_link_sections(F, warn, post_H)
    else:
        na.update({"link-order-alpha", "link-order-bfile-first", "link-order-index-last"})

    if comments_edited:
        lost = _multiset_lost(old_C, post_C)
        if lost is not None:
            fail("no-deletions",
                 "existing COMMENTS line deleted or altered | offending (original): %r" % lost)
    if not (refs_edited or links_edited or comments_edited):
        na.add("no-deletions")

    new_D_lines = _new_lines(old_D, post_D) if refs_edited else []
    new_H_lines = _new_lines(old_H, post_H) if links_edited else []
    new_C_lines = _new_lines(old_C, post_C) if comments_edited else []

    # ---- new-material style scans -------------------------------------------
    note = spec.get("discussion_note")
    units = []  # (label, raw, kind)
    units += [("EXTENSIONS", l, "ext") for l in actual_new_ext]
    units += [("REFERENCES", l, "ref") for l in new_D_lines]
    units += [("LINKS", l, "link") for l in new_H_lines]
    units += [("COMMENTS", l, "comment") for l in new_C_lines]
    if note is not None:
        units.append(("discussion note", note, "note"))

    if not new_H_lines:
        na.update({"link-anchor-format", "link-broken-marker"})
    if not (new_D_lines or new_H_lines):
        na.add("ref-initials-spacing")
    if not new_C_lines:
        na.update({"sign-comment-format", "sign-multiparagraph-wrapper"})

    for label, raw, kind in units:
        _scan_unit(F, fail, warn, label, raw, kind, scope, spec)

    # multiparagraph wrapper balance across new entry-field text
    field_text = "\n".join(l for _, l, k in units if k != "note")
    n_start, n_end = field_text.count("(Start)"), field_text.count("(End)")
    if n_start or n_end:
        na.discard("sign-multiparagraph-wrapper")
        if n_start != n_end:
            fail("sign-multiparagraph-wrapper",
                 "(Start)/(End) unbalanced: %d vs %d" % (n_start, n_end))
        if n_start and not re.search(
                r"From _Leo Y\. Zhang_, (" + MON + r") [0-3]\d [12]\d{3}: \(Start\)", field_text):
            fail("sign-multiparagraph-wrapper",
                 "(Start) block lacks the 'From _Leo Y. Zhang_, Mon DD YYYY: (Start)' opener")

    # ---- discussion note ----------------------------------------------------
    if note is None:
        na.update({"discussion-one-sentence", "discussion-no-open-question", "discussion-no-url"})
    else:
        if "?" in note:
            fail("discussion-no-open-question",
                 "question mark in discussion note -- never leave an own-question open | offending: %r" % note)
        if "\n" in note:
            fail("discussion-one-sentence", "discussion note spans multiple lines")
        if not note.rstrip().endswith("."):
            fail("discussion-one-sentence",
                 "discussion note does not end with a period | offending: %r" % note)
        s = note
        for ab in ("e.g.", "i.e.", "cf.", "vs.", "et al.", "etc.", "a.k.a."):
            s = s.replace(ab, " ")
        s = _EMAIL_RE.sub(" ", s)
        s = re.sub(r"https?://\S+|\bwww\.\S+", " ", s)
        s = re.sub(r"\b[A-Z]\.", " ", s)
        s = re.sub(r"\d\.\d", "0", s)
        s = s.replace("...", " ")
        terminals = len(re.findall(r"[.!?]", s))
        if terminals != 1:
            fail("discussion-one-sentence",
                 "discussion note is not exactly one sentence (%d terminal marks) | offending: %r"
                 % (terminals, note))
        if ";" in note:
            warn("discussion-one-sentence",
                 "semicolon in discussion note -- avoid chained clauses")
        if _URL_RE.search(note) and not spec.get("note_may_reference_url"):
            fail("discussion-no-url",
                 "URL in discussion note (set note_may_reference_url only when replying about one) | offending: %r"
                 % note)

    # ---- b-file for the maths families --------------------------------------
    if scope == "data-extensions-only":
        for label, raw, kind in units:
            if _BFILE_TXT_RE.search(raw) or _BFILE_WORD_RE.search(raw):
                fail("no-b-file",
                     "b-file/a-file mentioned in new %s -- DATA-line terms only for these families | offending: %r"
                     % (label, raw))
    else:
        na.add("no-b-file")

    # ---- roll-up ------------------------------------------------------------
    failed_so_far = {r for lvl, r, _ in F if lvl == "FAIL"}
    if failed_so_far & {"no-deletions", "ext-preserve-existing-lines", "data-append-only"}:
        fail("preserve-all-existing-lines",
             "paste diff exceeds 'appended term(s) + new EXTENSIONS line(s)' -- see the preservation failures above")

    failed = {r for lvl, r, _ in F if lvl == "FAIL"}
    warned = {r for lvl, r, _ in F if lvl == "WARN"}
    statuses = {}
    for rule in RULE_IDS:
        if rule in failed:
            statuses[rule] = "FAIL"
        elif rule in warned:
            statuses[rule] = "WARN"
        elif rule in na:
            statuses[rule] = "skip"
        else:
            statuses[rule] = "PASS"
    return F, statuses, not failed


def _check_order(F, warn, lines, kind, rule):
    keyed = []
    for line in lines:
        key, author, flags = author_sort_key(line, kind)
        if key is None:
            warn(rule, "cannot identify an author to sort by | offending: %r" % line)
            continue
        if flags:
            warn(rule, "surname parse flagged for human confirmation: %r -> sort key %r (%s)"
                 % (author, key, ",".join(flags)))
        keyed.append((key, _year_of(line), line, _norm(author)))
    for (k1, y1, l1, a1), (k2, y2, l2, a2) in zip(keyed, keyed[1:]):
        if k1 > k2:
            F.append(("FAIL", rule,
                      "out of alphabetical order by first author's surname: %r (key %r) precedes %r (key %r)"
                      % (l1, k1, l2, k2)))
        elif k1 == k2 and y1 and y2 and y1 > y2 and a1 == a2:
            F.append(("FAIL", rule,
                      "same first author but not in chronological order: %r (%d) precedes %r (%d)"
                      % (l1, y1, l2, y2)))
        elif k1 == k2 and a1 != a2 and a1 > a2:
            F.append(("FAIL", rule,
                      "same surname but authors not in alphabetical order by given name: "
                      "%r (%r) precedes %r (%r)" % (l1, a1, l2, a2)))


def _check_link_sections(F, warn, post_H):
    kinds = [classify_link(l) for l in post_H]
    seen_normal = seen_index = False
    normals = []
    for line, k in zip(post_H, kinds):
        if k == "bfile":
            if seen_normal or seen_index:
                F.append(("FAIL", "link-order-bfile-first",
                          "b-file/a-file link must come first in LINKS | offending: %r" % line))
        elif k == "index":
            seen_index = True
        else:
            if seen_index:
                F.append(("FAIL", "link-order-index-last",
                          "Index entry must come last in LINKS; a normal link follows one | offending: %r" % line))
            seen_normal = True
            normals.append(line)
    _check_order(F, warn, normals, "link", "link-order-alpha")


def _scan_unit(F, fail, warn, label, raw, kind, scope, spec):
    q = " | offending [%s]: %r" % (label, raw)
    prose = _ANCHOR_STRIP_RE.sub(r"\1", raw) if kind == "link" else raw

    if "\t" in raw:
        fail("no-tabs-or-trailing-whitespace", "tab character" + q)
    if raw != raw.rstrip():
        fail("no-tabs-or-trailing-whitespace", "trailing whitespace" + q)

    for m in _SPELL_RE.finditer(prose):
        fail("us-spelling-denylist", "non-US/denylisted spelling %r" % m.group(0) + q)
    for m in _HYPHEN_RE.finditer(prose):
        fail("hyphenation-closed-forms",
             "hyphenated form %r; OEIS uses the closed form" % m.group(0) + q)
    if _PRIME_INDEX_RE.search(prose):
        fail("hyphenation-closed-forms", "use 'prime-indexed prime', not 'prime-index prime'" + q)

    for rx, msg in _NOTATION_CHECKS:
        if rx.search(prose):
            fail("notation-ascii-operators", msg + q)
    for rx in _DIV_CHECKS:
        m = rx.search(prose)
        if m:
            warn("no-ambiguous-division",
                 "possibly ambiguous division %r -- parenthesize" % m.group(0) + q)
            break

    if _EMAIL_RE.search(raw):
        fail("no-email-address", "email address present" + q)

    for ch in raw:
        if ord(ch) < 128:
            continue
        try:
            uname = unicodedata.name(ch)
        except ValueError:
            uname = "U+%04X" % ord(ch)
        if ch.isalpha() and "GREEK" not in uname:
            warn("no-non-ascii",
                 "non-ASCII letter %r (%s) -- allowed only in proper names; human must confirm" % (ch, uname) + q)
        else:
            fail("no-non-ascii", "non-ASCII character %r (%s) in mathematical text" % (ch, uname) + q)

    # dates in new text
    if _FULL_MONTH_RE.search(prose):
        fail("ext-date-format",
             "spelled-out month; dates are 'Mon DD YYYY'" + q)
    if _DAY_FIRST_RE.search(prose):
        fail("ext-date-format", "day-first date; dates are 'Mon DD YYYY'" + q)
    for m in _DATE_IN_TEXT_RE.finditer(prose):
        mon, day, year = m.group(1), m.group(2), m.group(3)
        exact = "%s %s %s" % (mon, day, year)
        if m.group(0) != exact or len(day) != 2:
            fail("ext-date-format",
                 "date %r not in 'Mon DD YYYY' form" % m.group(0) + q)
        elif not _valid_date(mon, int(day), int(year)):
            fail("ext-date-format", "date %r is not a real calendar date" % m.group(0) + q)

    if kind in ("ext", "comment"):
        if _NAME_UNWRAPPED_RE.search(raw) or _NAME_VARIANT_RE.search(raw):
            fail("sign-name-underscore-markup",
                 "registered name must appear exactly as _Leo Y. Zhang_" + q)

    if kind in ("ref", "link"):
        if _INITIALS_RE.search(prose):
            fail("ref-initials-spacing",
                 "initials need spaces: 'J. S. Bach' not 'J.S. Bach'" + q)

    if kind == "link":
        lk = classify_link(raw)
        if not _ANCHOR_RE.search(raw):
            fail("link-anchor-format", "no well-formed <a href=\"URL\">Title</a> anchor" + q)
        else:
            stripped = _ANCHOR_STRIP_RE.sub(" ", raw)
            if _URL_RE.search(stripped):
                fail("link-anchor-format", "bare URL outside the anchor" + q)
            if lk == "normal" and raw.lstrip().startswith("<a"):
                fail("link-anchor-format",
                     "missing author before the anchor (use 'Author?' if unknown)" + q)
        if "[broken link]" not in raw and re.search(r"\bbroken link\b|\bdead link\b",
                                                    prose, re.IGNORECASE):
            warn("link-broken-marker",
                 "broken-link note should be the literal marker '[broken link]'" + q)

    if kind == "comment":
        if ("_Leo Y. Zhang_" in raw and "(Start)" not in raw and "(End)" not in raw
                and not re.search(r"\. - _Leo Y\. Zhang_, (" + MON + r") [0-3]\d [12]\d{3}$", raw)):
            fail("sign-comment-format",
                 "signed addition must end '. - _Leo Y. Zhang_, Mon DD YYYY'" + q)


# --------------------------------------------------------------------------- #
# report / CLI
# --------------------------------------------------------------------------- #

def render_report(seq, findings, statuses, ok):
    out = []
    out.append("oeis_lint: %s" % (seq or "?"))
    fails = [f for f in findings if f[0] == "FAIL"]
    warns = [f for f in findings if f[0] == "WARN"]
    for _, rule, msg in fails:
        out.append("FAIL %s: %s" % (rule, msg))
    for _, rule, msg in warns:
        out.append("WARN %s: %s" % (rule, msg))
    out.append("-- rule summary --")
    for rule, desc in RULES:
        out.append("%-4s %-36s %s" % (statuses[rule], rule, desc))
    n_pass = sum(1 for r in RULE_IDS if statuses[r] == "PASS")
    n_skip = sum(1 for r in RULE_IDS if statuses[r] == "skip")
    out.append("RESULT: %s (%d failed, %d warned, %d passed, %d n/a of %d rules)"
               % ("FAIL" if not ok else "PASS", len(fails), len(warns),
                  n_pass, n_skip, len(RULE_IDS)))
    return "\n".join(out)


def lint_file(path, today=None):
    with open(path, "r", encoding="utf-8") as fh:
        spec = json.load(fh)
    findings, statuses, ok = lint_spec(spec, today=today)
    return spec, findings, statuses, ok


# --------------------------------------------------------------------------- #
# fixtures (scenario reconstructions + unit cases)
# --------------------------------------------------------------------------- #

def _entry(seq, terms, offset="1,1", keywords="nonn,more", D=(), H=(), E=(), name="Fixture."):
    lines = ["%%S %s %s" % (seq, ",".join(terms))]
    lines.append("%%N %s %s" % (seq, name))
    for d in D:
        lines.append("%%D %s %s" % (seq, d))
    for h in H:
        lines.append("%%H %s %s" % (seq, h))
    lines.append("%%K %s %s" % (seq, keywords))
    lines.append("%%O %s %s" % (seq, offset))
    for e in E:
        lines.append("%%E %s %s" % (seq, e))
    return "\n".join(lines)


_A006672_REFS_RED = [
    "B. M. Landman and A. Robertson, Ramsey Theory on the Integers, American Mathematical Society, 2014.",
    "N. J. A. Sloane and Simon Plouffe, The Encyclopedia of Integer Sequences, Academic Press, 1995.",
    "T. D. Parsons, Ramsey graphs and block designs, Trans. Amer. Math. Soc., 209 (1975), 33-44.",
]
_A006672_REFS_GREEN = [_A006672_REFS_RED[0], _A006672_REFS_RED[2], _A006672_REFS_RED[1]]

_A006672_LINKS = {
    "bloom": 'G. S. Bloom, <a href="https://doi.org/10.1002/jgt.3190010000">A note on generalized Ramsey numbers</a>',
    "boza": 'L. Boza, M. P. Revuelta, and M. I. Sanz, <a href="https://arxiv.org/abs/1908.00000">On some Ramsey and van der Waerden type numbers</a>',
    "burr": 'S. A. Burr, <a href="https://doi.org/10.1016/0012-365X(75)90000-0">Generalized Ramsey theory for graphs</a>',
    "erdos": 'Erdős problems database contributors, <a href="https://www.erdosproblems.com/">The Erdos problems database</a>',
    "tse": 'Kung-Kuen Tse, <a href="https://arxiv.org/abs/math/0409000">On some van der Waerden type numbers</a>',
    "ucsd": 'UCSD Mathematics Department, <a href="https://mathweb.ucsd.edu/~vdw/">Van der Waerden number pages</a>',
}
_A006672_LINKS_RED = [_A006672_LINKS[k] for k in ("boza", "bloom", "burr", "erdos", "ucsd", "tse")]
_A006672_LINKS_GREEN = [_A006672_LINKS[k] for k in ("bloom", "boza", "burr", "erdos", "tse", "ucsd")]


def _fixture_specs():
    """The four demanded scenario reconstructions, red and green."""
    fx = {}

    # (a) A006672 -- the real 2026-08-13 bounce: refs/links not alphabetized.
    a_entry = _entry("A006672", ["5", "10", "16", "23", "31", "40", "50"], offset="1,1")
    base_a = {
        "seq": "A006672",
        "current_entry_text": a_entry,
        "new_data": None,
        "new_extensions_lines": [],
        "discussion_note": "References and links are now ordered by the surname of the first author.",
        "paste_date": "Aug 13 2026",
        "scope": "full",
    }
    fx["a006672_red"] = dict(base_a, new_references=list(_A006672_REFS_RED),
                             new_links=list(_A006672_LINKS_RED))
    fx["a006672_green"] = dict(base_a, new_references=list(_A006672_REFS_GREEN),
                               new_links=list(_A006672_LINKS_GREEN))

    # (b) A217058 lesson -- Tanbir Ahmed's existing EXTENSIONS line lost its underscores.
    b_entry = _entry("A217058",
                     ["77", "152", "269", "439", "644", "906", "1204", "1559"],
                     offset="1,1", keywords="nonn,hard,more",
                     E=["a(6)-a(8) from _Tanbir Ahmed_, Aug 24 2012"])
    base_b = {
        "seq": "A217058",
        "current_entry_text": b_entry,
        "new_data": "77, 152, 269, 439, 644, 906, 1204, 1559, 1972",
        "new_extensions_lines": ["a(9) from _Leo Y. Zhang_, Aug 13 2026"],
        "discussion_note": "Added a(9) = 1972, verified before submission.",
        "paste_date": "Aug 13 2026",
        "scope": "data-extensions-only",
        "certificate_gate_passed": True,
    }
    fx["a217058_red"] = dict(base_b, post_edit_extensions=[
        "a(6)-a(8) from Tanbir Ahmed, Aug 24 2012",           # underscores LOST
        "a(9) from _Leo Y. Zhang_, Aug 13 2026",
    ])
    fx["a217058_green"] = dict(base_b, post_edit_extensions=[
        "a(6)-a(8) from _Tanbir Ahmed_, Aug 24 2012",         # restored byte-for-byte
        "a(9) from _Leo Y. Zhang_, Aug 13 2026",
    ])

    # (c)/(d) A250026-style a(31) paste appending 41.
    d_terms = [str(i) for i in range(1, 31)]  # 30 existing terms, offset 1 -> next is a(31)
    d_entry = _entry("A250026", d_terms, offset="1,2", keywords="nonn,more",
                     E=["a(25)-a(30) from _Tanbir Ahmed_, Sep 05 2012"])
    base_d = {
        "seq": "A250026",
        "current_entry_text": d_entry,
        "new_data": ", ".join(d_terms + ["41"]),
        "new_extensions_lines": ["a(31) from _Leo Y. Zhang_, Aug 14 2026"],
        "discussion_note": "Added a(31) = 41, verified with the same search program as the earlier terms.",
        "paste_date": "Aug 14 2026",
        "scope": "data-extensions-only",
        "certificate_gate_passed": True,
    }
    fx["a250026_green"] = dict(base_d)
    fx["british_red"] = dict(
        base_d,
        discussion_note="Recomputed the colouring bound for the appended term as requested.")
    return fx


# --------------------------------------------------------------------------- #
# selftest
# --------------------------------------------------------------------------- #

def _unit_spec(**over):
    entry = _entry(over.pop("_seq", "A200001"),
                   over.pop("_terms", ["3", "6", "9", "12"]),
                   offset=over.pop("_offset", "1,1"),
                   keywords=over.pop("_keywords", "nonn,more"),
                   D=over.pop("_D", ()), H=over.pop("_H", ()), E=over.pop("_E", ()))
    spec = {
        "seq": "A200001",
        "current_entry_text": entry,
        "new_data": "3, 6, 9, 12, 15",
        "new_extensions_lines": ["a(5) from _Leo Y. Zhang_, Aug 13 2026"],
        "discussion_note": "Added a(5) = 15 with a verified certificate.",
        "paste_date": "Aug 13 2026",
        "scope": "data-extensions-only",
        "certificate_gate_passed": True,
    }
    spec.update(over)
    return spec


def selftest(verbose=True):
    TODAY = datetime.date(2026, 8, 13)
    fx = _fixture_specs()
    cases = []  # (name, spec, expect_ok, must_fail(set), exact(bool))

    # scenario fixtures ------------------------------------------------------
    cases.append(("a006672_red", fx["a006672_red"], False,
                  {"ref-alpha-by-first-author-surname", "link-order-alpha"}, True))
    cases.append(("a006672_green", fx["a006672_green"], True, set(), True))
    cases.append(("a217058_red", fx["a217058_red"], False,
                  {"ext-preserve-existing-lines"}, False))
    cases.append(("a217058_green", fx["a217058_green"], True, set(), True))
    cases.append(("british_red", fx["british_red"], False,
                  {"us-spelling-denylist"}, True))
    cases.append(("a250026_green", fx["a250026_green"], True, set(), True))

    # unit fixtures ----------------------------------------------------------
    cases.append(("u_green_base", _unit_spec(), True, set(), True))
    cases.append(("u_trailing_comma",
                  _unit_spec(new_data="3, 6, 9, 12, 15,"),
                  False, {"data-no-trailing-separator"}, False))
    cases.append(("u_missing_space",
                  _unit_spec(new_data="3,6, 9, 12, 15"),
                  False, {"data-comma-space-separated"}, False))
    cases.append(("u_bad_integer",
                  _unit_spec(new_data="3, 6, 9, 12, 1e5"),
                  False, {"data-integers-only"}, False))
    cases.append(("u_altered_term",
                  _unit_spec(new_data="3, 6, 9, 13, 15"),
                  False, {"data-append-only", "preserve-all-existing-lines"}, False))
    cases.append(("u_too_few_terms",
                  _unit_spec(_terms=["3", "6"], new_data="3, 6, 9",
                             new_extensions_lines=["a(3) from _Leo Y. Zhang_, Aug 13 2026"],
                             discussion_note="Added a(3) = 9 with a verified certificate."),
                  False, {"data-min-terms"}, True))
    cases.append(("u_negative_nonn",
                  _unit_spec(new_data="3, 6, 9, 12, -15"),
                  False, {"data-sign-keyword-consistency"}, True))
    cases.append(("u_gate_false",
                  _unit_spec(certificate_gate_passed=False),
                  False, {"data-terms-not-conjectured"}, True))
    g = dict(_unit_spec())
    del g["certificate_gate_passed"]
    cases.append(("u_gate_missing_warn_only", g, True, set(), True))
    cases.append(("u_ext_trailing_period",
                  _unit_spec(new_extensions_lines=["a(5) from _Leo Y. Zhang_, Aug 13 2026."]),
                  False, {"ext-line-format"}, False))
    cases.append(("u_ext_wrong_date",
                  _unit_spec(new_extensions_lines=["a(5) from _Leo Y. Zhang_, Aug 12 2026"]),
                  False, {"ext-date-is-paste-date"}, False))
    cases.append(("u_ext_invalid_date",
                  _unit_spec(new_extensions_lines=["a(5) from _Leo Y. Zhang_, Feb 30 2026"],
                             paste_date="Feb 30 2026"),
                  False, {"ext-date-format"}, False))
    cases.append(("u_ext_wrong_range",
                  _unit_spec(new_extensions_lines=["a(6) from _Leo Y. Zhang_, Aug 13 2026"]),
                  False, {"ext-term-range-matches-data"}, True))
    cases.append(("u_ext_inserted_not_appended",
                  _unit_spec(_E=["a(4) from _Old Contributor_, Jan 02 2000"],
                             post_edit_extensions=[
                                 "a(5) from _Leo Y. Zhang_, Aug 13 2026",
                                 "a(4) from _Old Contributor_, Jan 02 2000"]),
                  False, {"ext-appended-at-end"}, False))
    cases.append(("u_ext_housekeeping",
                  _unit_spec(new_extensions_lines=[
                      "a(5) from _Leo Y. Zhang_, Aug 13 2026",
                      "Added a comment. - _Leo Y. Zhang_, Aug 13 2026"]),
                  False, {"ext-no-housekeeping-notes"}, False))
    cases.append(("u_missing_ext_credit",
                  _unit_spec(new_extensions_lines=[]),
                  False, {"ext-term-range-matches-data"}, True))
    cases.append(("u_deleted_reference",
                  _unit_spec(scope="full",
                             _D=["K. Alpha, Book One, Springer, 2001.",
                                 "M. Beta, Book Two, Springer, 2002."],
                             new_references=["M. Beta, Book Two, Springer, 2002."]),
                  False, {"no-deletions", "preserve-all-existing-lines"}, True))
    cases.append(("u_refs_unsorted",
                  _unit_spec(scope="full",
                             _D=["K. Alpha, Book One, Springer, 2001."],
                             new_references=["M. Beta, Book Two, Springer, 2002.",
                                             "K. Alpha, Book One, Springer, 2001."]),
                  False, {"ref-alpha-by-first-author-surname"}, True))
    cases.append(("u_bfile_not_first",
                  _unit_spec(scope="full",
                             new_links=[
                                 'N. J. A. Sloane, <a href="https://doi.org/10.1000/x">A survey</a>',
                                 'N. J. A. Sloane, <a href="/A200001/b200001.txt">Table of n, a(n) for n = 1..100</a>']),
                  False, {"link-order-bfile-first"}, True))
    cases.append(("u_index_not_last",
                  _unit_spec(scope="full",
                             new_links=[
                                 '<a href="/index/Ra#vdW">Index entries for sequences related to van der Waerden numbers</a>',
                                 'N. J. A. Sloane, <a href="https://doi.org/10.1000/x">A survey</a>']),
                  False, {"link-order-index-last"}, True))
    cases.append(("u_bare_url_link",
                  _unit_spec(scope="full",
                             new_links=["John Doe, https://example.org/paper.pdf"]),
                  False, {"link-anchor-format"}, True))
    cases.append(("u_initials_unspaced",
                  _unit_spec(scope="full",
                             new_references=["J.S. Bach, The Art of Fugue, Leipzig, 1750."]),
                  False, {"ref-initials-spacing"}, True))
    cases.append(("u_email_in_note",
                  _unit_spec(discussion_note="Certificates available from foo@bar.com on request."),
                  False, {"no-email-address"}, True))
    cases.append(("u_tab_in_note",
                  _unit_spec(discussion_note="Added\ta(5) = 15 with a verified certificate."),
                  False, {"no-tabs-or-trailing-whitespace"}, True))
    cases.append(("u_nth_notation",
                  _unit_spec(discussion_note="This extends the nth term of the family."),
                  False, {"notation-ascii-operators"}, True))
    cases.append(("u_hyphenated_form",
                  _unit_spec(discussion_note="All appended values stay non-negative here."),
                  False, {"hyphenation-closed-forms"}, True))
    cases.append(("u_question_in_note",
                  _unit_spec(discussion_note="Should the offset change too?"),
                  False, {"discussion-no-open-question", "discussion-one-sentence"}, True))
    cases.append(("u_two_sentence_note",
                  _unit_spec(discussion_note="Added a(5). Please review."),
                  False, {"discussion-one-sentence"}, True))
    cases.append(("u_url_in_note",
                  _unit_spec(discussion_note="See https://oeis.org/draft for the run."),
                  False, {"discussion-no-url"}, True))
    cases.append(("u_full_month_date",
                  _unit_spec(discussion_note="Confirmed by a rerun on August 13 2026 exactly."),
                  False, {"ext-date-format"}, True))
    cases.append(("u_unicode_math",
                  _unit_spec(discussion_note="All appended terms are ≤ 100 here."),
                  False, {"no-non-ascii"}, True))
    cases.append(("u_unicode_name_warn_only",
                  _unit_spec(scope="full",
                             new_references=["J. Dybizbański, Some vdW paper, Elsevier, 2015."]),
                  True, set(), True))
    cases.append(("u_bfile_mention_in_scope",
                  _unit_spec(discussion_note="A b-file upload will follow shortly."),
                  False, {"no-b-file"}, True))
    cases.append(("u_scope_violation",
                  _unit_spec(new_references=["K. Alpha, Book One, Springer, 2001."]),
                  False, {"scope-data-extensions-only"}, True))
    cases.append(("u_unwrapped_signature",
                  _unit_spec(new_extensions_lines=["a(5) from Leo Y. Zhang, Aug 13 2026"]),
                  False, {"sign-name-underscore-markup", "ext-line-format"}, False))
    cases.append(("u_start_without_end",
                  _unit_spec(scope="full",
                             new_comments=["From _Leo Y. Zhang_, Aug 13 2026: (Start)",
                                           "A first fact about the sequence."]),
                  False, {"sign-multiparagraph-wrapper"}, True))
    cases.append(("u_start_end_balanced",
                  _unit_spec(scope="full",
                             new_comments=["From _Leo Y. Zhang_, Aug 13 2026: (Start)",
                                           "A first fact about the sequence.",
                                           "(End)"]),
                  True, set(), True))
    cases.append(("u_bad_comment_signature",
                  _unit_spec(scope="full",
                             new_comments=["A fact worth recording - _Leo Y. Zhang_, Aug 13 2026"]),
                  False, {"sign-comment-format"}, True))
    long_terms = [str(10**7 + i) for i in range(60)]
    cases.append(("u_long_data_warn_only",
                  _unit_spec(_terms=long_terms,
                             new_data=", ".join(long_terms + ["99999999"]),
                             new_extensions_lines=["a(61) from _Leo Y. Zhang_, Aug 13 2026"],
                             discussion_note="Added a(61) with a verified certificate."),
                  True, set(), True))
    cases.append(("u_paste_date_bad",
                  _unit_spec(paste_date="13 Aug 2026",
                             new_extensions_lines=["a(5) from _Leo Y. Zhang_, Aug 13 2026"]),
                  False, {"ext-date-format"}, False))

    n_pass = n_fail = 0
    failures = []
    for name, spec, expect_ok, must_fail, exact in cases:
        try:
            findings, statuses, ok = lint_spec(spec, today=TODAY)
        except LintInputError as e:
            failures.append("%s: LintInputError %s" % (name, e))
            n_fail += 1
            continue
        failed_rules = {r for lvl, r, _ in findings if lvl == "FAIL"}
        problems = []
        if ok != expect_ok:
            problems.append("expected ok=%s got %s (failed rules: %s)"
                            % (expect_ok, ok, sorted(failed_rules)))
        missing = must_fail - failed_rules
        if missing:
            problems.append("expected failing rules missing: %s" % sorted(missing))
        if exact and expect_ok is False:
            extra = failed_rules - must_fail - {"preserve-all-existing-lines"}
            if extra:
                problems.append("unexpected extra failures: %s" % sorted(extra))
        if exact and expect_ok is True and failed_rules:
            problems.append("green case has failures: %s" % sorted(failed_rules))
        if problems:
            failures.append("%s: %s" % (name, "; ".join(problems)))
            n_fail += 1
        else:
            n_pass += 1
            if verbose:
                print("ok   %s" % name)
    if failures:
        for f in failures:
            print("SELFTEST FAIL %s" % f)
    print("SELFTEST: %d cases, %d passed, %d failed" % (len(cases), n_pass, n_fail))
    return 0 if n_fail == 0 else 1


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #

def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "--selftest":
        return selftest()
    if argv[0] == "--emit-fixtures":
        if len(argv) < 2:
            print("--emit-fixtures needs a directory", file=sys.stderr)
            return 2
        import os
        os.makedirs(argv[1], exist_ok=True)
        for name, spec in _fixture_specs().items():
            p = os.path.join(argv[1], name + ".json")
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(spec, fh, indent=2, ensure_ascii=False)
            print("wrote %s" % p)
        return 0
    as_json = "--json" in argv
    path = [a for a in argv if not a.startswith("--")][0]
    try:
        spec, findings, statuses, ok = lint_file(path)
    except (LintInputError, json.JSONDecodeError, OSError) as e:
        print("oeis_lint: input error: %s" % e, file=sys.stderr)
        return 2
    if as_json:
        print(json.dumps({
            "seq": spec.get("seq"), "ok": ok,
            "failures": [{"rule": r, "message": m} for lvl, r, m in findings if lvl == "FAIL"],
            "warnings": [{"rule": r, "message": m} for lvl, r, m in findings if lvl == "WARN"],
            "statuses": statuses,
        }, indent=2, ensure_ascii=False))
    else:
        print(render_report(spec.get("seq"), findings, statuses, ok))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

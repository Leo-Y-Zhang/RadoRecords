#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Adversarial attack suite for oeis_lint.py.

Each attack is a subtly-violating paste spec. An attack is CAUGHT iff the
linter returns ok=False (exit 1, at least one FAIL). WARN-only = MISSED,
because the workflow pastes on exit 0.
"""
import os
import sys
import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from oeis_lint import lint_spec, _entry

TODAY = datetime.date(2026, 8, 13)


def base(**over):
    """Green one-term paste on a 4-term fixture entry; attacks mutate it."""
    entry_kw = {}
    for k in ("_seq", "_terms", "_offset", "_keywords", "_D", "_H", "_E"):
        if k in over:
            entry_kw[k.lstrip("_")] = over.pop(k)
    seq = entry_kw.pop("seq", "A200001")
    terms = entry_kw.pop("terms", ["3", "6", "9", "12"])
    entry = _entry(seq, terms,
                   offset=entry_kw.pop("offset", "1,1"),
                   keywords=entry_kw.pop("keywords", "nonn,more"),
                   D=entry_kw.pop("D", ()), H=entry_kw.pop("H", ()),
                   E=entry_kw.pop("E", ()))
    spec = {
        "seq": seq,
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


ATTACKS = []


def attack(name, desc, **over):
    ATTACKS.append((name, desc, base(**over)))


# ---- ordering attacks -------------------------------------------------------
attack("A01_same_surname_firstname_misorder",
       "Zoe Smith listed before Adam Smith, same year: tie must break on given name",
       scope="full",
       new_references=[
           "Zoe Smith, Zeta function bounds, Springer, 2005.",
           "Adam Smith, Alpha colorings of the integers, Springer, 2005.",
       ])

attack("A02_capitalized_particle_De_Loera",
       "J. A. De Loera sorts under 'De Loera' (D), so must precede Katz; byte sort by 'Loera' hides it",
       scope="full",
       new_references=[
           "M. Katz, Combinatorial convexity, AMS, 2010.",
           "J. A. De Loera, Triangulations of point sets, Springer, 2012.",
       ])

attack("A03_diacritic_sorted_by_byte_value",
       "Öhman placed after Zhang (byte order); normalized 'ohman' < 'zhang' means out of order",
       scope="full",
       new_references=[
           "A. Zhang, Alpha sequences, Elsevier, 2001.",
           "L. Öhman, Beta sequences and progressions, Elsevier, 2002.",
       ])

attack("A04_institutional_author_misplaced",
       "UCSD (u) link sits between Bloom (b) and Tse (t)",
       scope="full",
       new_links=[
           'G. S. Bloom, <a href="https://doi.org/10.1002/jgt.3190010000">A note on generalized Ramsey numbers</a>',
           'UCSD Mathematics Department, <a href="https://mathweb.ucsd.edu/~vdw/">Van der Waerden number pages</a>',
           'Kung-Kuen Tse, <a href="https://arxiv.org/abs/math/0409000">On some van der Waerden type numbers</a>',
       ])

attack("A05_refs_sorted_but_links_not",
       "References alphabetized, Links section left unsorted (Tse before Bloom)",
       scope="full",
       new_references=[
           "G. Alpha, First topics, AMS, 2001.",
           "K. Beta, Second topics, AMS, 2002.",
       ],
       new_links=[
           'Kung-Kuen Tse, <a href="https://arxiv.org/abs/math/0409000">On some van der Waerden type numbers</a>',
           'G. S. Bloom, <a href="https://doi.org/10.1002/jgt.3190010000">A note on generalized Ramsey numbers</a>',
       ])

attack("A19_et_al_ref_misparsed_as_institution",
       "'T. Brown et al.' placed after Davis; et-al misparse must not hide surname 'Brown'",
       scope="full",
       new_references=[
           "C. Davis, Convexity theory, Wiley, 1955.",
           "T. Brown et al., A density version of the Hales-Jewett theorem, CUP, 2000.",
       ])

# ---- preservation attacks ---------------------------------------------------
attack("A06_existing_ref_period_dropped",
       "Existing reference reproduced with its final period silently dropped",
       scope="full",
       _D=["B. M. Landman and A. Robertson, Ramsey Theory on the Integers, AMS, 2014.",
           "T. D. Parsons, Ramsey graphs and block designs, Trans. Amer. Math. Soc., 209 (1975), 33-44."],
       new_references=[
           "B. M. Landman and A. Robertson, Ramsey Theory on the Integers, AMS, 2014.",
           "T. D. Parsons, Ramsey graphs and block designs, Trans. Amer. Math. Soc., 209 (1975), 33-44",
       ])

attack("A07_underscores_stripped_one_of_three",
       "Middle of three existing EXTENSIONS lines loses its author underscores",
       _terms=[str(3 * i) for i in range(1, 11)],
       new_data=", ".join(str(3 * i) for i in range(1, 11)) + ", 33",
       _E=["a(6)-a(8) from _Tanbir Ahmed_, Aug 24 2012",
           "a(9) from _Bert Dobbelaere_, Jan 05 2020",
           "a(10) from _Rachel Barnett_, Mar 11 2023"],
       new_extensions_lines=["a(11) from _Leo Y. Zhang_, Aug 13 2026"],
       post_edit_extensions=[
           "a(6)-a(8) from _Tanbir Ahmed_, Aug 24 2012",
           "a(9) from Bert Dobbelaere, Jan 05 2020",
           "a(10) from _Rachel Barnett_, Mar 11 2023",
           "a(11) from _Leo Y. Zhang_, Aug 13 2026",
       ],
       discussion_note="Added a(11) = 33 with a verified certificate.")

attack("A13_silent_term_change_while_appending",
       "a(3) changed 9 -> 10 in the same paste that appends a(5)",
       new_data="3, 6, 10, 12, 15")

attack("A18_empty_links_list_vs_null",
       "new_links=[] (deleting the whole Links section) instead of null (untouched)",
       _H=['Tanbir Ahmed, <a href="http://www.integers-ejcnt.org/j6/j6.Abstract.html">Some new van der Waerden numbers</a>'],
       new_links=[])

# ---- date attacks -----------------------------------------------------------
attack("A08_full_month_name",
       "EXTENSIONS dated 'August 13 2026' instead of 'Aug 13 2026'",
       new_extensions_lines=["a(5) from _Leo Y. Zhang_, August 13 2026"])

attack("A09_no_zero_pad_day",
       "'Aug 4 2026' -- OEIS zero-pads (verified live: Aug 07 2026 / Jul 30 2026 / Jan 09 2009)",
       new_extensions_lines=["a(5) from _Leo Y. Zhang_, Aug 4 2026"],
       paste_date="Aug 4 2026")

attack("A27_invalid_calendar_date",
       "Feb 30 2026 is well-formed but not a real date",
       new_extensions_lines=["a(5) from _Leo Y. Zhang_, Feb 30 2026"],
       paste_date="Feb 30 2026")

# ---- DATA formatting attacks ------------------------------------------------
attack("A11_data_double_space",
       "double space between two DATA terms",
       new_data="3, 6,  9, 12, 15")

attack("A12_data_trailing_comma",
       "DATA ends with a trailing comma",
       new_data="3, 6, 9, 12, 15,")

attack("A22_leading_zero_term",
       "appended term written '015' -- not a valid DATA integer rendering",
       new_data="3, 6, 9, 12, 015")

attack("A24_unicode_minus_in_data",
       "U+2212 minus sign instead of ASCII hyphen in appended term",
       new_data="3, 6, 9, 12, \u221215")

# ---- signature attacks ------------------------------------------------------
attack("A14_ext_leo_missing_Y",
       "extension credited to _Leo Zhang_ (registered name is Leo Y. Zhang)",
       new_extensions_lines=["a(5) from _Leo Zhang_, Aug 13 2026"])

attack("A15_comment_signed_leo_missing_Y",
       "comment signed '- _Leo Zhang_, Aug 13 2026' -- wrong registered name, underscore-wrapped",
       scope="full",
       new_comments=["The corresponding certificate has been archived. - _Leo Zhang_, Aug 13 2026"])

attack("A20_single_term_range_style",
       "single-term credit written a(5)-a(5) instead of a(5)",
       new_extensions_lines=["a(5)-a(5) from _Leo Y. Zhang_, Aug 13 2026"])

attack("A25_ext_trailing_space",
       "trailing space after the extension date",
       new_extensions_lines=["a(5) from _Leo Y. Zhang_, Aug 13 2026 "])

attack("A26_housekeeping_extension",
       "'Added a link ...' housekeeping note smuggled into EXTENSIONS",
       new_extensions_lines=[
           "a(5) from _Leo Y. Zhang_, Aug 13 2026",
           "Added a link to the certificate archive. - _Leo Y. Zhang_, Aug 13 2026",
       ])

attack("A23_reversed_range_claim",
       "two terms appended but credit claims a(6)-a(5) (reversed)",
       new_data="3, 6, 9, 12, 15, 18",
       new_extensions_lines=["a(6)-a(5) from _Leo Y. Zhang_, Aug 13 2026"])

# ---- prose / note attacks ---------------------------------------------------
attack("A10_behaviour_mid_sentence",
       "British 'behaviour' buried mid-sentence in the note",
       discussion_note="The added term keeps the asymptotic behaviour of the family unchanged.")

attack("A16_two_sentence_note",
       "discussion note is two sentences",
       discussion_note="Added a(5) = 15. The certificate is archived.")

attack("A17_note_no_terminal_period",
       "discussion note does not end with a period",
       discussion_note="Added a(5) = 15 with a verified certificate")

attack("A21_bfile_unhyphenated",
       "'bfile' spelled without the hyphen dodges the b-file word check",
       discussion_note="A bfile with further terms will follow.")

attack("A28_url_in_note",
       "URL in the discussion note without note_may_reference_url",
       discussion_note="See https://oeis.org/draft/A200001 for the certificate discussion.")


def run():
    caught = missed = 0
    rows = []
    for name, desc, spec in ATTACKS:
        findings, statuses, ok = lint_spec(spec, today=TODAY)
        fails = sorted({r for lvl, r, _ in findings if lvl == "FAIL"})
        warns = sorted({r for lvl, r, _ in findings if lvl == "WARN"})
        verdict = "MISSED" if ok else "CAUGHT"
        if ok:
            missed += 1
        else:
            caught += 1
        rows.append((verdict, name, desc, fails, warns))
    for verdict, name, desc, fails, warns in rows:
        print("%-6s %s" % (verdict, name))
        print("       attack: %s" % desc)
        if fails:
            print("       FAIL rules: %s" % ", ".join(fails))
        if warns:
            print("       warn rules: %s" % ", ".join(warns))
    print()
    print("SUITE: %d attacks, %d caught, %d MISSED" % (len(ATTACKS), caught, missed))
    return 0 if missed == 0 else 1


if __name__ == "__main__":
    sys.exit(run())

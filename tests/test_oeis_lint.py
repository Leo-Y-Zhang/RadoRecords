import datetime
import json

import pytest

import oeis_lint


TODAY = datetime.date(2026, 8, 13)
ENTRY = '%S A000001 3,6,9,12\n%K A000001 nonn,more\n%O A000001 1,1'


def spec(**changes):
    return dict({'current_entry_text': ENTRY, 'paste_date': 'Aug 13 2026',
                 'scope': 'data-extensions-only'}, **changes)


def test_valid_four_term_spec_is_accepted():
    findings, statuses, ok = oeis_lint.lint_spec(spec(), today=TODAY)
    assert ok, findings
    assert statuses['data-min-terms'] == 'PASS'


@pytest.mark.parametrize('new_data', ['3, 7, 9, 12', '3, 6, 9'])
def test_changed_or_removed_term_is_rejected(new_data):
    _findings, statuses, ok = oeis_lint.lint_spec(spec(new_data=new_data), today=TODAY)
    assert not ok
    assert statuses['data-append-only'] == 'FAIL'
    assert statuses['preserve-all-existing-lines'] == 'FAIL'


def test_parser_preserves_all_data_lines_and_signed_offset():
    text = ('%S A000001 1,2,\n%T A000001 3,4\n%U A000001 5,6\n'
            '%O A000001 -2,1\n%K A000001 sign,more')
    parsed = oeis_lint.parse_internal(text)
    assert parsed['terms'] == ['1', '2', '3', '4', '5', '6']
    assert parsed['offset'] == -2
    assert parsed['keywords'] == ['sign', 'more']


@pytest.mark.parametrize('text', ['', '%S', 'A000001 1,2', '%S A000001 1\nbroken'])
def test_parser_rejects_empty_or_truncated_internal_lines(text):
    with pytest.raises(oeis_lint.LintInputError):
        oeis_lint.parse_internal(text)


def test_preservation_counts_duplicate_lines():
    assert oeis_lint._multiset_lost(['same', 'same'], ['same', 'same']) is None
    assert oeis_lint._multiset_lost(['same', 'same'], ['same']) == 'same'
    assert oeis_lint._new_lines(['same'], ['same', 'same']) == ['same']


@pytest.mark.parametrize('month,day,year,valid', [
    ('Feb', 29, 2024, True), ('Feb', 29, 2025, False),
    ('Apr', 30, 2026, True), ('Apr', 31, 2026, False),
    ('Jan', 0, 2026, False), ('Unknown', 1, 2026, False),
])
def test_date_validation_includes_last_day(month, day, year, valid):
    assert oeis_lint._valid_date(month, day, year) is valid


def test_truncated_spec_json_is_rejected(tmp_path):
    path = tmp_path / 'paste.json'
    path.write_text('{"current_entry_text":')
    with pytest.raises(json.JSONDecodeError):
        oeis_lint.lint_file(path, today=TODAY)

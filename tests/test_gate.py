import itertools
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import verify_all


@pytest.fixture
def gate_evidence(monkeypatch, tmp_path):
    """One tiny claim exercises metadata checks without the large exhaustion."""
    monkeypatch.setattr(verify_all, 'CLAIMS', {})
    monkeypatch.setattr(verify_all.drat_certify, 'EXPECTED', {})
    monkeypatch.setattr(verify_all, 'LAZY_CLAIMS', {9: 4})
    monkeypatch.setattr(verify_all.drat_certify, 'LAZY_EXPECTED', {9: 4})
    monkeypatch.setattr(verify_all, 'BRUTE_PINS', {})
    monkeypatch.setattr(verify_all, 'EVID', str(tmp_path))
    monkeypatch.setattr(verify_all, '_pass', [])
    monkeypatch.setattr(verify_all, '_fail', [])
    monkeypatch.setattr(verify_all.brute_force, 'brute_sat', lambda *a, **kw: (False, None, 0))
    monkeypatch.setattr(verify_all.drat_certify, 'find_tools', lambda: ({}, ['mock-tools']))
    monkeypatch.setattr(verify_all.subprocess, 'run',
                        lambda *a, **kw: SimpleNamespace(returncode=0, stdout='SELFTEST PASSED'))
    # Enumeration and brute-force mathematics have independent tests; here
    # they are stubs so each metadata corruption reaches the gate quickly.
    monkeypatch.setattr(verify_all.encode, 'iter_supports', lambda *a, **kw: [])
    monkeypatch.setattr(itertools, 'combinations_with_replacement', lambda *a: [])
    convention = {'distinct': False, 'z_colored': True}
    ref = {'n': 9, 'N': 4, 'sat': False, 'convention': convention,
           'clauses': 2, 'justifications': [{'support': [1, 3], 'x': [[1, 9]], 'z': 3}]}
    wit = {'n': 9, 'N': 3, 'sat': True, 'coloring': '001', 'convention': convention}
    for mode in ['lazy', 'reach']:
        (tmp_path / f'{mode}_n9_N4.json').write_text(json.dumps(ref))
        (tmp_path / f'{mode}_n9_N3.json').write_text(json.dumps(wit))
    sample = {'justifications': [{'x': [[1, 33], [2, 4]], 'z': 7}]}
    (tmp_path / 'lazy_n37_N45.json').write_text(json.dumps(sample))
    return tmp_path


def test_gate_accepts_consistent_evidence(gate_evidence, capsys):
    assert verify_all.main() == 0
    assert not verify_all._fail


@pytest.mark.parametrize('file,corruption,failed_check', [
    ('lazy_n9_N4.json', 'empty', 'clause count'),
    ('lazy_n9_N4.json', 'wrong-count', 'clause count'),
    ('lazy_n9_N4.json', 'removed-support', 'support of its own solution'),
    ('lazy_n9_N4.json', 'changed-value', 'justified by a real solution'),
    ('lazy_n9_N4.json', 'wrong-n', 'pinned convention'),
    ('lazy_n9_N4.json', 'convention', 'pinned convention'),
    ('reach_n9_N4.json', 'wrong-N', 'right N'),
    ('reach_n9_N4.json', 'wrong-n', 'right N'),
    ('reach_n9_N4.json', 'convention', 'pinned convention'),
    ('reach_n9_N3.json', 'color', 'witness re-verified'),
    ('reach_n9_N3.json', 'missing', 'evidence present'),
])
def test_gate_rejects_specific_evidence_corruptions(gate_evidence, capsys, file,
                                                 corruption, failed_check):
    path = gate_evidence / file
    doc = json.loads(path.read_text())
    if corruption == 'empty':
        doc.update(clauses=0, justifications=[])
    elif corruption == 'wrong-count':
        doc['clauses'] += 2
    elif corruption == 'removed-support':
        doc['justifications'][0]['support'].remove(3)
    elif corruption == 'changed-value':
        doc['justifications'][0]['x'][0][0] = 2
    elif corruption == 'wrong-n':
        doc['n'] += 1
    elif corruption == 'wrong-N':
        doc['N'] -= 1
    elif corruption == 'convention':
        doc['convention']['z_colored'] = False
    elif corruption == 'color':
        doc['coloring'] = '00x'
    if corruption == 'missing':
        path.unlink()
    else:
        path.write_text(json.dumps(doc))
    assert verify_all.main() == 1
    assert any(failed_check in name for name in verify_all._fail), verify_all._fail


def test_truncated_evidence_is_not_accepted(gate_evidence):
    Path(gate_evidence / 'lazy_n9_N4.json').write_text('{"sat": false')
    with pytest.raises(json.JSONDecodeError):
        verify_all.main()

import pytest

import brute_force


def test_support_masks_use_the_value_minus_one_bit():
    assert brute_force.support_masks(2, 5) == [0b11100]
    assert set(brute_force.support_masks(9, 3)) == {0b101}


def test_small_sat_witness_and_exact_checked_count():
    # Masks c=0..3 color 3,4,5 alike; c=4 is the first good coloring.
    assert brute_force.brute_sat(2, 5, cross_check=True) == (True, '00100', 5)
    assert brute_force.brute_sat(2, 2) == (True, '00', 1)


def test_exhausted_instance_returns_no_witness():
    assert brute_force.brute_sat(9, 15, cross_check=True) == (False, None, 1 << 14)


def test_budget_expiry_is_not_an_unsat_result(monkeypatch):
    times = iter([10.0, 12.0])
    monkeypatch.setattr(brute_force.time, 'time', lambda: next(times))
    with pytest.raises(TimeoutError, match='budget exceeded'):
        brute_force.brute_sat(2, 5, budget_s=1)


def test_positive_budget_allows_small_result(monkeypatch):
    monkeypatch.setattr(brute_force.time, 'time', lambda: 10.0)
    assert brute_force.brute_sat(2, 5, budget_s=1)[0] is True

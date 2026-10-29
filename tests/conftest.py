from itertools import combinations, combinations_with_replacement
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'rado'), str(ROOT / 'tools')]


@pytest.fixture
def arithmetic_solutions():
    """Tiny ground truth, independent of the bitsets and support enumerator."""
    def enumerate_solutions(n, N, distinct=False):
        choose = combinations if distinct else combinations_with_replacement
        return [(xs, z) for xs in choose(range(1, N + 1), n)
                for z in range(1, N + 1)
                if sum(x * x for x in xs) == z * z]
    return enumerate_solutions

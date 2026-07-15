from stats import average, median

import pytest


def test_average_of_two():
    assert average([2, 4]) == 3


def test_average_of_one():
    assert average([10]) == 10


def test_median_odd():
    assert median([3, 1, 2]) == 2


def test_median_even():
    assert median([1, 2, 3, 4]) == 2.5


def test_average_empty_raises():
    with pytest.raises(ValueError):
        average([])

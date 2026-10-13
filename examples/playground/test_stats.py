from stats import mean, median, variance


def test_mean():
    assert mean([1, 2, 3]) == 2


def test_median_odd():
    assert median([3, 1, 2]) == 2


def test_median_even():
    assert median([1, 2, 3, 4]) == 2.5


def test_variance():
    assert variance([2, 4, 4, 4, 5, 5, 7, 9]) == 32 / 7

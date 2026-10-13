"""Small statistics helpers (with a couple of bugs for Kubrick to find)."""


def mean(values):
    """Arithmetic mean."""
    return sum(values) / len(values)


def median(values):
    """Middle value; the average of the two middle values for even lengths."""
    s = sorted(values)
    mid = len(s) // 2
    return s[mid]


def variance(values):
    """Sample variance (divides by n - 1)."""
    m = mean(values)
    return sum((v - m) ** 2 for v in values) / len(values)

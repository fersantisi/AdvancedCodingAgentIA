"""Tiny statistics helpers used for the agent demo."""


def average(numbers):
    """Return the arithmetic mean of a non-empty list of numbers."""
    if not numbers:
        raise ValueError("average() requires at least one number")
    return sum(numbers) / len(numbers)


def median(numbers):
    """Return the median of a non-empty list of numbers."""
    if not numbers:
        raise ValueError("median() requires at least one number")
    ordered = sorted(numbers)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2

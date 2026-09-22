# select: RT,YD
"""Module docstring."""


def rt01():  # expect: RT01
    """Summary."""
    return 1


def rt02():  # expect: RT02
    """
    Summary.

    Returns
    -------
    value : int
        A number.
    """
    return 1


def rt03():  # expect: RT03
    """
    Summary.

    Returns
    -------
    int
    """
    return 1


def rt04():  # expect: RT04
    """
    Summary.

    Returns
    -------
    int
        a number.
    """
    return 1


def rt05():  # expect: RT05
    """
    Summary.

    Returns
    -------
    int
        A number
    """
    return 1


def yd01():  # expect: YD01
    """Summary."""
    yield 1


def returns_none_is_fine():
    """Summary."""
    return None


def nested_return_ignored():
    """Summary."""

    def inner():
        return 1

    inner()

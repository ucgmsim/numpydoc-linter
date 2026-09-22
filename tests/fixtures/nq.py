"""Suppression comments that do, and do not, earn their place.

The bare spellings are exercised in ``tests/test_suppression.py`` instead:
numpydoc does not recognise them, so a fixture carrying one would look like a
rule divergence to the parity test.
"""


def needed():  # numpydoc ignore=GL08
    pass


def partly_needed():  # numpydoc ignore=GL08,RT01  # expect: NQ01
    pass


def nothing_to_suppress(x):  # numpydoc ignore=SS03  # expect: NQ01
    """
    Summarise.

    Parameters
    ----------
    x : int
        The value.

    Returns
    -------
    int
        The value.
    """
    return x


def typo(x):  # numpydoc ignore=GL99  # expect: NQ02
    """
    Summarise.

    Parameters
    ----------
    x : int
        The value.

    Returns
    -------
    int
        The value.
    """
    return x


def buried(x):
    """
    Summarise.

    Parameters
    ----------
    x : int
        The value.

    Returns
    -------
    int
        The value.
    """
    y = x + 1  # numpydoc ignore=GL08  # expect: NQ01
    return y


def belongs_to_another_linter(x):  # noqa: F401
    """
    Summarise.

    Parameters
    ----------
    x : int
        The value.

    Returns
    -------
    int
        The value.
    """
    return x


def rule_is_not_enabled(x):  # numpydoc ignore=ES01
    """
    Summarise.

    Parameters
    ----------
    x : int
        The value.

    Returns
    -------
    int
        The value.
    """
    return x

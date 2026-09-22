# select: SA,EX
"""Module docstring."""


def sa01():  # expect: EX01,SA01
    """Summary."""


def sa02():  # expect: SA02
    """
    Summary.

    See Also
    --------
    other : No period here

    Examples
    --------
    >>> sa02()
    """


def sa03():  # expect: SA03
    """
    Summary.

    See Also
    --------
    other : lower case.

    Examples
    --------
    >>> sa03()
    """


def sa04():  # expect: SA04
    """
    Summary.

    See Also
    --------
    other

    Examples
    --------
    >>> sa04()
    """


def ex01():  # expect: EX01
    """
    Summary.

    See Also
    --------
    other : Something.
    """

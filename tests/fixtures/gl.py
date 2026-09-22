# select: GL,DS
"""Module docstring."""


def gl01():  # expect: GL01,GL03
    """

    Summary.
    """


def gl02():  # expect: GL02
    """
    Summary."""


def gl03():  # expect: GL03
    """
    Summary.


    More text.
    """


def gl05():  # expect: GL05
    """
	Summary.
    """


def gl06():  # expect: GL06,GL07
    """
    Summary.

    Bogus Section
    -------------
    Nothing.
    """


def gl07(x):  # expect: GL07
    """
    Summary.

    Returns
    -------
    int
        A number.

    Parameters
    ----------
    x : int
        The x.
    """


def gl08():  # expect: GL08
    pass


def gl09():  # expect: GL09
    """
    Summary.

    Something else first.

    .. deprecated:: 1.0
        Gone.
    """


def gl10():  # expect: GL10
    """
    Summary.

    .. versionadded: 1.0
    """


def ds01():  # expect: DS01
    """
    Summary.

    See Also
    --------
    : this is invalid
    """

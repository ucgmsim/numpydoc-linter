# select: SS,ES
"""Module docstring."""


def ss01():  # expect: ES01,SS01
    """
    Parameters
    ----------
    x : int
        The x.
    """


def ss02():  # expect: SS02
    """
    lower case summary.

    Extended.
    """


def ss03():  # expect: SS03
    """
    No period here

    Extended.
    """


def ss04():  # expect: SS04
    """
      Indented summary.

    Extended.
    """


def ss05():  # expect: SS05
    """
    Generates a thing.

    Extended.
    """


def ss06():  # expect: SS06
    """
    A summary that runs on
    across two lines.
    """


def es01():  # expect: ES01
    """Summary only."""

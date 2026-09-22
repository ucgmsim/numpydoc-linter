# select: PR
"""Module docstring."""


def pr01(alpha, beta):  # expect: PR01
    """
    Summary.

    Parameters
    ----------
    alpha : int
        The alpha.
    """


def pr02(alpha):  # expect: PR02
    """
    Summary.

    Parameters
    ----------
    alpha : int
        The alpha.
    gamma : int
        Not real.
    """


def pr03(alpha, beta):  # expect: PR03
    """
    Summary.

    Parameters
    ----------
    beta : int
        The beta.
    alpha : int
        The alpha.
    """


def pr04(alpha):  # expect: PR04
    """
    Summary.

    Parameters
    ----------
    alpha
        The alpha.
    """


def pr05(alpha):  # expect: PR05
    """
    Summary.

    Parameters
    ----------
    alpha : int.
        The alpha.
    """


def pr06(alpha):  # expect: PR06
    """
    Summary.

    Parameters
    ----------
    alpha : integer
        The alpha.
    """


def pr07(alpha):  # expect: PR07
    """
    Summary.

    Parameters
    ----------
    alpha : int
    """


def pr08(alpha):  # expect: PR08
    """
    Summary.

    Parameters
    ----------
    alpha : int
        the alpha.
    """


def pr09(alpha):  # expect: PR09
    """
    Summary.

    Parameters
    ----------
    alpha : int
        The alpha
    """


def pr10(alpha):  # expect: PR01,PR02,PR10
    """
    Summary.

    Parameters
    ----------
    alpha: int
        The alpha.
    """

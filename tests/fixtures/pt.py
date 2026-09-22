# select: PT,SS02,SS03
"""Module docstring."""

import functools


class Shape:
    """A shape."""

    @property
    def good(self) -> float:
        """float: The area in square metres."""
        return 1.0

    @property
    def missing_type(self) -> float:  # expect: PT01
        """The area in square metres."""
        return 1.0

    @property
    def wrong_type(self) -> int:  # expect: PT02
        """float: The count."""
        return 1

    @property
    def has_returns(self) -> float:  # expect: PT03
        """
        float: The area.

        Returns
        -------
        float
            The area.
        """
        return 1.0

    @functools.cached_property
    def cached_good(self) -> str:
        """str: The cached name."""
        return "x"

    @property
    def unannotated(self):
        """float: No annotation to compare against."""
        return 1.0

    @property
    def lower_summary(self) -> float:  # expect: SS02
        """float: the area in square metres."""
        return 1.0

    @property
    def no_period(self) -> float:  # expect: SS03
        """float: The area"""
        return 1.0

    def regular_method(self) -> float:
        """
        Compute something.

        Returns
        -------
        float
            A number.
        """
        return 1.0

# select: GL08
"""Module docstring."""

from typing import overload


def public_function():  # expect: GL08
    pass


def _private_helper():
    pass


class Widget:
    """A widget."""

    def method(self):  # expect: GL08
        pass

    def _private_method(self):
        pass

    def __repr__(self):  # expect: GL08
        pass

    def __init__(self):
        pass

    @property
    def size(self):
        pass

    @staticmethod
    def helper():  # expect: GL08
        pass

    @overload
    def get(self, key: str) -> str: ...

    def get(self, key):  # expect: GL08
        pass

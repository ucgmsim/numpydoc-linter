"""Load third-party rules."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from importlib.metadata import entry_points
from pathlib import Path

from numpydoc_linter.rules.base import Registry, registry

#: Entry-point group packaged rule providers advertise themselves under.
ENTRY_POINT_GROUP = "numpydoc_linter.rules"

_loaded: set[str] = set()


class PluginError(RuntimeError):
    """Raised when a plugin cannot be imported or does not register rules."""


def _register_module(module: object, target: Registry) -> None:
    """
    Let a module add its rules to a registry.

    A module may expose ``register(registry)``, or simply decorate its rules
    with the shared registry at import time.

    Parameters
    ----------
    module : object
        The imported module.
    target : Registry
        Registry to add rules to.
    """
    hook = getattr(module, "register", None)
    if callable(hook):
        hook(target)


def load_entry_points(target: Registry = registry) -> list[str]:
    """
    Load every packaged rule provider.

    Parameters
    ----------
    target : Registry
        Registry to add rules to.

    Returns
    -------
    list of str
        Names of the providers that were loaded.
    """
    loaded: list[str] = []
    try:
        points = entry_points(group=ENTRY_POINT_GROUP)
    except Exception:  # pragma: no cover - defensive
        return loaded
    for point in points:
        key = f"ep:{point.name}"
        if key in _loaded:
            continue
        try:
            module = point.load()
        except Exception as exc:  # pragma: no cover - defensive
            raise PluginError(f"could not load plugin {point.name!r}: {exc}") from exc
        _register_module(module, target)
        _loaded.add(key)
        loaded.append(point.name)
    return loaded


def load_path(spec: str, root: Path, target: Registry = registry) -> str:
    """
    Load rules from a local module, given a file path or a dotted name.

    Parameters
    ----------
    spec : str
        A path to a ``.py`` file, or an importable dotted module name.
    root : pathlib.Path
        Project root, which relative paths resolve against.
    target : Registry
        Registry to add rules to.

    Returns
    -------
    str
        The name the plugin was loaded under.

    Raises
    ------
    PluginError
        When the module cannot be imported.
    """
    key = f"path:{spec}"
    if key in _loaded:
        return spec

    if spec.endswith(".py"):
        path = Path(spec)
        if not path.is_absolute():
            path = root / path
        if not path.is_file():
            raise PluginError(f"plugin file not found: {path}")
        name = f"_numpydoc_linter_plugin_{path.stem}"
        module_spec = importlib.util.spec_from_file_location(name, path)
        if module_spec is None or module_spec.loader is None:
            raise PluginError(f"could not load plugin file: {path}")
        module = importlib.util.module_from_spec(module_spec)
        sys.modules[name] = module
        try:
            module_spec.loader.exec_module(module)
        except Exception as exc:
            raise PluginError(f"error importing plugin {path}: {exc}") from exc
    else:
        try:
            module = importlib.import_module(spec)
        except Exception as exc:
            raise PluginError(f"could not import plugin {spec!r}: {exc}") from exc

    _register_module(module, target)
    _loaded.add(key)
    return spec


def load_all(plugin_specs: tuple[str, ...], root: Path) -> None:
    """
    Load packaged and local plugins.

    Parameters
    ----------
    plugin_specs : tuple of str
        Local plugin paths or dotted module names from configuration.
    root : pathlib.Path
        Project root.
    """
    load_entry_points()
    for spec in plugin_specs:
        load_path(spec, root)

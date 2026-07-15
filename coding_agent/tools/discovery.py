"""Plugin auto-discovery for tools.

Scans a package (``coding_agent.tools.plugins`` by default) for concrete
:class:`~coding_agent.tools.base.Tool` subclasses with no-argument constructors
and returns instances of them. This lets new tools be added by dropping a file
in the plugins package, without editing the composition root.

Discovery is best-effort and never raises for a single bad module or a tool with
an unsupported constructor: it logs a warning and skips it, so a broken plugin
can never take the whole agent down.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil

from coding_agent.tools.base import Tool

logger = logging.getLogger(__name__)


def discover_tools(
    package: str = "coding_agent.tools.plugins",
    allowlist: tuple[str, ...] | None = None,
) -> list[Tool]:
    """Instantiate every no-arg concrete ``Tool`` found in ``package``.

    Args:
        package: dotted name of the package to scan.
        allowlist: when not ``None``, only tools whose ``name`` is listed load
            (an empty tuple therefore loads nothing); ``None`` loads all.

    Returns:
        A list of tool instances, de-duplicated by ``name``.
    """
    try:
        pkg = importlib.import_module(package)
    except ImportError as exc:
        logger.warning("Plugin package '%s' could not be imported: %s", package, exc)
        return []

    tools: list[Tool] = []
    seen: set[str] = set()
    for module_info in pkgutil.iter_modules(pkg.__path__, pkg.__name__ + "."):
        try:
            module = importlib.import_module(module_info.name)
        except Exception as exc:  # a broken plugin must not break discovery
            logger.warning("Skipping plugin module '%s': %s", module_info.name, exc)
            continue
        for obj in vars(module).values():
            tool = _instantiate_tool(obj)
            if tool is None or tool.name in seen:
                continue
            if allowlist is not None and tool.name not in allowlist:
                continue
            seen.add(tool.name)
            tools.append(tool)
    return tools


def _instantiate_tool(obj: object) -> Tool | None:
    """Return a Tool instance for a concrete no-arg Tool subclass, else None."""
    if not (inspect.isclass(obj) and issubclass(obj, Tool)):
        return None
    if obj is Tool or inspect.isabstract(obj):
        return None
    try:
        return obj()
    except TypeError as exc:
        logger.warning("Plugin tool '%s' needs constructor args; skipping: %s", obj.__name__, exc)
        return None

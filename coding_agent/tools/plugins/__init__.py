"""Auto-discovered tool plugins.

Every module dropped in this package that defines a concrete
:class:`~coding_agent.tools.base.Tool` subclass with a **no-argument
constructor** is instantiated and registered automatically at startup by
``coding_agent.tools.discovery.discover_tools`` (called from
``cli/main.py::build_registry``). No wiring changes are needed to add a plugin.

Loading can be restricted with the optional ``"plugins": {"enabled": [...]}``
allowlist in ``agent.config.json`` (matched against each tool's ``name``);
without that key every discovered plugin loads.

Tools needing constructor arguments are out of scope for auto-discovery — wire
those explicitly in ``build_registry`` instead.
"""

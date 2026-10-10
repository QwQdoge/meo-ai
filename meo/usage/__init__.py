"""Meo AI usage collection and synchronization.

The local collector is intentionally independent from GTK/Newelle UI state so
native and web surfaces can share the same normalized activity contract.
"""

from .collector import UsageCollector, UsageEvent

__all__ = ["UsageCollector", "UsageEvent"]

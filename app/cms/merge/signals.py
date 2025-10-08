"""Signals emitted by the merge framework."""
from __future__ import annotations

from django.dispatch import Signal

# ``error`` contains the raised exception instance. ``source``/``target`` provide
# the model instances involved in the merge attempt.
merge_failed = Signal()

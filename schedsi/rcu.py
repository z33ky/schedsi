#!/usr/bin/env python3
"""Emulate RCU storage."""

import copy
import sys
import threading


class RCU:
    """RCU storage emulation.

    Thread-safe.
    """

    def __init__(self, data):
        """Create a :class:`RCU`.

        Updates can only happen through :class:`RCUCopy` and :meth:`apply`.
        Updates are protected via an "update" id that signifies when the
        RCU data has been updated.
        """
        self._uid = 0
        self._data = data
        self._lock = threading.Lock()

    def _changed(self):
        """Update :attr:`uid:`."""
        # prevent uid getting big
        if self._uid == sys.maxsize:
            self._uid = -sys.maxsize
        else:
            self._uid += 1

    def read(self):
        """Return the contained data. \
        Do not modify.
        """
        return self.copy().data

    def copy(self):
        """Obtain an :class:`RCUCopy` of the contained data."""
        with self._lock:
            return RCUCopy(self)

    def update(self, new):
        """Update the data via an :class:`RCUCopy`.

        Returns a flag indicating success.
        On failure you typically want to obtain a fresh :class:`RCUCopy`
        and reapply your modifications to try again.
        """
        # pylint: disable=protected-access
        # see if we can fail quick
        if self._uid != new._uid:
            return False

        with self._lock:
            if self._uid != new._uid:
                return False
            self._data = new.data
            self._changed()
            new._uid = self._uid
        return True

    def apply(self, updater):
        """Apply a transformation to the contained data."""
        with self._lock:
            ret = updater(self._data)
            self._changed()
        return ret

    def look(self, looker):
        """Apply a looker to the contained data.

        Do not modify the data with the looker.
        """
        with self._lock:
            return looker(self._data)


class RCUCopy:  # pylint: disable=too-few-public-methods
    """A copy of RCU data.

    Uses :mod:`copy` to do a *shallow copy* of the data,
    so take care that you do not accidentally modify shared references.

    Contained :attr:`data` can be freely modified
    and should be written back via :meth:`RCU.update`.
    """

    def __init__(self, rcu):
        """Create a :class:`RCUCopy`."""
        # pylint: disable=protected-access
        assert rcu._lock.locked
        self._uid = rcu._uid
        self.data = copy.copy(rcu._data)

"""Hardware guard for offline validation, loaded through ``PYTHONPATH``.

Any platform or instrument connection, and any non-loopback socket connection,
raises and is appended to ``$QW5Q_GUARD_LOG``.
"""

import importlib.abc
import importlib.machinery
import ipaddress
import os
import socket
import sys

LOG = os.environ.get("QW5Q_GUARD_LOG", "qw5q_guard_violations.log")


def _violation(what):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{os.getpid()} {what}\n")
    raise RuntimeError(f"HARDWARE GUARD: {what}")


_connect = socket.socket.connect


def _guarded_connect(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6):
        host = address[0]
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = host == "localhost"
        if not loopback:
            _violation(f"socket connect to {address}")
    return _connect(self, address)


def _guarded_connect_ex(self, address):
    _guarded_connect(self, address)
    return 0


socket.socket.connect = _guarded_connect
socket.socket.connect_ex = _guarded_connect_ex

_PATCHES = {
    "qibolab._core.platform.platform": ("Platform", "Platform.connect"),
    "qibolab._core.instruments.abstract": ("Instrument", "Instrument.connect"),
    "qibolab._core.instruments.qblox.cluster": ("Cluster", "Cluster.connect"),
}


class _Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname not in _PATCHES:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.loader is None:
            return spec
        exec_module = spec.loader.exec_module
        cls, what = _PATCHES[fullname]

        def wrapped(module):
            exec_module(module)
            getattr(module, cls).connect = lambda self: _violation(what)

        spec.loader.exec_module = wrapped
        return spec


sys.meta_path.insert(0, _Finder())

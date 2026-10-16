"""Support code for the ``coherence_flux.py`` Marimo notebook.

Everything here is offline: environment checks, platform loading, preflight,
plan validation and plotting never connect to instruments.
The only exception is :meth:`HardwareSession.trigger`, which opens a Qibocal
``Executor`` (thus connecting) exclusively for a new button click on a plan that
passed all the gates.

Units follow the Qibocal protocols: frequencies in Hz, times in ns, amplitudes in
arbitrary units of the respective output.
"""

from __future__ import annotations

import copy
import datetime
import hashlib
import importlib
import json
import math
import os
import pkgutil
import platform as pyplatform
import re
import signal
import sys
import threading
import traceback
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

import numpy as np

PLATFORM = os.environ.get("QW5Q_PLATFORM", "qw5q_platinum")
"""Target platform name, overridable through ``$QW5Q_PLATFORM``."""

SUPPORTED_PYTHON = ((3, 11), (3, 14))
"""Interval ``[min, max)`` required by Qibocal and Qibolab."""

TESTED = {"qibocal": "0.2.7", "qibolab": "0.2.18"}
"""Versions the notebook was written against: older ones are flagged."""

OK, WARN, FAIL, INFO = "ok", "warn", "fail", "info"

UNSUPPORTED = (
    (
        "No registered Qibocal routine measures 1-2 (EF) coherence versus flux: "
        "`t1_flux` and `t2_flux` only address the 0-1 transition."
    ),
    (
        "No registered routine measures EF T1, T2 or Ramsey either: `t1`, `t2`, "
        "`ramsey`, `spin_echo`, `cpmg`, `zeno` and their `_signal`/`_flux` variants "
        "only address the 0-1 transition."
    ),
    (
        "Registered routines driving the 1-2 transition: `qubit_spectroscopy_ef`, "
        "`rabi_amplitude_ef` and `two_levels_crossing` (not exposed here), while "
        "`dispersive_shift_qutrit` and `qutrit_classification` prepare state 2 "
        "with RX12."
    ),
    (
        "`rabi_amplitude_ef` without a calibrated RX12 bootstraps a rectangular pulse "
        "(no DRAG) of `pulse_length`, and with `update=True` stores it as RX12."
    ),
    (
        "`dispersive_shift_qutrit` and `qutrit_classification` require a calibrated RX12, "
        "and have no update function."
    ),
    (
        "This notebook never creates or patches the drive12 channel: it must be "
        "configured in `qibolab_platforms_qrc` (`platform.py` and `parameters.json`)."
    ),
)


# ---------------------------------------------------------------------------
# environment


@dataclass(frozen=True)
class Component:
    name: str
    version: str | None = None
    location: str | None = None
    error: str | None = None
    """Blocking: the notebook cannot work."""
    warning: str | None = None

    @property
    def status(self) -> str:
        if self.error is not None:
            return FAIL
        return WARN if self.warning is not None else OK


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(m) for m in re.findall(r"\d+", text)[:3])


def platforms_dir(name: str | None = None) -> Path | None:
    """Entry of ``$QIBOLAB_PLATFORMS`` containing the platform ``name``."""
    name = PLATFORM if name is None else name
    for entry in os.environ.get("QIBOLAB_PLATFORMS", "").split(os.pathsep):
        if entry and (Path(entry) / name).is_dir():
            return Path(entry)
    return None


def check_environment(name: str | None = None) -> list[Component]:
    """Report the versions in use, and what prevents the notebook from working."""
    name = PLATFORM if name is None else name
    components = []

    python = pyplatform.python_version()
    low, high = SUPPORTED_PYTHON
    components.append(
        Component(
            "python",
            version=python,
            location=sys.executable,
            error=None
            if low <= _version(python)[:2] < high
            else f"Python >={'.'.join(map(str, low))},<{'.'.join(map(str, high))} "
            "required",
        )
    )

    for module_name in ("qibocal", "qibolab", "qibo", "marimo"):
        try:
            module = importlib.import_module(module_name)
            if getattr(module, "__file__", None) is None:
                raise ImportError(
                    "empty namespace package, e.g. an uninitialised submodule "
                    "directory on `sys.path`"
                )
        except Exception as exc:  # noqa: BLE001
            components.append(
                Component(module_name, error=f"cannot import `{module_name}` ({exc})")
            )
            continue
        version = getattr(module, "__version__", None)
        tested = TESTED.get(module_name)
        components.append(
            Component(
                module_name,
                version=version,
                location=str(Path(module.__file__).parent),
                warning=f"older than the {tested} the notebook was written against"
                if tested and version and _version(version) < _version(tested)
                else None,
            )
        )

    folder = platforms_dir(name)
    components.append(
        Component(
            "platforms",
            location=None if folder is None else str(folder / name),
            error=None
            if folder is not None
            else f"`$QIBOLAB_PLATFORMS` has no `{name}` folder",
        )
    )
    return components


def environment_ok(components: Iterable[Component]) -> bool:
    return not any(c.error for c in components)


def environment_rows(components: Iterable[Component]) -> list[dict[str, str]]:
    return [
        {
            "component": c.name,
            "status": c.status,
            "version": c.version or "",
            "detail": c.error or c.warning or c.location or "",
        }
        for c in components
    ]


@contextmanager
def _host_signal_handlers():
    """Keep the SIGINT and SIGTERM handlers of the host process.

    Qibolab platforms replace them on creation, with a handler raising
    ``RuntimeError``, which prevents interrupting or shutting down the marimo
    kernel. Disconnection on termination is restored during runs, cf.
    :func:`_disconnect_on_sigterm`.
    """
    main = threading.current_thread() is threading.main_thread()
    signals = (signal.SIGINT, signal.SIGTERM)
    saved = {s: signal.getsignal(s) for s in signals} if main else {}
    try:
        yield
    finally:
        for s, handler in saved.items():
            if handler is not None:
                signal.signal(s, handler)


@contextmanager
def _disconnect_on_sigterm(platform):
    """On SIGTERM, disconnect before delegating to the host handler."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    previous = signal.getsignal(signal.SIGTERM)
    restore = signal.SIG_DFL if previous is None else previous

    def handler(signum, frame):
        _ensure_disconnected(platform)
        signal.signal(signum, restore)
        if callable(restore):
            restore(signum, frame)
        else:
            signal.raise_signal(signum)

    signal.signal(signal.SIGTERM, handler)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, restore)


@contextmanager
def _working_directory(path: Path):
    """Run in ``path``: some Qibocal fits write relative paths (e.g. the
    ``qubit<N>/`` hyperparameters of ``single_shot_classification``)."""
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def load_platform(name: str | None = None):
    """Load the calibration platform, without connecting to instruments."""
    name = PLATFORM if name is None else name
    from qibocal.calibration import create_calibration_platform

    with _host_signal_handlers():
        platform = create_calibration_platform(name)
    if platform.is_connected:
        raise RuntimeError(f"platform {name} unexpectedly connected while loading")
    return platform


# ---------------------------------------------------------------------------
# preflight


@dataclass(frozen=True)
class Check:
    status: str
    detail: str


PREFLIGHT = {
    "drive_rx": "RX native",
    "readout_mz": "MZ native",
    "readout_discrimination": "Discrimination",
    "flux_channel": "Flux channel",
    "flux_sweetspot": "Flux offset vs sweetspot",
    "flux_coefficients": "Flux coefficients",
    "drive12_channel": "drive12 channel",
    "frequency_12": "frequency_12",
    "readout_state1": "State-1 readout frequency",
    "rx12": "RX12 native",
}
"""Preflight checks, with their labels."""


def _fmt_hz(value: float) -> str:
    return f"{value / 1e9:.6f} GHz"


AMPLITUDE_RANGE = 1.0
"""Qibolab normalises amplitudes to [-1, 1], and the Qblox driver rejects any other.

This is a representability bound, not a device safety limit.
"""


def _amplitudes(native) -> list[float]:
    """Amplitudes of the pulses in a native, including readout probes."""
    out = []
    for _, pulse in native:
        for p in (pulse, getattr(pulse, "probe", None)):
            amplitude = getattr(p, "amplitude", None)
            if amplitude is not None:
                out.append(float(amplitude))
    return out


def _native_check(native, label: str) -> Check:
    if native is None or len(native) == 0:
        return Check(FAIL, f"{label} not calibrated (null)")
    channels = ", ".join(sorted({str(ch) for ch, _ in native}))
    invalid = [a for a in _amplitudes(native) if not abs(a) <= AMPLITUDE_RANGE]
    if invalid:
        return Check(FAIL, f"{label} amplitude {invalid} outside [-1, 1] on {channels}")
    return Check(OK, f"{len(native)} pulse(s) on {channels}")


def _qubit_checks(platform, q) -> dict[str, Check]:
    qubit = platform.qubits[q]
    natives = platform.natives.single_qubit.get(q)
    configs = platform.parameters.configs
    cal = platform.calibration.single_qubits.get(q)
    checks: dict[str, Check] = {}

    checks["drive_rx"] = _native_check(natives and natives.RX, "RX")
    checks["readout_mz"] = _native_check(natives and natives.MZ, "MZ")

    acq = configs.get(qubit.acquisition) if qubit.acquisition is not None else None
    threshold = getattr(acq, "threshold", None)
    angle = getattr(acq, "iq_angle", None)
    fidelity = cal.readout.fidelity if cal is not None else None
    if threshold is None or angle is None:
        checks["readout_discrimination"] = Check(
            FAIL, "threshold/iq_angle missing: run single_shot_classification"
        )
    else:
        checks["readout_discrimination"] = Check(
            OK,
            f"threshold {threshold:.4g}, iq_angle {angle:.4g} rad, "
            f"assignment fidelity {'n/a' if fidelity is None else f'{fidelity:.3f}'}",
        )

    offset = None
    if qubit.flux is None or qubit.flux not in platform.channels:
        checks["flux_channel"] = Check(FAIL, "no flux channel")
    else:
        offset = getattr(configs.get(qubit.flux), "offset", None)
        if offset is None:
            checks["flux_channel"] = Check(FAIL, f"{qubit.flux} has no DC config")
        else:
            checks["flux_channel"] = Check(
                OK,
                f"{qubit.flux} at {platform.channels[qubit.flux].path}, "
                f"DC offset {offset:+.6g}",
            )

    sweetspot = cal.qubit.sweetspot if cal is not None else None
    if offset is None:
        checks["flux_sweetspot"] = Check(INFO, "n/a")
    elif sweetspot is None:
        checks["flux_sweetspot"] = Check(
            WARN, "no calibrated sweetspot: flux pulses act around the current offset"
        )
    elif not math.isclose(offset, sweetspot, rel_tol=0, abs_tol=1e-12):
        checks["flux_sweetspot"] = Check(
            WARN,
            f"DC offset {offset:+.6g} differs from sweetspot {sweetspot:+.6g} "
            f"(delta {offset - sweetspot:+.3g}): flux_coefficients refer to the bias "
            "at which they were measured",
        )
    else:
        checks["flux_sweetspot"] = Check(OK, f"offset = sweetspot = {sweetspot:+.6g}")

    coeffs = cal.qubit.flux_coefficients if cal is not None else None
    if coeffs is None:
        checks["flux_coefficients"] = Check(
            FAIL, "missing: run flux_amplitude_frequency with amplitude_min=0"
        )
    elif len(coeffs) == 0 or not all(math.isfinite(c) for c in coeffs):
        checks["flux_coefficients"] = Check(FAIL, f"unusable: {coeffs}")
    else:
        status, notes = OK, []
        if len(coeffs) != 3:
            status = WARN
            notes.append(f"degree {len(coeffs) - 1}, flux_amplitude_frequency fits 2")
        elif coeffs[0] >= 0:
            status = WARN
            notes.append(
                "non-negative curvature: predicted frequency rises away from zero "
                "amplitude, unexpected around a sweetspot; review or recalibrate"
            )
        detail = (
            f"[{', '.join(f'{c:.6g}' for c in coeffs)}] (GHz vs a.u.), "
            f"detuning(0) {np.polyval(coeffs, 0.0) * 1e3:+.3f} MHz"
        )
        checks["flux_coefficients"] = Check(status, "; ".join([detail, *notes]))

    ch12 = qubit.drive_extra.get((1, 2))
    freq12 = None
    if ch12 is None:
        checks["drive12_channel"] = Check(
            FAIL,
            "no drive_extra[(1, 2)] in platform.py: qutrit routines need a "
            "configured drive12 channel (not patched here)",
        )
    elif ch12 not in platform.channels:
        checks["drive12_channel"] = Check(FAIL, f"{ch12} not mapped to a port")
    else:
        freq12 = getattr(configs.get(ch12), "frequency", None)
        if freq12 is None:
            checks["drive12_channel"] = Check(
                FAIL, f"{ch12} has no IQ config with a frequency in parameters.json"
            )
        else:
            drive = (
                f", drive {qubit.drive} at {platform.channels[qubit.drive].path}"
                if qubit.drive in platform.channels
                else ""
            )
            checks["drive12_channel"] = Check(
                OK,
                f"{ch12} at {platform.channels[ch12].path}{drive}, {_fmt_hz(freq12)}",
            )

    f12 = cal.qubit.frequency_12 if cal is not None else None
    if f12 is None:
        checks["frequency_12"] = Check(
            INFO, "not calibrated: EF spectroscopy centres on the drive12 config"
        )
    elif freq12 is None:
        checks["frequency_12"] = Check(INFO, f"{_fmt_hz(f12)} (no drive12 config)")
    elif not math.isclose(f12, freq12, rel_tol=0, abs_tol=1.0):
        checks["frequency_12"] = Check(
            WARN,
            f"calibration {_fmt_hz(f12)} vs drive12 config {_fmt_hz(freq12)} "
            f"(delta {(freq12 - f12) / 1e6:+.3f} MHz)",
        )
    else:
        checks["frequency_12"] = Check(OK, _fmt_hz(f12))

    f1 = cal.readout.qudits_frequency.get(1) if cal is not None else None
    if f1 is None:
        checks["readout_state1"] = Check(
            WARN,
            "missing (written by dispersive_shift): routines fall back to the "
            "dressed resonator frequency",
        )
    else:
        checks["readout_state1"] = Check(OK, _fmt_hz(f1))

    rx12 = natives.RX12 if natives is not None else None
    if rx12 is None or len(rx12) == 0:
        checks["rx12"] = Check(FAIL, "RX12 not calibrated (null)")
    else:
        ch, pulse = rx12[0]
        amplitude = getattr(pulse, "amplitude", None)
        if not amplitude:
            checks["rx12"] = Check(FAIL, f"RX12 on {ch} has zero amplitude")
        elif not abs(amplitude) <= AMPLITUDE_RANGE:
            checks["rx12"] = Check(
                FAIL, f"RX12 amplitude {amplitude!r} on {ch} outside [-1, 1]"
            )
        elif ch12 is not None and ch != ch12:
            checks["rx12"] = Check(WARN, f"RX12 plays on {ch}, not on {ch12}")
        else:
            checks["rx12"] = Check(
                OK, f"{pulse.duration:g} ns, amplitude {amplitude:.4g} on {ch}"
            )

    return checks


def preflight(platform) -> dict[Any, dict[str, Check]]:
    """Inspect the in-memory platform, per qubit."""
    return {q: _qubit_checks(platform, q) for q in platform.qubits}


def preflight_rows(checks: Mapping[Any, Mapping[str, Check]]) -> list[dict[str, str]]:
    return [
        {
            "qubit": f"q{q}",
            "check": PREFLIGHT[name],
            "status": c.status,
            "detail": c.detail,
        }
        for q, qchecks in checks.items()
        for name, c in qchecks.items()
    ]


# ---------------------------------------------------------------------------
# routines


@dataclass(frozen=True)
class ScanField:
    name: str
    label: str
    unit: str
    kind: str
    """One of ``int``, ``float``, ``list``, ``qubit``."""
    required: bool = True
    default: str = ""
    help: str = ""


COMMON_FIELDS = (
    ScanField("nshots", "Shots", "", "int", False, help="blank: platform default"),
    ScanField(
        "relaxation_time",
        "Relaxation time",
        "ns",
        "float",
        False,
        help="blank: platform default",
    ),
)

_CLASSIFIERS = ScanField(
    "classifiers_list",
    "Classifiers",
    "",
    "list",
    False,
    help="comma separated; blank: Qibocal default (qubit_fit)",
)


def available_classifiers() -> list[str]:
    """Classifier modules shipped by the installed Qibocal."""
    try:
        import qibocal.fitting.classifier as package
    except ImportError:
        return []
    return sorted(
        m.name
        for m in pkgutil.iter_modules(package.__path__)
        if m.name.endswith("_fit")
    )


def _amplitude_fields(prefix: str, label: str, inclusive: bool) -> tuple:
    end = "included" if inclusive else "excluded"
    return (
        ScanField(f"{prefix}_min", f"{label} min", "a.u.", "float"),
        ScanField(f"{prefix}_max", f"{label} max", "a.u.", "float", help=end),
        ScanField(f"{prefix}_step", f"{label} step", "a.u.", "float"),
    )


_DELAY_FIELDS = (
    ScanField("delay_min", "Delay min", "ns", "int"),
    ScanField("delay_max", "Delay max", "ns", "int", help="excluded"),
    ScanField("delay_step", "Delay step", "ns", "int"),
)


@dataclass(frozen=True)
class Routine:
    name: str
    group: str
    title: str
    fields: tuple[ScanField, ...]
    requires: tuple[str, ...]
    single_target: bool = False
    updates: str = ""
    """What ``update=True`` changes in the in-memory platform (empty: nothing)."""
    notes: tuple[str, ...] = ()


ROUTINES = {
    r.name: r
    for r in [
        Routine(
            "single_shot_classification",
            "prerequisite",
            "Single-shot classification (0/1)",
            (_CLASSIFIERS,),
            ("drive_rx", "readout_mz"),
            updates="readout threshold, IQ angle, state centroids, fidelity, "
            "effective temperature",
        ),
        Routine(
            "flux_amplitude_frequency",
            "prerequisite",
            "Flux pulse amplitude vs frequency",
            (
                *_amplitude_fields("amplitude", "Flux amplitude", False),
                ScanField("duration", "Flux pulse duration", "ns", "float"),
                ScanField(
                    "crosstalk_qubit",
                    "Crosstalk qubit",
                    "",
                    "qubit",
                    False,
                    help="pulse this qubit's flux line instead",
                ),
                ScanField(
                    "flux_pulse_amplitude",
                    "Target flux amplitude (crosstalk only)",
                    "a.u.",
                    "float",
                    False,
                    default="0",
                ),
            ),
            ("drive_rx", "readout_mz", "readout_discrimination", "flux_channel"),
            updates="flux_coefficients (without crosstalk qubit) and one flux "
            "crosstalk matrix element",
            notes=(
                "Ramsey-like X/Y sequences around a flux pulse of fixed duration.",
                (
                    "Without existing coefficients, the protocol requires amplitude_min=0 "
                    "and no crosstalk qubit."
                ),
            ),
        ),
        Routine(
            "t1_flux",
            "coherence vs flux",
            "T1 vs flux pulse amplitude",
            (*_DELAY_FIELDS, *_amplitude_fields("amplitude", "Flux amplitude", True)),
            (
                "drive_rx",
                "readout_mz",
                "readout_discrimination",
                "flux_channel",
                "flux_sweetspot",
                "flux_coefficients",
            ),
            single_target=True,
            notes=(
                "RX, then a flux pulse lasting the whole delay, then MZ.",
                "Single-shot discrimination; no update function.",
            ),
        ),
        Routine(
            "t2_flux",
            "coherence vs flux",
            "T2 (Ramsey) vs flux pulse amplitude",
            (*_DELAY_FIELDS, *_amplitude_fields("amplitude", "Flux amplitude", True)),
            (
                "drive_rx",
                "readout_mz",
                "readout_discrimination",
                "flux_channel",
                "flux_sweetspot",
                "flux_coefficients",
            ),
            single_target=True,
            notes=(
                (
                    "RX90 - delay with flux pulse - RX90 - MZ, without software detuning: "
                    "fringes only come from the flux-induced detuning, fits close to zero "
                    "detuning may fail."
                ),
                "Single-shot discrimination; no update function.",
            ),
        ),
        Routine(
            "qubit_spectroscopy_ef",
            "qutrit",
            "EF spectroscopy (bootstrap, no RX12 needed)",
            (
                ScanField("freq_width", "Frequency width", "Hz", "int"),
                ScanField("freq_step", "Frequency step", "Hz", "int"),
                ScanField("drive_duration", "drive12 pulse duration", "ns", "int"),
                ScanField(
                    "drive_amplitude", "drive12 pulse amplitude", "a.u.", "float"
                ),
            ),
            (
                "drive_rx",
                "readout_mz",
                "drive12_channel",
                "readout_state1",
                "frequency_12",
            ),
            updates="drive12 frequency and frequency_12",
            notes=("RX, then a rectangular drive12 pulse, swept around its config.",),
        ),
        Routine(
            "rabi_amplitude_ef",
            "qutrit",
            "EF Rabi amplitude (bootstrap with pulse_length if no RX12)",
            (
                ScanField("min_amp", "Amplitude min", "a.u.", "float"),
                ScanField("max_amp", "Amplitude max", "a.u.", "float", help="excluded"),
                ScanField("step_amp", "Amplitude step", "a.u.", "float"),
                ScanField(
                    "pulse_length",
                    "RX12 duration",
                    "ns",
                    "float",
                    False,
                    help="required without calibrated RX12",
                ),
            ),
            ("drive_rx", "readout_mz", "drive12_channel", "readout_state1"),
            updates="RX12 native (rectangular pulse when bootstrapping)",
        ),
        Routine(
            "dispersive_shift_qutrit",
            "qutrit",
            "Dispersive shift for states 0/1/2",
            (
                ScanField("freq_width", "Frequency width", "Hz", "int"),
                ScanField("freq_step", "Frequency step", "Hz", "int"),
            ),
            ("drive_rx", "readout_mz", "drive12_channel", "readout_state1", "rx12"),
            notes=("Needs a calibrated RX12; no update function.",),
        ),
        Routine(
            "qutrit_classification",
            "qutrit",
            "Qutrit (0/1/2) classification",
            (),
            ("drive_rx", "readout_mz", "drive12_channel", "rx12"),
            notes=(
                "Needs a calibrated RX12; no update function.",
                "Only acquires and plots the 0/1/2 IQ clouds: no classifier is trained.",
            ),
        ),
    ]
}


def routine_status(routine: Routine, checks: Mapping[str, Check]) -> str:
    """Short readiness summary of a routine for one qubit."""
    blocked = [PREFLIGHT[n] for n in routine.requires if checks[n].status == FAIL]
    if blocked:
        return "blocked: " + ", ".join(blocked)
    review = [PREFLIGHT[n] for n in routine.requires if checks[n].status == WARN]
    notes = []
    if (
        routine.name == "flux_amplitude_frequency"
        and checks["flux_coefficients"].status == FAIL
    ):
        notes.append("amplitude_min=0 only")
    if routine.name == "rabi_amplitude_ef" and checks["rx12"].status == FAIL:
        notes.append("bootstrap: pulse_length required")
    status = "ready" + (f" ({', '.join(notes)})" if notes else "")
    return status + (f"; review: {', '.join(review)}" if review else "")


def support_rows(checks: Mapping[Any, Mapping[str, Check]]) -> list[dict[str, str]]:
    return [
        {"routine": r.name, "group": r.group}
        | {f"q{q}": routine_status(r, qchecks) for q, qchecks in checks.items()}
        for r in ROUTINES.values()
    ]


# ---------------------------------------------------------------------------
# plans


def parse_field(spec: ScanField, raw: Any) -> Any:
    """Parse a widget value; ``None`` for blank fields."""
    if spec.kind == "qubit":
        return None if raw is None or raw == "" else raw
    text = "" if raw is None else str(raw).strip()
    if not text:
        return None
    if spec.kind == "list":
        return [t.strip() for t in text.split(",") if t.strip()]
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("must be finite")
    if spec.kind == "int":
        if not value.is_integer():
            raise ValueError("must be an integer")
        return int(value)
    return value


def _freeze(value: Any) -> Any:
    """Deep, read-only copy of nested containers."""
    if isinstance(value, Mapping):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list | tuple | set | frozenset):
        return tuple(_freeze(v) for v in value)
    return copy.deepcopy(value)


def _thaw(value: Any) -> Any:
    """Mutable copy of a frozen value, with lists in place of tuples."""
    if isinstance(value, Mapping):
        return {k: _thaw(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_thaw(v) for v in value]
    return copy.deepcopy(value)


def _dump(model: Any, drop: frozenset[str] = frozenset({"id_"})) -> Any:
    """JSON view of a model, without object identifiers."""

    def strip(value):
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k not in drop}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value

    if model is None:
        return None
    if hasattr(model, "model_dump"):
        return strip(model.model_dump(mode="json"))
    return repr(model)


def execution_state(platform, qubits: Iterable) -> str:
    """Digest of the platform state determining what the qubits' routines play.

    It covers the platform settings and, for each qubit, its channels with their
    configurations (including LO, mixer and TWPA), natives and calibration.
    """
    state: dict[str, Any] = {"settings": _dump(platform.settings)}
    for q in sorted(set(qubits), key=str):
        if q not in platform.qubits:
            continue
        names = set()
        for ch in platform.qubits[q].channels:
            names.add(ch)
            channel = platform.channels.get(ch)
            for attr in ("lo", "mixer", "twpa_pump", "probe"):
                ref = getattr(channel, attr, None)
                if ref:
                    names.add(ref)
        configs = platform.parameters.configs
        state[f"q{q}"] = {
            "channels": {n: _dump(platform.channels.get(n)) for n in sorted(names)},
            "configs": {n: _dump(configs.get(n)) for n in sorted(names)},
            "natives": _dump(platform.natives.single_qubit.get(q)),
            "calibration": _dump(platform.calibration.single_qubits.get(q)),
        }
    payload = json.dumps(state, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class Plan:
    """Immutable description of one action, as previewed to the operator.

    ``parameters`` and ``raw`` are deep, read-only copies: use :meth:`kwargs` for
    a mutable copy of the parameters.
    """

    platform: str
    routine: str
    targets: tuple
    parameters: Mapping[str, Any]
    update: bool
    raw: tuple[tuple[str, Any], ...]
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    overshoot: tuple[str, ...] = ()
    """Amplitudes played beyond the declared bounds: blocking unless accepted."""
    preview: tuple[tuple[str, str], ...] = ()
    state: str = ""
    """Digest of the execution-relevant platform state, cf. :func:`execution_state`."""

    def __post_init__(self):
        object.__setattr__(self, "targets", tuple(self.targets))
        object.__setattr__(self, "parameters", _freeze(self.parameters))
        object.__setattr__(self, "raw", _freeze(self.raw))
        for name in ("errors", "warnings", "overshoot", "preview"):
            object.__setattr__(self, name, _freeze(getattr(self, name)))

    def kwargs(self) -> dict[str, Any]:
        """Fresh mutable copy of the parameters, for execution."""
        return _thaw(self.parameters)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def fingerprint(self) -> str:
        """Confirmation code, changing with any executed input or previewed value,
        and with the execution-relevant platform state."""
        payload = json.dumps(
            {
                "platform": self.platform,
                "routine": self.routine,
                "targets": list(self.targets),
                "parameters": _thaw(self.parameters),
                "update": self.update,
                "preview": _thaw(self.preview),
                "overshoot": _thaw(self.overshoot),
                "state": self.state,
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:6].upper()


def protocol_parameters(routine: str, parameters: Mapping[str, Any]):
    """Instantiate the Qibocal parameters, exactly as the executor will."""
    from qibocal.protocols import PROTOCOLS

    return PROTOCOLS[routine].parameters_type.load(dict(parameters))


def _range_errors(params, lo: str, hi: str, step: str) -> list[str]:
    if params[step] <= 0:
        return [f"{step} must be positive"]
    if params[hi] <= params[lo]:
        return [f"{hi} must exceed {lo}"]
    return []


def _describe(values, unit: str, scale: float = 1.0, digits: int = 6) -> str:
    values = np.asarray(values, dtype=float) * scale
    step = f", step {values[1] - values[0]:.{digits}g}" if values.size > 1 else ""
    return (
        f"{values.size} points, {values[0]:.{digits}g} to {values[-1]:.{digits}g} "
        f"{unit}{step}"
    ).strip()


@dataclass
class _Review:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    overshoot: list[str] = field(default_factory=list)
    preview: list[tuple[str, str]] = field(default_factory=list)
    points: int = 0
    sequences: int = 1


def _exact(values) -> str:
    values = [repr(float(v)) for v in values]
    if len(values) > 12:
        values = [*values[:5], "...", *values[-5:]]
    return "[" + ", ".join(values) + "]"


def qibocal_range(start: float, bound: float, step: float, inclusive: bool):
    """Values swept by Qibocal, for an inclusive or exclusive ``bound``."""
    return np.arange(start, bound + step if inclusive else bound, step)


def _beyond(values, bound: float, step: float, inclusive: bool):
    """Values outside the declared bound, beyond floating point noise."""
    tol = 1e-9 * step
    return values[values > bound + tol] if inclusive else values[values >= bound - tol]


def _suggest_bound(start: float, step: float, intended: float, inclusive: bool):
    """A bound making Qibocal's range end exactly at ``intended``, if any."""
    candidates = (
        [np.nextafter(intended, -np.inf), intended - 1e-10 * step]
        if inclusive
        else [intended + step / 2]
    )
    for bound in candidates:
        values = qibocal_range(start, bound, step, inclusive)
        if (
            values.size
            and math.isclose(values[-1], intended, rel_tol=0, abs_tol=1e-9 * step)
            and not _beyond(values, bound, step, inclusive).size
        ):
            return float(bound)
    return None


def _representable(review, label: str, values) -> None:
    """Amplitudes outside Qibolab's normalised range cannot be played."""
    values = np.atleast_1d(np.asarray(values, dtype=float))
    invalid = values[~(np.abs(values) <= AMPLITUDE_RANGE)]
    if invalid.size:
        review.errors.append(
            f"{label}: {_exact(invalid)} outside Qibolab's normalised amplitude range "
            "[-1, 1], rejected by the Qblox driver"
        )


def _largest(review, *values) -> None:
    played = np.concatenate([np.atleast_1d(np.asarray(v, dtype=float)) for v in values])
    review.preview.append(
        ("Largest |amplitude| played", f"{float(np.max(np.abs(played)))!r} a.u.")
    )


def _amplitude_sweep(review, label, params, keys, inclusive: bool):
    """Preview an amplitude sweep exactly, and flag points beyond its bound."""
    lo, hi, step = (params[k] for k in keys)
    values = qibocal_range(lo, hi, step, inclusive)
    end = "included" if inclusive else "excluded"
    review.preview += [
        (f"{label} ({keys[1]} {end})", _describe(values, "a.u.")),
        (f"{label}, exact values", _exact(values)),
    ]
    _representable(review, label, values)
    beyond = _beyond(values, hi, step, inclusive)
    if beyond.size:
        within = values[: values.size - beyond.size]
        hint = ""
        if within.size:
            bound = _suggest_bound(lo, step, float(within[-1]), inclusive)
            if bound is not None:
                hint = f"; {keys[1]}={bound!r} ends at {float(within[-1])!r}"
        review.overshoot.append(
            f"{label}: Qibocal plays {_exact(beyond)} beyond {keys[1]}={hi!r} "
            f"({end}), due to floating point range end points{hint}"
        )
    return values


def _review_coherence_flux(platform, params, proto, targets, checks, review):
    review.errors += _range_errors(params, "delay_min", "delay_max", "delay_step")
    review.errors += _range_errors(
        params, "amplitude_min", "amplitude_max", "amplitude_step"
    )
    if params["delay_min"] < 0:
        review.errors.append("delay_min must be non-negative")
    if review.errors:
        return
    delays, amps = proto.delay_range, proto.flux_range
    review.preview.append(("Delays (end excluded)", _describe(delays, "ns")))
    keys = ("amplitude_min", "amplitude_max", "amplitude_step")
    swept = _amplitude_sweep(review, "Flux amplitudes", params, keys, inclusive=True)
    if not np.array_equal(swept, amps):
        review.errors.append("previewed amplitudes differ from Qibocal's flux_range")
        return
    _largest(review, amps)
    for q in targets:
        coeffs = platform.calibration.single_qubits[q].qubit.flux_coefficients
        if coeffs is None or checks[q]["flux_coefficients"].status == FAIL:
            continue
        detuning = np.polyval(coeffs, amps)
        drive = platform.config(platform.qubits[q].drive).frequency
        review.preview.append(
            (
                f"q{q} predicted detuning",
                (
                    f"{detuning.min() * 1e3:+.3f} to {detuning.max() * 1e3:+.3f} MHz, "
                    f"i.e. {_fmt_hz(drive + detuning.min() * 1e9)} to "
                    f"{_fmt_hz(drive + detuning.max() * 1e9)} (from flux_coefficients)"
                ),
            )
        )
    review.points = delays.size * amps.size
    review.preview.append(
        ("Single-shot values per qubit", f"{params['nshots'] * review.points:,}")
    )


def _review_flux_amplitude(platform, params, proto, targets, checks, review):
    review.errors += _range_errors(
        params, "amplitude_min", "amplitude_max", "amplitude_step"
    )
    if params["duration"] <= 0:
        review.errors.append("duration must be positive")
    crosstalk = params.get("crosstalk_qubit")
    if crosstalk is not None:
        if crosstalk not in platform.qubits:
            review.errors.append(f"unknown crosstalk qubit {crosstalk}")
        elif crosstalk in targets:
            review.errors.append("crosstalk qubit must differ from the targets")
        elif checks[crosstalk]["flux_channel"].status == FAIL:
            review.errors.append(
                f"crosstalk qubit q{crosstalk}: {checks[crosstalk]['flux_channel'].detail}"
            )
    elif params.get("flux_pulse_amplitude", 0) != 0:
        review.warnings.append(
            "flux_pulse_amplitude is ignored without crosstalk qubit"
        )
    if crosstalk is not None or not math.isclose(params["amplitude_min"], 0):
        for q in targets:
            if checks[q]["flux_coefficients"].status == FAIL:
                review.errors.append(
                    f"q{q}: existing flux_coefficients required unless amplitude_min=0 "
                    "and no crosstalk qubit"
                )
            elif checks[q]["flux_coefficients"].status == WARN:
                review.warnings.append(
                    f"q{q} flux_coefficients: {checks[q]['flux_coefficients'].detail}"
                )
    if review.errors:
        return
    line = f"crosstalk qubit q{crosstalk}" if crosstalk is not None else "target qubits"
    keys = ("amplitude_min", "amplitude_max", "amplitude_step")
    amps = _amplitude_sweep(
        review, f"Flux amplitudes on {line}", params, keys, inclusive=False
    )
    played = [amps]
    if crosstalk is not None:
        fixed = float(params.get("flux_pulse_amplitude", 0))
        label = (
            "Fixed flux amplitude on "
            + ", ".join(f"q{q}" for q in targets)
            + " (crosstalk mode)"
        )
        review.preview.append((label, f"{fixed!r} a.u."))
        _representable(review, label, fixed)
        played.append(fixed)
    _largest(review, *played)
    review.preview.append(("Flux pulse duration", f"{params['duration']:g} ns"))
    review.points, review.sequences = amps.size, 2


def _review_spectroscopy_ef(platform, params, proto, targets, checks, review):
    for name in ("freq_width", "freq_step", "drive_duration"):
        if params[name] <= 0:
            review.errors.append(f"{name} must be positive")
    if review.errors:
        return
    for q in targets:
        ch12 = platform.qubits[q].drive_extra.get((1, 2))
        if checks[q]["drive12_channel"].status == FAIL or ch12 is None:
            continue
        center = platform.config(ch12).frequency
        freqs = np.arange(*proto.frequency_range(center))
        review.preview += [
            (f"q{q} drive12 frequencies", _describe(freqs, "GHz", 1e-9, 9)),
            (f"q{q} drive12 centre", f"{center!r} Hz"),
        ]
        review.points = max(review.points, freqs.size)
    amplitude = float(params["drive_amplitude"])
    review.preview.append(
        (
            "drive12 pulse",
            f"rectangular, {params['drive_duration']} ns, amplitude {amplitude!r} a.u.",
        )
    )
    _representable(review, "drive12 pulse amplitude", amplitude)
    _largest(review, amplitude)


def _review_rabi_ef(platform, params, proto, targets, checks, review):
    review.errors += _range_errors(params, "min_amp", "max_amp", "step_amp")
    length = params.get("pulse_length")
    if length is not None and length <= 0:
        review.errors.append("pulse_length must be positive")
    for q in targets:
        if checks[q]["rx12"].status == FAIL:
            if length is None:
                review.errors.append(
                    f"q{q}: pulse_length required to bootstrap without calibrated RX12"
                )
            else:
                review.preview.append(
                    (f"q{q} pulse", f"bootstrap: rectangular, {length:g} ns")
                )
        else:
            duration = (
                "calibrated" if length is None else f"overridden to {length:g} ns"
            )
            review.preview.append((f"q{q} pulse", f"RX12 shape, duration {duration}"))
    if review.errors:
        return
    keys = ("min_amp", "max_amp", "step_amp")
    amps = _amplitude_sweep(review, "RX12 amplitudes", params, keys, inclusive=False)
    _largest(review, amps)
    review.points = amps.size


def _review_dispersive_qutrit(platform, params, proto, targets, checks, review):
    for name in ("freq_width", "freq_step"):
        if params[name] <= 0:
            review.errors.append(f"{name} must be positive")
    if review.errors:
        return
    from qibocal.protocols.utils import readout_frequency

    for q in targets:
        center = readout_frequency(q, platform, state=1)
        freqs = np.arange(*proto.frequency_range(center))
        review.preview += [
            (f"q{q} probe frequencies", _describe(freqs, "GHz", 1e-9, 9)),
            (f"q{q} probe centre (state 1)", f"{center!r} Hz"),
        ]
        review.points = max(review.points, freqs.size)
    review.sequences = 3


def _review_classification(states: int):
    def review_(platform, params, proto, targets, checks, review):
        review.preview.append(("Prepared states", ", ".join(map(str, range(states)))))
        review.points, review.sequences = 1, states

    return review_


_REVIEWS = {
    "single_shot_classification": _review_classification(2),
    "flux_amplitude_frequency": _review_flux_amplitude,
    "t1_flux": _review_coherence_flux,
    "t2_flux": _review_coherence_flux,
    "qubit_spectroscopy_ef": _review_spectroscopy_ef,
    "rabi_amplitude_ef": _review_rabi_ef,
    "dispersive_shift_qutrit": _review_dispersive_qutrit,
    "qutrit_classification": _review_classification(3),
}


def build_plan(
    platform,
    routine: str,
    raw: Mapping[str, Any],
    targets: Iterable,
    update: bool = False,
    checks: Mapping[Any, Mapping[str, Check]] | None = None,
) -> Plan:
    """Validate inputs and describe exactly what would be executed."""
    spec = ROUTINES[routine]
    checks = preflight(platform) if checks is None else checks
    targets = tuple(targets)
    errors: list[str] = []
    warnings: list[str] = []

    if not targets:
        errors.append("select at least one target qubit")
    unknown = [q for q in targets if q not in platform.qubits]
    if unknown:
        errors.append(f"unknown qubits: {unknown}")
    if spec.single_target and len(targets) > 1:
        errors.append(f"{routine} runs one qubit at a time")
    known = [q for q in targets if q in platform.qubits]

    params: dict[str, Any] = {}
    for f in (*spec.fields, *COMMON_FIELDS):
        try:
            value = parse_field(f, raw.get(f.name, f.default))
        except ValueError as exc:
            errors.append(f"{f.label}: {exc}")
            continue
        if value is None:
            if f.required:
                errors.append(f"{f.label} is required")
            continue
        params[f.name] = value
    params.setdefault("nshots", platform.settings.nshots)
    params.setdefault("relaxation_time", platform.settings.relaxation_time)
    if params["nshots"] is None or params["nshots"] <= 0:
        errors.append("nshots must be positive")
    if params["relaxation_time"] is None or params["relaxation_time"] < 0:
        errors.append("relaxation_time must be non-negative")

    for q in known:
        for name in spec.requires:
            check = checks[q][name]
            if check.status == FAIL:
                errors.append(f"q{q} {PREFLIGHT[name]}: {check.detail}")
            elif check.status == WARN:
                warnings.append(f"q{q} {PREFLIGHT[name]}: {check.detail}")

    if "classifiers_list" in params:
        available = available_classifiers()
        unknown = sorted(set(params["classifiers_list"]) - set(available))
        if unknown:
            errors.append(f"unknown classifiers {unknown}, available: {available}")
    review = _Review()
    overshoot: list[str] = []
    crosstalk = params.get("crosstalk_qubit")
    preview: list[tuple[str, str]] = [
        ("Platform", platform.name),
        ("Routine", f"{routine} ({spec.title})"),
        ("Targets", ", ".join(f"q{q}" for q in targets)),
    ]
    if not errors:
        try:
            proto = protocol_parameters(routine, params)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Qibocal rejected the parameters: {exc}")
        else:
            _REVIEWS[routine](platform, params, proto, known, checks, review)
            errors += review.errors
            warnings += review.warnings
            overshoot = review.overshoot
            preview += review.preview

    preview += [
        ("Shots", f"{params.get('nshots')}"),
        ("Relaxation time", f"{params.get('relaxation_time')} ns"),
    ]
    if review.points and params.get("nshots") and params.get("relaxation_time"):
        seconds = (
            review.points
            * review.sequences
            * params["nshots"]
            * params["relaxation_time"]
            * 1e-9
        )
        preview.append(
            (
                "Duration lower bound",
                (
                    f"{seconds:.1f} s (points x sequences x shots x relaxation, "
                    "excluding pulses and overheads)"
                ),
            )
        )
    if spec.updates:
        preview.append(
            (
                "Update",
                f"update=True: {spec.updates}, in memory only"
                if update
                else "update=False: platform left unchanged",
            )
        )
    else:
        preview.append(("Update", "no update function: platform left unchanged"))
    preview += [("Note", n) for n in spec.notes]

    return Plan(
        platform=platform.name,
        routine=routine,
        targets=targets,
        parameters=params,
        update=bool(update),
        raw=tuple(sorted((k, v) for k, v in raw.items())),
        errors=tuple(errors),
        warnings=tuple(warnings),
        overshoot=tuple(overshoot),
        preview=tuple(preview),
        state=execution_state(
            platform, [*known, *([crosstalk] if crosstalk is not None else [])]
        ),
    )


# ---------------------------------------------------------------------------
# execution


@dataclass(frozen=True)
class Gate:
    """Operator consent, collected outside of the plan."""

    hardware_consent: bool = False
    ranges_confirmed: bool = False
    overshoot_accepted: bool = False
    confirmation: str = ""
    warnings_reviewed: bool = False


def blocking_reasons(plan: Plan | None, gate: Gate, environment_ok: bool) -> list[str]:
    if plan is None:
        return ["no submitted plan"]
    reasons = []
    if not plan.ok:
        reasons.append("the plan has errors")
    if not gate.hardware_consent:
        reasons.append("hardware access is not enabled")
    if not gate.ranges_confirmed:
        reasons.append("the operator did not confirm the scan ranges")
    if gate.confirmation.strip().upper() != plan.fingerprint:
        reasons.append("the confirmation code does not match the current plan")
    if plan.warnings and not gate.warnings_reviewed:
        reasons.append("the plan warnings are not acknowledged")
    if plan.overshoot and not gate.overshoot_accepted:
        reasons.append("amplitudes beyond the declared bounds are not accepted")
    if not environment_ok:
        reasons.append("the environment has errors (see the environment table)")
    return reasons


@dataclass
class RunRecord:
    plan: Plan
    nonce: int
    status: str
    """One of ``blocked``, ``completed``, ``failed``, ``interrupted``."""
    reasons: list[str] = field(default_factory=list)
    path: Path | None = None
    data: Any = None
    results: Any = None
    error: str | None = None
    traceback: str | None = None
    changes: list[str] = field(default_factory=list)
    disconnected: bool | None = None
    started: datetime.datetime | None = None
    finished: datetime.datetime | None = None
    report: Path | None = None
    report_error: str | None = None
    environment: list[dict[str, str]] = field(default_factory=list)


def unique_output_path(
    root: Path, plan: Plan, now: datetime.datetime | None = None
) -> Path:
    """Fresh output folder: existing folders are never reused or deleted."""
    now = datetime.datetime.now() if now is None else now
    targets = "-".join(f"q{q}" for q in plan.targets)
    stem = f"{now:%H%M%S}_{plan.routine}_{targets}_{plan.fingerprint}"
    folder = Path(root) / f"{now:%Y-%m-%d}"
    path, n = folder / stem, 1
    while path.exists():
        path, n = folder / f"{stem}_{n}", n + 1
    return path


def _flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(obj, Mapping):
        out = {}
        for k, v in obj.items():
            out |= _flatten(v, f"{prefix}{k}.")
        return out
    if isinstance(obj, list | tuple):
        out = {}
        for i, v in enumerate(obj):
            out |= _flatten(v, f"{prefix}{i}.")
        return out or {prefix.rstrip("."): obj}
    return {prefix.rstrip("."): obj}


def snapshot(platform) -> dict[str, Any]:
    """Flat view of parameters and calibration, to report in-memory changes."""
    out = {}
    for name, model in (
        ("parameters", platform.parameters),
        ("calibration", platform.calibration),
    ):
        try:
            out |= _flatten(model.model_dump(mode="json"), f"{name}.")
        except Exception as exc:  # noqa: BLE001
            out[name] = f"<not serializable: {exc}>"
    return out


def diff(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    def short(v):
        s = repr(v)
        return s if len(s) < 80 else s[:77] + "..."

    keys = sorted(set(before) | set(after))
    return [
        f"{k}: {short(before.get(k))} -> {short(after.get(k))}"
        for k in keys
        if before.get(k) != after.get(k)
    ]


def _ensure_disconnected(platform) -> bool:
    """Disconnect, including instruments left connected by a failed connection."""
    try:
        platform.disconnect()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    for instrument in platform.instruments.values():
        try:
            if getattr(instrument, "is_connected", False):
                instrument.disconnect()
        except Exception:  # noqa: BLE001
            traceback.print_exc()
    return not platform.is_connected and not any(
        getattr(i, "is_connected", False) for i in platform.instruments.values()
    )


def _load_task_data(path: Path, routine: str):
    """Best-effort reload of acquired data, e.g. when fitting failed."""
    from qibocal.protocols import PROTOCOLS

    folder = path / "data" / f"{routine}-0"
    if not folder.is_dir():
        return None
    try:
        return PROTOCOLS[routine].data_type.load(folder)
    except Exception:  # noqa: BLE001
        return None


RUN_METADATA = "qw5q_run.json"
"""Notebook record written in each run folder, next to Qibocal's outputs."""


def write_run_metadata(record: RunRecord) -> None:
    """Record plan, outcome and environment, also for failed runs."""
    if record.path is None or not record.path.is_dir():
        return
    plan = record.plan
    data = {
        "platform": plan.platform,
        "routine": plan.routine,
        "targets": list(plan.targets),
        "parameters": plan.kwargs(),
        "update": plan.update,
        "fingerprint": plan.fingerprint,
        "state": plan.state,
        "preview": _thaw(plan.preview),
        "warnings": _thaw(plan.warnings),
        "overshoot": _thaw(plan.overshoot),
        "nonce": record.nonce,
        "status": record.status,
        "error": record.error,
        "disconnected": record.disconnected,
        "changes": record.changes,
        "started": record.started,
        "finished": record.finished,
        "report": record.report,
        "report_error": record.report_error,
        "python": sys.executable,
        "environment": record.environment,
    }
    try:
        (record.path / RUN_METADATA).write_text(
            json.dumps(data, indent=2, default=str), encoding="utf-8"
        )
    except OSError:
        traceback.print_exc()


class HardwareSession:
    """Owns the in-memory platform and the executed actions.

    A run requires a *new* click: the first observed button value only sets the
    baseline, and each value is consumed once, so that reactive re-execution of
    notebook cells (e.g. after editing widgets) never re-triggers acquisition.
    """

    def __init__(self, platform, output_root: Path):
        self.platform = platform
        self.output_root = Path(output_root)
        self.records: list[RunRecord] = []
        self._last_nonce: int | None = None

    def claim(self, nonce: Any) -> bool:
        nonce = int(nonce or 0)
        # first observation, or a recreated button: only (re)set the baseline
        if self._last_nonce is None or nonce < self._last_nonce:
            self._last_nonce = nonce
            return False
        if nonce == self._last_nonce:
            return False
        self._last_nonce = nonce
        return True

    def trigger(
        self,
        nonce: Any,
        plan: Plan | None,
        gate: Gate,
        environment_ok: bool,
        report: bool = False,
        environment: Iterable[Component] | None = None,
    ) -> RunRecord | None:
        """Run ``plan`` if ``nonce`` is a new click and all gates pass.

        ``environment`` is recorded in the run folder, if given.
        """
        if not self.claim(nonce):
            return None
        if plan is None:
            return None

        reasons = blocking_reasons(plan, gate, environment_ok)
        if not reasons:
            # the in-memory platform may have changed since the preview
            current = build_plan(
                self.platform, plan.routine, dict(plan.raw), plan.targets, plan.update
            )
            changed = [
                name
                for name in (
                    "parameters",
                    "preview",
                    "state",
                    "errors",
                    "warnings",
                    "overshoot",
                )
                if getattr(current, name) != getattr(plan, name)
            ]
            if changed or current.fingerprint != plan.fingerprint:
                reasons.append(
                    "the plan no longer matches the in-memory platform "
                    f"({', '.join(changed) or 'fingerprint'} changed): rebuild and "
                    "review"
                )
        record = RunRecord(plan, int(nonce), "blocked", reasons=reasons)
        if environment is not None:
            record.environment = environment_rows(environment)
        # recorded before executing, to survive interruptions
        self.records.append(record)
        if not reasons:
            record.status = "failed"
            self._execute(record, report)
        return record

    def _execute(self, record: RunRecord, report: bool):
        from qibocal.auto.execute import Executor

        plan = record.plan
        record.path = unique_output_path(self.output_root, plan)
        before = snapshot(self.platform)
        record.started = datetime.datetime.now()
        executor = None
        try:
            with (
                _disconnect_on_sigterm(self.platform),
                Executor.open(
                    path=record.path,
                    targets=list(plan.targets),
                    platform=self.platform,
                    force=False,
                    update=plan.update,
                ) as executor,
                _working_directory(record.path),
            ):
                completed = getattr(executor, plan.routine)(
                    targets=list(plan.targets),
                    update=plan.update,
                    **plan.kwargs(),
                )
            record.data = completed.data
            record.results = completed.results
            record.status = "completed"
        except KeyboardInterrupt:
            record.status = "interrupted"
            record.error = "interrupted by the operator"
            raise
        except Exception as exc:  # noqa: BLE001
            record.error = "".join(traceback.format_exception_only(exc)).strip()
            record.traceback = traceback.format_exc()
            record.data = _load_task_data(record.path, plan.routine)
        finally:
            record.disconnected = _ensure_disconnected(self.platform)
            record.finished = datetime.datetime.now()
            record.changes = diff(before, snapshot(self.platform))
            write_run_metadata(record)

        if report and executor is not None and record.status == "completed":
            try:
                from qibocal.cli.report import report as qibocal_report

                qibocal_report(record.path, executor.history)
                record.report = record.path / "index.html"
            except Exception as exc:  # noqa: BLE001
                record.report_error = f"{type(exc).__name__}: {exc}"
            write_run_metadata(record)


# ---------------------------------------------------------------------------
# plots


def _value_error(item) -> tuple[float, float]:
    try:
        arr = np.asarray(item, dtype=float).ravel()
    except (TypeError, ValueError):
        return math.nan, math.nan
    if arr.size >= 2:
        return float(arr[0]), float(arr[1])
    if arr.size == 1:
        return float(arr[0]), math.nan
    return math.nan, math.nan


def coherence_flux_figures(data, results, kind: str) -> tuple[list, list[str]]:
    """Raw P(1) maps and fitted times, robust to failed fits."""
    import plotly.graph_objects as go

    figures, notes = [], []
    attr = "t1" if kind == "T1" else "t2"
    amps = np.asarray(data.flux_range, dtype=float)
    delays = np.asarray(data.wait_range, dtype=float)
    for q in data.data:
        prob = np.asarray(data.probability(q), dtype=float)
        if prob.ndim == 2:
            heat = go.Figure(
                go.Heatmap(x=delays, y=amps, z=prob, colorbar={"title": "P(1)"})
            )
            heat.update_layout(
                title=f"q{q}: {kind} vs flux, measured P(1)",
                xaxis_title="Delay [ns]",
                yaxis_title="Flux pulse amplitude [a.u.]",
            )
            figures.append(heat)
        else:
            notes.append(f"q{q}: unexpected data shape {prob.shape}")

        fitted = []
        if results is not None:
            fitted = list(getattr(results, attr, {}).get(q, []))
        fitted = (fitted + [math.nan] * len(amps))[: len(amps)]
        values, errors = np.array([_value_error(f) for f in fitted]).reshape(-1, 2).T
        good = np.isfinite(values) & (values > 0)
        bars = np.where(np.isfinite(errors), errors, 0.0)
        detuning = np.asarray(data.detuning.get(q, [math.nan] * len(amps)), float)
        fig = go.Figure(
            go.Scatter(
                x=amps[good],
                y=values[good],
                error_y={"type": "data", "array": bars[good]},
                customdata=detuning[good],
                hovertemplate="amplitude %{x:.4g}<br>"
                + kind
                + " %{y:.4g} ns<br>predicted frequency %{customdata:.6f} GHz",
                mode="markers",
                name=kind,
            )
        )
        fig.update_layout(
            title=f"q{q}: fitted {kind} ({int(good.sum())}/{len(amps)} fits succeeded)",
            xaxis_title="Flux pulse amplitude [a.u.]",
            yaxis_title=f"{kind} [ns]",
        )
        figures.append(fig)
        if not good.all():
            notes.append(f"q{q}: fit failed at amplitudes {amps[~good].tolist()}")
    return figures, notes


def flux_amplitude_figures(data, results) -> tuple[list, list[str]]:
    import plotly.graph_objects as go

    figures, notes = [], []
    qubits = sorted({k[0] for k in data.data}, key=str)
    for q in qubits:
        fig = go.Figure()
        for measure in ("X", "Y"):
            arr = data.data.get((q, measure))
            if arr is not None:
                fig.add_scatter(
                    x=arr["amplitude"], y=arr["prob_1"], name=f"<{measure}>"
                )
        fig.update_layout(
            title=f"q{q}: flux amplitude vs frequency, raw P(1)",
            xaxis_title="Flux pulse amplitude [a.u.]",
            yaxis_title="P(1)",
        )
        figures.append(fig)
        if results is None or q not in getattr(results, "detuning", {}):
            notes.append(f"q{q}: no fitted detuning")
            continue
        amps = np.asarray(data.data[(q, "X")]["amplitude"], dtype=float)
        detuning = np.asarray(results.detuning[q], dtype=float)
        fig = go.Figure(
            go.Scatter(x=amps, y=detuning * 1e3, mode="markers", name="measured")
        )
        coeffs = results.fitted_parameters_detuning.get(q)
        if coeffs:
            fine = np.linspace(amps.min(), amps.max(), 200)
            fig.add_scatter(x=fine, y=np.polyval(coeffs, fine) * 1e3, name="fit")
        fig.update_layout(
            title=f"q{q}: detuning, fit {coeffs}",
            xaxis_title="Flux pulse amplitude [a.u.]",
            yaxis_title="Detuning [MHz]",
        )
        figures.append(fig)
    return figures, notes


def protocol_figures(routine: str, data, results, targets) -> tuple[list, list[str]]:
    """Qibocal's own report figures, when they can be produced."""
    from qibocal.protocols import PROTOCOLS

    figures, notes = [], []
    for q in targets:
        try:
            figs, _ = PROTOCOLS[routine].report(data, q, results)
            figures += list(figs)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"q{q}: Qibocal plot failed ({type(exc).__name__}: {exc})")
    return figures, notes


def record_figures(record: RunRecord) -> tuple[list, list[str]]:
    if record.data is None:
        return [], ["no data acquired"]
    routine = record.plan.routine
    try:
        if routine in ("t1_flux", "t2_flux"):
            kind = "T1" if routine == "t1_flux" else "T2"
            return coherence_flux_figures(record.data, record.results, kind)
        if routine == "flux_amplitude_frequency":
            return flux_amplitude_figures(record.data, record.results)
        return protocol_figures(
            routine, record.data, record.results, record.plan.targets
        )
    except Exception as exc:  # noqa: BLE001
        return [], [f"plotting failed ({type(exc).__name__}: {exc})"]

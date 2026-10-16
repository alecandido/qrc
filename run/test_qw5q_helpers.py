"""Mandatory offline safety tests for the ``qw5q_coherence_flux.py`` notebook.

They exercise the real execution helper (Qibocal ``Executor`` included) on the
``mock`` platform shipped with Qibocal's tests, driven by Qibolab's dummy
instrument, and load the stock ``qw5q_platinum`` offline: no hardware is involved.
Missing requirements fail, instead of skipping. Run them through the validation
entry point, in the environment created with ``run/qw5q_env.bash``::

    run/qw5q_validate.bash
"""

import dataclasses
import hashlib
import importlib.util
import math
import os
import signal
import subprocess
from pathlib import Path

import pytest

SETUP = "create and source the environment of run/qw5q_env.bash"

try:
    import qibocal

    if getattr(qibocal, "__file__", None) is None:
        raise ImportError(
            "only an empty namespace package found, e.g. the uninitialised qibocal "
            "submodule directory"
        )
except ImportError as exc:
    pytest.fail(f"qibocal is required by these tests ({exc}): {SETUP}", pytrace=False)

import qw5q_helpers as h

MOCK_PLATFORMS = Path(qibocal.__file__).resolve().parents[2] / "tests" / "platforms"
NOTEBOOK = Path(__file__).parent / "qw5q_coherence_flux.py"
VERIFIED_PLATFORMS = os.environ.get("QIBOLAB_PLATFORMS", "")
"""Platforms checkout configured by the environment, before tests switch to mock."""

FLUX = {
    "amplitude_min": "0",
    "amplitude_max": "0.2",
    "amplitude_step": "0.05",
    "duration": "60",
    "nshots": "50",
    "relaxation_time": "1000",
}
T1 = {
    "delay_min": "20",
    "delay_max": "2000",
    "delay_step": "500",
    "amplitude_min": "0",
    "amplitude_max": "0.08",
    "amplitude_step": "0.04",
    "nshots": "50",
    "relaxation_time": "1000",
}
ALLOW = h.Gate(hardware_consent=True, ranges_confirmed=True, warnings_reviewed=True)


@pytest.fixture(autouse=True)
def mock_environment(monkeypatch):
    if not (MOCK_PLATFORMS / "mock").is_dir():
        pytest.fail(
            f"Qibocal mock platform not found in {MOCK_PLATFORMS}: {SETUP}",
            pytrace=False,
        )
    monkeypatch.setenv("QIBOLAB_PLATFORMS", str(MOCK_PLATFORMS))
    monkeypatch.setattr(h, "PLATFORM", "mock")


@pytest.fixture
def platform():
    return h.load_platform()


def approve(plan: h.Plan) -> h.Gate:
    return dataclasses.replace(ALLOW, confirmation=plan.fingerprint)


def run(session: h.HardwareSession, plan: h.Plan) -> h.RunRecord:
    """Observe the button, then click it once."""
    nonce = session._last_nonce or 0
    session.claim(nonce)
    record = session.trigger(nonce + 1, plan, approve(plan), environment_ok=True)
    assert record is not None
    return record


def digest(folder: Path) -> dict[str, str]:
    return {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def test_environment_components():
    names = {c.name: c for c in h.check_environment()}
    expected = {"python", "qibocal", "qibolab", "qibo", "packages"}
    assert expected | {"qibolab_platforms_qrc"} <= set(names)
    assert names["qibolab_platforms_qrc"].error is None


def test_preflight_mock(platform):
    checks = h.preflight(platform)
    q0 = checks[0]
    assert q0["drive12_channel"].status == h.OK
    assert q0["rx12"].status == h.OK
    assert q0["flux_coefficients"].status == h.OK
    assert set(q0) == set(h.PREFLIGHT)
    assert all(r["q0"].startswith("ready") for r in h.support_rows(checks))
    assert not platform.is_connected


def test_plan_validation(platform):
    missing = h.build_plan(platform, "t1_flux", {}, [0])
    assert any("is required" in e for e in missing.errors)

    two = h.build_plan(platform, "t1_flux", T1, [0, 1])
    assert any("one qubit at a time" in e for e in two.errors)

    negative = h.build_plan(platform, "t1_flux", T1 | {"amplitude_step": "-0.05"}, [0])
    assert any("must be positive" in e for e in negative.errors)

    plan = h.build_plan(platform, "t1_flux", T1, [0])
    assert plan.ok, plan.errors
    assert plan.parameters["nshots"] == 50
    preview = dict(plan.preview)
    assert preview["Flux amplitudes, exact values"] == "[0.0, 0.04, 0.08]"
    assert "q0 predicted detuning" in preview
    assert plan.overshoot == ()

    same = h.build_plan(platform, "t1_flux", T1, [0])
    other = h.build_plan(platform, "t1_flux", T1 | {"delay_step": "400"}, [0])
    assert same.fingerprint == plan.fingerprint != other.fingerprint

    defaults = h.build_plan(platform, "t1_flux", T1 | {"nshots": ""}, [0])
    assert defaults.parameters["nshots"] == platform.settings.nshots


def test_flux_coefficients_prerequisites(platform):
    platform.calibration.single_qubits[0].qubit.flux_coefficients = None
    checks = h.preflight(platform)
    assert checks[0]["flux_coefficients"].status == h.FAIL

    assert not h.build_plan(platform, "t1_flux", T1, [0], checks=checks).ok
    assert not h.build_plan(platform, "t2_flux", T1, [0], checks=checks).ok
    shifted = FLUX | {"amplitude_min": "0.05"}
    assert not h.build_plan(
        platform, "flux_amplitude_frequency", shifted, [0], checks=checks
    ).ok
    assert h.build_plan(
        platform, "flux_amplitude_frequency", FLUX, [0], checks=checks
    ).ok

    platform.calibration.single_qubits[0].qubit.flux_coefficients = [1.0, 0.0, 0.0]
    checks = h.preflight(platform)
    assert checks[0]["flux_coefficients"].status == h.WARN
    assert h.build_plan(platform, "t1_flux", T1, [0], checks=checks).warnings


def test_qutrit_requires_configured_drive12(platform):
    del platform.qubits[0].drive_extra[(1, 2)]
    checks = h.preflight(platform)
    assert checks[0]["drive12_channel"].status == h.FAIL
    raw = {
        "qubit_spectroscopy_ef": {
            "freq_width": "2e7",
            "freq_step": "5e6",
            "drive_duration": "1000",
            "drive_amplitude": "0.1",
        },
        "rabi_amplitude_ef": {
            "min_amp": "0",
            "max_amp": "0.5",
            "step_amp": "0.1",
            "pulse_length": "40",
        },
        "dispersive_shift_qutrit": {"freq_width": "4e6", "freq_step": "1e6"},
        "qutrit_classification": {},
    }
    for routine, values in raw.items():
        plan = h.build_plan(platform, routine, values, [0], checks=checks)
        assert any("drive12" in e for e in plan.errors), routine
        status = h.routine_status(h.ROUTINES[routine], checks[0])
        assert status.startswith("blocked"), routine


def test_rx12_bootstrap_distinction(platform):
    checks = h.preflight(platform)
    checks[0] = dict(checks[0]) | {"rx12": h.Check(h.FAIL, "RX12 not calibrated")}
    rabi = {"min_amp": "0", "max_amp": "0.5", "step_amp": "0.1"}

    plan = h.build_plan(platform, "rabi_amplitude_ef", rabi, [0], checks=checks)
    assert any("pulse_length required" in e for e in plan.errors)
    plan = h.build_plan(
        platform, "rabi_amplitude_ef", rabi | {"pulse_length": "40"}, [0], checks=checks
    )
    assert plan.ok, plan.errors
    spectroscopy = {
        "freq_width": "2e7",
        "freq_step": "5e6",
        "drive_duration": "1000",
        "drive_amplitude": "0.1",
    }
    plan = h.build_plan(
        platform, "qubit_spectroscopy_ef", spectroscopy, [0], checks=checks
    )
    assert plan.ok, plan.errors
    for routine, values in [
        ("dispersive_shift_qutrit", {"freq_width": "4e6", "freq_step": "1e6"}),
        ("qutrit_classification", {}),
    ]:
        plan = h.build_plan(platform, routine, values, [0], checks=checks)
        assert any("RX12" in e for e in plan.errors), routine


def test_trigger_gates_and_nonce(platform, tmp_path):
    session = h.HardwareSession(platform, tmp_path)
    plan = h.build_plan(platform, "flux_amplitude_frequency", FLUX, [0])
    assert plan.ok, plan.errors

    # first observation only sets the baseline, even with a stale counter
    assert session.trigger(3, plan, approve(plan), True) is None
    assert session.trigger(3, plan, approve(plan), True) is None

    blocked = session.trigger(4, plan, ALLOW, True)
    assert blocked.status == "blocked"
    assert any("confirmation code" in r for r in blocked.reasons)
    unverified = session.trigger(5, plan, approve(plan), False)
    assert unverified.status == "blocked"
    no_consent = dataclasses.replace(approve(plan), hardware_consent=False)
    assert session.trigger(6, plan, no_consent, True).status == "blocked"
    no_ranges = dataclasses.replace(approve(plan), ranges_confirmed=False)
    assert session.trigger(7, plan, no_ranges, True).status == "blocked"
    assert not tmp_path.exists() or not any(tmp_path.iterdir())

    # a consumed click never runs again, e.g. on reactive re-execution
    assert session.trigger(7, plan, approve(plan), True) is None
    record = session.trigger(8, plan, approve(plan), True)
    assert record.status == "completed", record.traceback
    assert record.path.is_dir() and record.path.is_relative_to(tmp_path)
    assert record.disconnected and not platform.is_connected
    assert session.trigger(8, plan, approve(plan), True) is None

    # a recreated button (counter restarting from 0) neither runs nor jams
    assert session.trigger(0, plan, approve(plan), True) is None
    assert session.trigger(1, plan, approve(plan), True).status == "completed"


def test_update_false_keeps_platform(platform, tmp_path):
    files = digest(MOCK_PLATFORMS / "mock")
    before = list(platform.calibration.single_qubits[0].qubit.flux_coefficients)
    plan = h.build_plan(platform, "flux_amplitude_frequency", FLUX, [0])
    record = run(h.HardwareSession(platform, tmp_path), plan)
    assert record.status == "completed", record.traceback
    assert platform.calibration.single_qubits[0].qubit.flux_coefficients == before
    assert not any("flux_coefficients" in c for c in record.changes)
    assert (record.path / "new_platform").is_dir()
    assert digest(MOCK_PLATFORMS / "mock") == files


def test_update_true_chains_in_memory(platform, tmp_path):
    files = digest(MOCK_PLATFORMS / "mock")
    session = h.HardwareSession(platform, tmp_path)
    platform.calibration.single_qubits[0].qubit.flux_coefficients = None
    assert not h.build_plan(platform, "t1_flux", T1, [0]).ok

    plan = h.build_plan(platform, "flux_amplitude_frequency", FLUX, [0], update=True)
    record = run(session, plan)
    assert record.status == "completed", record.traceback
    assert platform.calibration.single_qubits[0].qubit.flux_coefficients is not None
    assert any("flux_coefficients" in c for c in record.changes)

    t1 = h.build_plan(platform, "t1_flux", T1, [0])
    assert t1.ok, t1.errors
    record = run(session, t1)
    assert record.status == "completed", record.traceback
    figures, _ = h.record_figures(record)
    assert len(figures) == 2
    assert len({r.path for r in session.records}) == 2
    assert digest(MOCK_PLATFORMS / "mock") == files


@pytest.mark.parametrize("routine", ["t1_flux", "t2_flux"])
def test_figures_robust_to_failed_fits(platform, tmp_path, routine):
    record = run(
        h.HardwareSession(platform, tmp_path), h.build_plan(platform, routine, T1, [0])
    )
    assert record.status == "completed", record.traceback
    attr = "t1" if routine == "t1_flux" else "t2"
    n = len(record.data.flux_range)
    record.results = type(record.results)(**{attr: {0: [math.nan] * n}})
    figures, notes = h.record_figures(record)
    assert len(figures) == 2 and any("fit failed" in n for n in notes)
    record.results = None
    figures, _ = h.record_figures(record)
    assert len(figures) == 2


def test_failure_still_disconnects(platform, tmp_path, monkeypatch):
    from qibocal.auto.execute import Executor

    def fail(*args, **kwargs):
        assert platform.is_connected
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(Executor, "run_protocol", fail)
    plan = h.build_plan(platform, "flux_amplitude_frequency", FLUX, [0])
    record = run(h.HardwareSession(platform, tmp_path), plan)
    assert record.status == "failed" and "simulated failure" in record.error
    assert record.disconnected and not platform.is_connected


def test_unique_output_paths(platform, tmp_path):
    import datetime

    plan = h.build_plan(platform, "t1_flux", T1, [0])
    now = datetime.datetime(2026, 10, 16, 12, 0, 0)
    first = h.unique_output_path(tmp_path, plan, now)
    first.mkdir(parents=True)
    second = h.unique_output_path(tmp_path, plan, now)
    assert second != first and not second.exists()


class Widget:
    """Stand-in for a marimo UI element, overriding notebook definitions."""

    def __init__(self, value):
        self.value = value


def notebook_app():
    spec = importlib.util.spec_from_file_location("qw5q_coherence_flux", NOTEBOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.app


@pytest.fixture
def host_sigterm():
    """A host SIGTERM handler, as installed by the marimo kernel."""
    calls = []

    def host(signum, frame):
        calls.append(signum)

    previous = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, host)
    yield host, calls
    signal.signal(signal.SIGTERM, previous)


def test_notebook_opens_offline(monkeypatch, host_sigterm):
    from qibolab import Platform

    def forbidden(self):
        raise AssertionError("the notebook connected on opening")

    monkeypatch.setattr(Platform, "connect", forbidden)
    _, defs = notebook_app().run()
    assert defs["platform"].name == "mock"
    assert defs["plan"] is None
    assert defs["session"].records == []
    assert not defs["platform"].is_connected
    # loading the platform must not hijack the kernel shutdown (export hang)
    assert signal.getsignal(signal.SIGTERM) is host_sigterm[0]


def test_notebook_click_and_reactive_reruns(platform, tmp_path):
    app = notebook_app()
    session = h.HardwareSession(platform, tmp_path)
    values = FLUX | {"targets": [0], "update": False, "crosstalk_qubit": None}
    raw = {k: v for k, v in values.items() if k not in ("targets", "update")}
    expected = h.build_plan(platform, "flux_amplitude_frequency", raw, [0])

    def defs(clicks, code=expected.fingerprint, consent=True, current=session):
        return {
            "platform": platform,
            "session": current,
            "routine_picker": Widget("flux_amplitude_frequency"),
            "hardware_consent": Widget(consent),
            "plan_form": Widget(dict(values)),
            "allow_unverified": Widget(True),
            "confirmation": Widget(code),
            "overshoot_accepted": Widget(False),
            "ranges_confirmed": Widget(True),
            "warnings_reviewed": Widget(True),
            "write_report": Widget(False),
            "run_button": Widget(clicks),
        }

    # opening: the counter only sets the baseline
    _, out = app.run(defs=defs(0))
    assert out["plan"].fingerprint == expected.fingerprint
    assert session.records == []
    # a click runs once
    app.run(defs=defs(1))
    assert [r.status for r in session.records] == ["completed"]
    # reactive re-execution with the same counter never runs again
    app.run(defs=defs(1))
    app.run(defs=defs(1, code="WRONG"))
    assert len(session.records) == 1
    # new clicks failing the gates are recorded, but nothing executes
    app.run(defs=defs(2, code="WRONG"))
    app.run(defs=defs(3, consent=False))
    assert [r.status for r in session.records[1:]] == ["blocked", "blocked"]
    assert len(list(tmp_path.rglob("meta.json"))) == 1
    assert not platform.is_connected
    # a new session (e.g. reopened notebook) with a stale counter never runs
    fresh = h.HardwareSession(platform, tmp_path / "fresh")
    app.run(defs=defs(7, current=fresh))
    assert fresh.records == []


def test_amplitude_overshoot_blocks_unless_accepted(platform):
    raw = T1 | {"amplitude_max": "0.1", "amplitude_step": "0.05"}
    plan = h.build_plan(platform, "t1_flux", raw, [0])
    assert plan.ok, plan.errors
    assert len(plan.overshoot) == 1 and "0.15000000000000002" in plan.overshoot[0]
    exact = dict(plan.preview)["Flux amplitudes, exact values"]
    assert exact == "[0.0, 0.05, 0.1, 0.15000000000000002]"

    reasons = h.blocking_reasons(plan, approve(plan), True)
    assert any("beyond the declared bounds" in r for r in reasons)
    accepted = dataclasses.replace(approve(plan), overshoot_accepted=True)
    assert h.blocking_reasons(plan, accepted, True) == []

    # the suggested bound ends exactly at the intended amplitude
    bound = plan.overshoot[0].rsplit("amplitude_max=", 1)[1].split(" ")[0]
    fixed = h.build_plan(platform, "t1_flux", raw | {"amplitude_max": bound}, [0])
    assert fixed.overshoot == ()
    assert dict(fixed.preview)["Flux amplitudes, exact values"] == "[0.0, 0.05, 0.1]"


@pytest.mark.parametrize(
    ("routine", "keys", "base"),
    [
        (
            "rabi_amplitude_ef",
            ("min_amp", "max_amp", "step_amp"),
            {"pulse_length": "40"},
        ),
        (
            "flux_amplitude_frequency",
            ("amplitude_min", "amplitude_max", "amplitude_step"),
            FLUX,
        ),
    ],
)
def test_exclusive_bound_overshoot(platform, routine, keys, base):
    # np.arange(0.1, 0.4, 0.1) plays the excluded bound 0.4
    raw = base | dict(zip(keys, ["0.1", "0.4", "0.1"], strict=True))
    plan = h.build_plan(platform, routine, raw, [0])
    assert plan.ok, plan.errors
    assert plan.overshoot and "plays [0.4] beyond" in plan.overshoot[0]
    bound = plan.overshoot[0].rsplit(f"{keys[1]}=", 1)[1].split(" ")[0]
    fixed = h.build_plan(platform, routine, raw | {keys[1]: bound}, [0])
    assert fixed.overshoot == ()


def test_load_platform_keeps_host_signal_handlers(host_sigterm):
    from qibocal.calibration import create_calibration_platform

    host = host_sigterm[0]
    previous = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, host)
    try:
        h.load_platform()
        assert signal.getsignal(signal.SIGTERM) is host
        assert signal.getsignal(signal.SIGINT) is host
        # the hazard guarded against: Qibolab replaces both handlers
        create_calibration_platform("mock")
        assert signal.getsignal(signal.SIGTERM) is not host
    finally:
        signal.signal(signal.SIGINT, previous)


def test_sigterm_during_run_disconnects_first(
    platform, tmp_path, monkeypatch, host_sigterm
):
    from qibocal.auto.execute import Executor

    host, calls = host_sigterm
    connected = []

    def terminated(*args, **kwargs):
        assert platform.is_connected
        signal.raise_signal(signal.SIGTERM)
        connected.append(platform.is_connected)
        raise RuntimeError("terminated")

    monkeypatch.setattr(Executor, "run_protocol", terminated)
    plan = h.build_plan(platform, "flux_amplitude_frequency", FLUX, [0])
    record = run(h.HardwareSession(platform, tmp_path), plan)
    # disconnected before the host handler ran, which is restored afterwards
    assert calls == [signal.SIGTERM] and connected == [False]
    assert record.status == "failed" and record.disconnected
    assert signal.getsignal(signal.SIGTERM) is host


def test_interrupt_is_recorded_and_disconnects(platform, tmp_path, monkeypatch):
    from qibocal.auto.execute import Executor

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(Executor, "run_protocol", interrupted)
    session = h.HardwareSession(platform, tmp_path)
    plan = h.build_plan(platform, "flux_amplitude_frequency", FLUX, [0])
    session.claim(0)
    with pytest.raises(KeyboardInterrupt):
        session.trigger(1, plan, approve(plan), True)
    assert session.records[-1].status == "interrupted"
    assert session.records[-1].disconnected and not platform.is_connected


def test_partial_connection_is_cleaned_up(platform, tmp_path, monkeypatch):
    from qibolab import Platform

    class Partial:
        is_connected = False

        def connect(self):
            self.is_connected = True

        def disconnect(self):
            self.is_connected = False

    partial = Partial()
    platform.instruments["partial"] = partial

    def connect(self):
        partial.connect()
        raise RuntimeError("Cannot establish connection to instrument other")

    monkeypatch.setattr(Platform, "connect", connect)
    plan = h.build_plan(platform, "flux_amplitude_frequency", FLUX, [0])
    record = run(h.HardwareSession(platform, tmp_path), plan)
    assert record.status == "failed" and "Cannot establish" in record.error
    assert record.disconnected and not partial.is_connected


ROUTINE_INPUTS = {
    "single_shot_classification": {"nshots": "50"},
    "flux_amplitude_frequency": FLUX,
    "t1_flux": T1,
    "t2_flux": T1,
    "qubit_spectroscopy_ef": {
        "freq_width": "2e7",
        "freq_step": "5e6",
        "drive_duration": "1000",
        "drive_amplitude": "0.1",
        "nshots": "50",
    },
    "rabi_amplitude_ef": {
        "min_amp": "0",
        "max_amp": "0.5",
        "step_amp": "0.1",
        "pulse_length": "40",
        "nshots": "50",
    },
    "dispersive_shift_qutrit": {
        "freq_width": "4e6",
        "freq_step": "1e6",
        "nshots": "50",
    },
    "qutrit_classification": {"nshots": "50"},
}


@pytest.mark.parametrize("update", [False, True])
@pytest.mark.parametrize("routine", list(h.ROUTINES))
def test_every_routine_runs_on_mock(platform, tmp_path, monkeypatch, routine, update):
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    files = digest(MOCK_PLATFORMS / "mock")
    plan = h.build_plan(platform, routine, ROUTINE_INPUTS[routine], [0], update=update)
    assert plan.ok and not plan.overshoot, (plan.errors, plan.overshoot)
    record = run(h.HardwareSession(platform, tmp_path), plan)
    assert record.status == "completed", record.traceback
    assert record.disconnected and not platform.is_connected
    assert (record.path / "platform").is_dir()
    assert (record.path / "new_platform").is_dir()
    if not update:
        assert record.changes == []
    figures, notes = h.record_figures(record)
    assert figures or notes
    assert digest(MOCK_PLATFORMS / "mock") == files
    # nothing written relative to the working directory, which is restored
    assert Path.cwd() == cwd and not any(cwd.iterdir())


def test_classifiers_validated_before_acquisition(platform):
    stale = {"classifiers_list": "naive_bayes"}
    plan = h.build_plan(platform, "single_shot_classification", stale, [0])
    assert any("unknown classifiers ['naive_bayes']" in e for e in plan.errors)
    explicit = {"classifiers_list": "qubit_fit"}
    assert h.build_plan(platform, "single_shot_classification", explicit, [0]).ok
    assert h.build_plan(platform, "single_shot_classification", {}, [0]).ok


# --- critic findings ---------------------------------------------------------

QUTRIT_INPUTS = {
    name: ROUTINE_INPUTS[name]
    for name in (
        "qubit_spectroscopy_ef",
        "rabi_amplitude_ef",
        "dispersive_shift_qutrit",
        "qutrit_classification",
    )
}


def approve_all(plan: h.Plan) -> h.Gate:
    return dataclasses.replace(approve(plan), overshoot_accepted=True)


def test_stock_qw5q_platinum_blocks_every_qutrit_plan(monkeypatch):
    # both from `qibolab._core`: import sorting must not depend on the empty
    # submodule directories of this repository
    from qibolab._core.instruments.qblox.cluster import Cluster
    from qibolab._core.platform.platform import Platform

    entries = [e for e in VERIFIED_PLATFORMS.split(os.pathsep) if e]
    stock = next(
        (Path(e) for e in entries if (Path(e) / "qw5q_platinum").is_dir()), None
    )
    if stock is None:
        pytest.fail(f"no qw5q_platinum in $QIBOLAB_PLATFORMS: {SETUP}", pytrace=False)
    expected = h.EXPECTED["qibolab_platforms_qrc"].commit
    assert h.git_state(stock) == (expected, None), "platforms checkout not verified"

    def forbidden(self):
        raise AssertionError("connection attempted")

    monkeypatch.setattr(Platform, "connect", forbidden)
    monkeypatch.setattr(Cluster, "connect", forbidden)
    monkeypatch.setenv("QIBOLAB_PLATFORMS", str(stock))
    monkeypatch.setattr(h, "PLATFORM", "qw5q_platinum")

    platform = h.load_platform()
    checks = h.preflight(platform)
    assert sorted(platform.qubits) == [0, 1, 2, 3, 4]
    for q, qubit in platform.qubits.items():
        assert (1, 2) not in qubit.drive_extra
        assert not any("drive12" in str(c) for c in platform.parameters.configs)
        assert platform.natives.single_qubit[q].RX12 is None
        assert checks[q]["drive12_channel"].status == h.FAIL
        assert checks[q]["rx12"].status == h.FAIL
        for routine, values in QUTRIT_INPUTS.items():
            plan = h.build_plan(platform, routine, values, [q], checks=checks)
            assert any("drive12 channel" in e for e in plan.errors), (routine, q)
            status = h.routine_status(h.ROUTINES[routine], checks[q])
            assert status.startswith("blocked: drive12 channel"), (routine, q)
    # flux routines need coefficients, missing on q0/q1
    for q in (0, 1):
        assert not h.build_plan(platform, "t1_flux", T1, [q], checks=checks).ok
    assert not platform.is_connected


@pytest.mark.parametrize(
    ("routine", "values", "mutate"),
    [
        (
            "t1_flux",
            T1,
            lambda p: setattr(
                p.calibration.single_qubits[0].qubit,
                "flux_coefficients",
                [-2.5, 0.1, 0.001],
            ),
        ),
        (
            "qubit_spectroscopy_ef",
            ROUTINE_INPUTS["qubit_spectroscopy_ef"],
            lambda p: p.update({"configs.0/drive12.frequency": 4.71e9}),
        ),
        (
            "dispersive_shift_qutrit",
            ROUTINE_INPUTS["dispersive_shift_qutrit"],
            lambda p: p.calibration.single_qubits[0].readout.qudits_frequency.update(
                {1: 5.123e9}
            ),
        ),
        (
            "t2_flux",
            T1,
            lambda p: p.update({"configs.0/drive.frequency": 4.01e9}),
        ),
    ],
)
def test_confirmation_bound_to_platform_state(
    platform, tmp_path, routine, values, mutate
):
    session = h.HardwareSession(platform, tmp_path)
    plan = h.build_plan(platform, routine, values, [0])
    assert plan.ok, plan.errors
    mutate(platform)
    session.claim(0)
    record = session.trigger(1, plan, approve_all(plan), True)
    assert record.status == "blocked"
    assert any("no longer matches" in r for r in record.reasons), record.reasons
    assert not any(tmp_path.iterdir())
    # a rebuilt plan has a new code, and runs
    rebuilt = h.build_plan(platform, routine, values, [0])
    assert rebuilt.fingerprint != plan.fingerprint
    assert session.trigger(2, rebuilt, approve_all(rebuilt), True).status == "completed"


def test_unrelated_qubit_changes_keep_the_code(platform):
    plan = h.build_plan(platform, "t1_flux", T1, [0])
    platform.calibration.single_qubits[1].qubit.flux_coefficients = [-3.0, 0.0, 0.0]
    assert h.build_plan(platform, "t1_flux", T1, [0]).fingerprint == plan.fingerprint


def test_plan_is_immutable(platform):
    raw = {"classifiers_list": "qubit_fit", "nshots": "50"}
    plan = h.build_plan(platform, "single_shot_classification", raw, [0])
    with pytest.raises(TypeError):
        plan.parameters["nshots"] = 1
    assert plan.parameters["classifiers_list"] == ("qubit_fit",)
    kwargs = plan.kwargs()
    kwargs["classifiers_list"].append("qblox_fit")
    kwargs["nshots"] = 1
    raw["nshots"] = "1"
    assert plan.kwargs() == {
        "classifiers_list": ["qubit_fit"],
        "nshots": 50,
        "relaxation_time": platform.settings.relaxation_time,
    }
    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.update = True


def crosstalk(**values):
    return FLUX | {"amplitude_min": "0.1", "crosstalk_qubit": 1} | values


def test_crosstalk_fixed_amplitude_previewed(platform):
    plan = h.build_plan(
        platform,
        "flux_amplitude_frequency",
        crosstalk(flux_pulse_amplitude="-0.7"),
        [0],
    )
    assert plan.ok, plan.errors
    preview = dict(plan.preview)
    assert preview["Fixed flux amplitude on q0 (crosstalk mode)"] == "-0.7 a.u."
    assert preview["Largest |amplitude| played"] == "0.7 a.u."
    other = h.build_plan(
        platform,
        "flux_amplitude_frequency",
        crosstalk(flux_pulse_amplitude="-0.6"),
        [0],
    )
    assert other.fingerprint != plan.fingerprint


@pytest.mark.parametrize(
    "values",
    [
        crosstalk(flux_pulse_amplitude="1e6"),
        crosstalk(flux_pulse_amplitude="-1.0001"),
        crosstalk(amplitude_max="1.5"),
    ],
)
def test_unrepresentable_amplitudes_block(platform, values):
    plan = h.build_plan(platform, "flux_amplitude_frequency", values, [0])
    assert any("outside Qibolab's normalised" in e for e in plan.errors), plan.errors


def test_crosstalk_channel_validated(platform):
    del platform.parameters.configs["1/flux"]
    plan = h.build_plan(platform, "flux_amplitude_frequency", crosstalk(), [0])
    assert any("q1: 1/flux has no DC config" in e for e in plan.errors), plan.errors
    platform.qubits[1].flux = "1/unmapped"
    plan = h.build_plan(platform, "flux_amplitude_frequency", crosstalk(), [0])
    assert any("q1: no flux channel" in e for e in plan.errors), plan.errors


@pytest.mark.parametrize(("amplitude", "ok"), [("-0.1", True), ("1.5", False)])
def test_drive12_amplitude_representability(platform, amplitude, ok):
    values = ROUTINE_INPUTS["qubit_spectroscopy_ef"] | {"drive_amplitude": amplitude}
    plan = h.build_plan(platform, "qubit_spectroscopy_ef", values, [0])
    assert plan.ok is ok, plan.errors
    pulse = dict(plan.preview)["drive12 pulse"]
    assert pulse.endswith(f"amplitude {float(amplitude)!r} a.u.")


def without_rx12(platform):
    platform.update({"native_gates.single_qubit.0.RX12": None})
    assert platform.natives.single_qubit[0].RX12 is None
    return platform


def test_rx12_bootstrap_executes(platform, tmp_path):
    without_rx12(platform)
    checks = h.preflight(platform)
    assert checks[0]["rx12"].status == h.FAIL
    for routine in ("dispersive_shift_qutrit", "qutrit_classification"):
        plan = h.build_plan(platform, routine, ROUTINE_INPUTS[routine], [0])
        assert any("RX12" in e for e in plan.errors), routine

    session = h.HardwareSession(platform, tmp_path)
    spectroscopy = h.build_plan(
        platform, "qubit_spectroscopy_ef", ROUTINE_INPUTS["qubit_spectroscopy_ef"], [0]
    )
    assert run(session, spectroscopy).status == "completed"

    plan = h.build_plan(
        platform, "rabi_amplitude_ef", ROUTINE_INPUTS["rabi_amplitude_ef"], [0], True
    )
    assert any("bootstrap: rectangular, 40 ns" in v for _, v in plan.preview)
    record = run(session, plan)
    assert record.status == "completed", record.traceback
    assert record.data.durations == {0: 40.0}
    amplitude = record.results.amplitude[0]
    rx12 = platform.natives.single_qubit[0].RX12
    if amplitude is None:
        assert rx12 is None
    else:
        [(channel, pulse)] = rx12
        assert channel == "0/drive12"
        assert pulse.envelope.kind == "rectangular"
        assert pulse.duration == 40.0 and pulse.amplitude == amplitude
        # out of range fits are stored by Qibocal, but blocked by preflight
        status = h.preflight(platform)[0]["rx12"].status
        assert status == (h.OK if abs(amplitude) <= 1 else h.FAIL)


def test_unrepresentable_native_blocks(platform):
    from qibolab import Pulse, Rectangular

    pulse = Pulse(duration=40, amplitude=16.5, envelope=Rectangular())
    platform.update({"native_gates.single_qubit.0.RX12": [("0/drive12", pulse)]})
    checks = h.preflight(platform)
    assert checks[0]["rx12"].status == h.FAIL
    plan = h.build_plan(platform, "qutrit_classification", {}, [0], checks=checks)
    assert any("outside [-1, 1]" in e for e in plan.errors)


def test_run_metadata_recorded(platform, tmp_path):
    import json

    plan = h.build_plan(platform, "t1_flux", T1, [0])
    session = h.HardwareSession(platform, tmp_path)
    session.claim(0)
    environment = h.check_environment()
    record = session.trigger(1, plan, approve(plan), True, environment=environment)
    data = json.loads((record.path / h.RUN_METADATA).read_text())
    assert data["fingerprint"] == plan.fingerprint and data["status"] == "completed"
    assert data["state"] == plan.state and data["parameters"]["nshots"] == 50
    assert {row["component"] for row in data["environment"]} >= {"python", "packages"}


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def test_dirty_checkouts_not_verified(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "a.txt").write_text("a")
    git(tmp_path, "add", "a.txt")
    git(
        tmp_path,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-q",
        "-m",
        "a",
    )
    head, dirty = h.git_state(tmp_path)
    assert head and dirty is None
    (tmp_path / "untracked.txt").write_text("b")
    assert "untracked.txt" in h.git_state(tmp_path)[1]
    (tmp_path / "untracked.txt").unlink()
    (tmp_path / "a.txt").write_text("changed")
    _, dirty = h.git_state(tmp_path)
    assert "a.txt" in dirty
    component = h.Component("qibocal", commit=head, problem=dirty, expected_commit=head)
    assert not component.verified and component.status == h.WARN
    assert h.git_state(tmp_path / "missing") == (None, "not a Git checkout")


def test_package_pins_compared(tmp_path):
    constraints = tmp_path / "constraints.txt"
    constraints.write_text("# comment\npytest==0.0.1\nnot-installed-xyz==1.0\n")
    mismatches = h.package_mismatches(constraints)
    assert len(mismatches) == 2 and "not-installed-xyz missing" in mismatches[1]


@pytest.mark.parametrize(
    ("version", "status"), [("3.13.15", h.OK), ("3.13.1", h.WARN), ("3.14.0", h.FAIL)]
)
def test_python_supported_and_tested(monkeypatch, version, status):
    monkeypatch.setattr(h.pyplatform, "python_version", lambda: version)
    python = next(c for c in h.check_environment() if c.name == "python")
    assert python.status == status


@pytest.mark.parametrize(
    ("routine", "label", "acquired"),
    [
        ("t1_flux", "Flux amplitudes", lambda d: d.flux_range),
        ("t2_flux", "Flux amplitudes", lambda d: d.flux_range),
        (
            "flux_amplitude_frequency",
            "Flux amplitudes on target qubits",
            lambda d: d.data[(0, "X")]["amplitude"],
        ),
        ("rabi_amplitude_ef", "RX12 amplitudes", lambda d: d.data[0]["amp"]),
    ],
)
def test_preview_matches_acquired_sweep(platform, tmp_path, routine, label, acquired):
    plan = h.build_plan(platform, routine, ROUTINE_INPUTS[routine], [0])
    record = run(h.HardwareSession(platform, tmp_path), plan)
    assert record.status == "completed", record.traceback
    previewed = dict(plan.preview)[f"{label}, exact values"]
    assert previewed == h._exact(acquired(record.data))

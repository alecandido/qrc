"""Offline smoke tests for the ``qw5q_coherence_flux.py`` notebook.

They exercise the real execution helper (Qibocal ``Executor`` included) on the
``mock`` platform shipped with Qibocal's tests, driven by Qibolab's dummy
instrument: no hardware is involved.
From an environment created with ``run/qw5q_env.bash``::

    pytest run/test_qw5q_helpers.py
"""

import dataclasses
import hashlib
import importlib.util
import math
import signal
from pathlib import Path

import pytest

qibocal = pytest.importorskip("qibocal")

import qw5q_helpers as h

MOCK_PLATFORMS = Path(qibocal.__file__).resolve().parents[2] / "tests" / "platforms"
NOTEBOOK = Path(__file__).parent / "qw5q_coherence_flux.py"

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
        pytest.skip(
            "Qibocal mock platform not found (editable qibocal checkout needed)"
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
    assert {"python", "qibocal", "qibolab", "qibo", "qibolab_platforms_qrc"} <= set(
        names
    )
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
    raw = base | dict(zip(keys, ["1", "1.3", "0.1"], strict=True))
    plan = h.build_plan(platform, routine, raw, [0])
    assert plan.ok, plan.errors
    assert plan.overshoot and "1.3000000000000003" in plan.overshoot[0]
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

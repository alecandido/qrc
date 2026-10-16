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
    "amplitude_max": "0.1",
    "amplitude_step": "0.05",
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
    assert "Flux amplitudes (end included)" in preview
    assert "q0 predicted detuning" in preview
    # Qibocal's inclusive range overshoots amplitude_max: it must be flagged
    assert any("amplitude_max" in w for w in plan.warnings)

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


def test_notebook_opens_offline(monkeypatch):
    from qibolab import Platform

    def forbidden(self):
        raise AssertionError("the notebook connected on opening")

    monkeypatch.setattr(Platform, "connect", forbidden)
    spec = importlib.util.spec_from_file_location("qw5q_coherence_flux", NOTEBOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _, defs = module.app.run()
    assert defs["platform"].name == "mock"
    assert defs["plan"] is None
    assert defs["session"].records == []
    assert not defs["platform"].is_connected

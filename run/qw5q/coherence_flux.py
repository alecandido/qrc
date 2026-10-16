import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")

with app.setup(hide_code=True):
    from datetime import datetime
    from pathlib import Path

    import marimo as mo
    from qibocal import Executor, protocols

    from helpers import (
        calibration_platform,
        save,
        show_data,
        show_qubits,
        show_reports,
    )

    VAR = Path(__file__).resolve().parents[2] / "var" / "qw5q"


@app.cell(hide_code=True)
def _():
    mo.md("""
    # `qw5q_platinum`: coherence vs flux and qutrit routines

    Uses the `Executor` and `BoundProtocol` interface of
    [qiboteam/qibocal#1722](https://github.com/qiboteam/qibocal/pull/1722).

    Edit the parameters, pick a routine and click **Acquire**: instruments are
    only connected during the acquisition, never on opening the notebook or
    editing cells. Fit and report follow automatically; updates only change the
    in-memory platform, on explicit request. See `README.md`.
    """)
    return


@app.cell
def _():
    platform = calibration_platform("qw5q_platinum")
    path = VAR / f"{datetime.now():%Y-%m-%d_%H%M%S}"
    executor = Executor.create(platform=platform, path=path, update=False)
    show_qubits(platform)
    return executor, path, platform


@app.cell
def _():
    # Qibocal units: Hz, ns, a.u. Fill the `None` before running.
    parameters = {
        "single_shot_classification": {"targets": [0], "nshots": 2000},
        # first run, without existing flux_coefficients: amplitude_min=0
        "flux_amplitude_frequency": {
            "targets": [0],
            "amplitude_min": 0.0,
            "amplitude_max": None,
            "amplitude_step": None,
            "duration": None,
        },
        # one qubit at a time; amplitude_max included
        "t1_flux": {
            "targets": [2],
            "delay_min": None,
            "delay_max": None,
            "delay_step": None,
            "amplitude_min": None,
            "amplitude_max": None,
            "amplitude_step": None,
        },
        "t2_flux": {
            "targets": [2],
            "delay_min": None,
            "delay_max": None,
            "delay_step": None,
            "amplitude_min": None,
            "amplitude_max": None,
            "amplitude_step": None,
        },
        # the qutrit routines need a drive12 channel, missing on qw5q_platinum
        "qubit_spectroscopy_ef": {
            "targets": [0],
            "frequency": ("lincenter", 60e6, 200),
            "drive_duration": 2000,
            "drive_amplitude": 0.3,
            "nshots": 1000,
            "relaxation_time": 20e3,
        },
        # without RX12, a rectangular pulse of pulse_length is calibrated
        "rabi_amplitude_ef": {
            "targets": [0],
            "min_amp": 0.05,
            "max_amp": 0.8,
            "step_amp": 0.01,
            "pulse_length": 40,
            "nshots": 500,
        },
        # these two need a calibrated RX12
        "dispersive_shift_qutrit": {
            "targets": [0],
            "freq_width": 5e6,
            "freq_step": 0.05e6,
            "nshots": 500,
        },
        "qutrit_classification": {"targets": [0], "nshots": 2000},
    }
    return (parameters,)


@app.cell
def _(parameters):
    routine = mo.ui.dropdown(list(parameters), value="t1_flux", label="Routine")
    acquire = mo.ui.run_button(label="Acquire", kind="danger")
    mo.hstack([routine, acquire], justify="start")
    return acquire, routine


@app.cell
def _(acquire, executor, parameters, path, routine):
    mo.stop(not acquire.value, mo.md("Click **Acquire** to run the selected routine."))
    kwargs = dict(parameters[routine.value])
    targets = kwargs.pop("targets")
    missing = [k for k, v in kwargs.items() if v is None]
    mo.stop(bool(missing), mo.callout(f"Fill in {missing}", kind="warn"))

    bound = getattr(protocols, routine.value)(**kwargs)
    with executor:
        acquired = executor.acquire(bound, targets=targets)
    acquired = save(acquired, path / f"{datetime.now():%H%M%S}_{routine.value}")
    show_data(acquired.data)
    return (acquired,)


@app.cell
def _(acquired, executor):
    fitted = save(executor.fit(acquired), acquired.path)
    fitted.results
    return (fitted,)


@app.cell
def _(executor, fitted):
    show_reports(executor.report(fitted).reports)
    return


@app.cell
def _():
    apply = mo.ui.run_button(label="Update the in-memory platform")
    apply
    return (apply,)


@app.cell
def _(apply, executor, fitted, platform):
    mo.stop(not apply.value)
    executor.update(fitted)
    show_qubits(platform)
    return


if __name__ == "__main__":
    app.run()

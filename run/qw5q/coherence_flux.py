import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")

with app.setup(hide_code=True):
    from datetime import datetime
    from pathlib import Path

    import marimo as mo
    from qibocal import Executor

    from helpers import calibration_platform, show_data, show_qubits, show_reports

    VAR = Path(__file__).resolve().parents[2] / "var" / "qw5q"


@app.cell(hide_code=True)
def _():
    mo.md("""
    # `qw5q_platinum`: coherence vs flux and qutrit routines

    Edit the parameters, pick a routine and click **Run**: instruments are only
    connected during that execution, never on opening the notebook or editing
    cells. Updates are off by default and only change the in-memory platform;
    the platform folder is never written. See `README.md`.
    """)
    return


@app.cell
def _():
    platform = calibration_platform("qw5q_platinum")
    path = VAR / f"{datetime.now():%Y-%m-%d_%H%M%S}"
    executor = Executor.create(
        platform=platform, path=path, targets=list(platform.qubits), update=True
    )
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
    update = mo.ui.checkbox(label="Update the in-memory platform")
    run = mo.ui.run_button(label="Run", kind="danger")
    mo.hstack([routine, update, run], justify="start")
    return routine, run, update


@app.cell
def _(executor, parameters, routine, run, update):
    mo.stop(not run.value, mo.md("Click **Run** to execute the selected routine."))
    kwargs = dict(parameters[routine.value])
    targets = kwargs.pop("targets")
    missing = [k for k, v in kwargs.items() if v is None]
    mo.stop(bool(missing), mo.callout(f"Fill in {missing}", kind="warn"))

    with executor:
        completed = getattr(executor, routine.value)(
            targets=targets, update=update.value, **kwargs
        )
    return completed, targets


@app.cell
def _(completed, path, platform, targets):
    mo.vstack(
        [
            mo.md(f"Output: `{path}`"),
            show_data(completed.data),
            completed.results,
            show_reports(completed, targets),
            show_qubits(platform),
        ]
    )
    return


if __name__ == "__main__":
    app.run()

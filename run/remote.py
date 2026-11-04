import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium")

with app.setup(hide_code=True):
    import json
    import os
    import shutil
    from pathlib import Path
    from datetime import datetime

    import marimo as mo
    from qibocal import protocols

    from qibocal_widgets import Executor, Session, reports_dir
    from qibocal_widgets.marimo import Marimo
    from qibocal_widgets.remote import (
        Connection,
        Remote,
        config_path,
        connections,
    )

    HERE = Path(__file__).resolve().parent


@app.cell(hide_code=True)
def _():
    mo.md("""
    # Platinum calibration
    """)
    return


@app.cell(hide_code=True)
def _():
    mo.md("""
    ## 1. The connection

    A connection is given inline, or by name. Named connections are stored in
    `remotes.json`, in the configuration shared with Qibocamp, whose desktop
    application can edit them too; `QIBOCAL_WIDGETS_CONNECTION` selects one
    without changing the notebook.

    **Edit the inline connection** to match your cluster, or set
    `QIBOCAL_WIDGETS_CONNECTION` to the name of a stored one.
    """)
    return


@app.cell
def _():
    remote = Remote("platinum")
    mo.vstack(
        [
            mo.md(f"`{remote!r}`"),
            mo.md(
                f"Stored connections, in `{config_path()}`: {sorted(connections())}"
            ),
        ]
    )
    return (remote,)


@app.cell(hide_code=True)
def _():
    mo.md("""
    To store the inline connection, e.g. as `lab`:
    `save_connection("lab", remote.connection)`; then use `Remote("lab")`.

    ## 2. The remote environment

    Acquisitions run in a Python environment on the remote machine. Installing
    it is a separate step, never performed by the acquisitions: it is skipped
    when the requirements did not change, and runs on the access node, outside
    of the queue.
    """)
    return


@app.cell
def _(remote):
    remote.install()
    # if needed, an environment rebuild can be foreced
    # remote.install(rebuild=True)
    return


@app.cell(hide_code=True)
def _():
    mo.md("""
    ## 3. The remote executor

    The executor records every execution in its session folder, here, as
    local executions are.
    """)
    return


@app.cell
def _(remote):
    path = (
        HERE.parent
        / "var"
        / "remote"
        / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    )

    executor = Executor(
        None,
        path=path,
        update=False,
        reuse=True,
        confirm=True,
        runner=remote,
        frontends=[Marimo()],
    )
    executor.path
    return (executor,)


@app.cell(hide_code=True)
def _():
    mo.md("""
    The platform state is asked to the remote machine, the first time it is
    needed.
    """)
    return


@app.cell
def _(executor):
    start = executor.platform_state.snapshot()
    return (start,)


@app.cell(hide_code=True)
def _():
    mo.md("""
    ## 4. Experiments

    The acquisition is a job in the queue (named `qibocal-widgets-acquire`).
    `executor.submit` returns at once, so the notebook stays interactive while
    the job waits: the platform explorer and the queue monitor keep working.
    The cell shows a spinner, replaced by the result when it arrives; the data
    are recorded in the session, fitted and reported here.

    With `reuse=True`, running the cell again (e.g. after editing an upstream
    cell) returns the identical execution instead of acquiring again: the one
    still running, or the one recorded in the session.
    """)
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    #### Targets

    Define the target to operate on.
    """)
    return


@app.cell
def _():
    targets = [(2, 4)]
    targets = [4]
    return (targets,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ### TWPA calibration
    """)
    return


@app.cell(hide_code=True, expand_output=True)
def _(executor, targets):
    # TWPA frequency amplitude sweep

    # TODO: infer the "qcm_rf2/o2/lo" string from the instruments in the platform,
    # for the time being leveraging the fact that there is a single TWPA
    executor.platform_state.update(
        {
            "parameters.configs.qcm_rf2/o2/lo.power": -23.0,
            "parameters.configs.qcm_rf2/o2/lo.frequency": 8.6e9,
        }
    )
    executor.submit(
        protocols.twpa_frequency_offset(
            # pump offset, relative to the configured power
            amplitude=("linspace", 0.6, 0.999, 100),
            frequency=("linwindow", 8.56e9, 40e6, 101),
            probes=[
                executor.platform_state.documents()["calibration"][
                    "single_qubits"
                ][str(q)]["resonator"]["dressed_frequency"]
                for q in range(5)
            ],
            # probes=[7.805e9],
            probe_amplitude=0.1,
            probe_duration=800,
        ),
        nshots=200,
        relaxation_time=1e3,
        targets=targets,
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    If needed, you can also update the TWPA pump parameters manually:
    """)
    return


@app.cell(hide_code=True)
def _(executor):
    # update TWPA parameters

    executor.platform_state.update(
        {
            "parameters.configs.twpa.frequency": 8.562e9,
            "parameters.configs.qcm_rf2/o2/lo.frequency": 8.6e9,
            "parameters.configs.qcm_rf2/o2/lo.power": -25.5,
        }
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ### Mixer calibration
    """)
    return


@app.cell
def _(executor, targets):
    from qibocal.protocols import calibrate_mixers

    executor.submit(calibrate_mixers(), targets=targets)
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ### Spectroscopies
    """)
    return


@app.cell(hide_code=True, expand_output=True)
def _(executor, targets):
    # resonator spectroscopy

    # disable the TWPA for a pump-off scan
    pump_off = False
    if pump_off:
        executor.platform_state.update(
            {"parameters.configs.qcm_rf2/o2/lo.power": -60}
        )

    executor.submit(
        protocols.resonator_spectroscopy(
            frequency=("lincenter", 10e6, 500),
            amplitude=0.1,
            # power_level="high",
        ),
        nshots=1000,
        relaxation_time=0.1e3,
        targets=targets,
    )
    return


@app.cell(hide_code=True, expand_output=True)
def _(executor, targets):
    # resonator punchout
    executor.submit(
        protocols.resonator_punchout(
            freq_width=5e6,
            freq_step=0.1e6,
            min_amp=0.005,
            max_amp=0.6,
            step_amp=0.02,
        ),
        nshots=2000,
        relaxation_time=500,
        targets=targets,
    )
    return


@app.cell(hide_code=True, expand_output=True)
def _(executor, targets):
    # qubit spectroscopy
    executor.submit(
        protocols.qubit_spectroscopy(
            frequency=("lincenter", 20e6, 400),
            drive_duration=8e3,
            drive_amplitude=3e-3,
        ),
        nshots=500,
        relaxation_time=2e3,
        targets=targets,
    )
    return


@app.cell(hide_code=True, expand_output=True)
def _(executor, targets):
    # qubit flux arc
    executor.submit(
        protocols.qubit_flux(
            frequency=("linasym", (50e6, 5e6), 80),
            bias=("lincenter", 0.2, 80),
        ),
        nshots=200,
        relaxation_time=10e3,
        targets=targets,
    )
    return


@app.cell(hide_code=True)
def _(executor, targets):
    # qubit power spectroscopy
    executor.submit(
        protocols.qubit_power_spectroscopy(
            frequency=("lincenter", 300e6, 1000),
            amplitude=("linspace", 1e-3, 300e-3, 40),
            duration=4e3,
        ),
        nshots=100,
        relaxation_time=2e3,
        targets=targets,
    )
    return


@app.cell(hide_code=True)
def _(executor, targets):
    # two-levels crossing
    executor.submit(
        protocols.two_levels_crossing(
            drive1=("lincenter", 40e6, 100),
            drive2=("lincenter", 40e6, 100),
            duration=8e3,
            amplitude=(0.02, 0.2),
        ),
        nshots=100,
        relaxation_time=2e3,
        targets=targets,
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ### Readout
    """)
    return


@app.cell(hide_code=True, expand_output=True)
def _(executor, targets):
    # single-shot classification
    executor.submit(
        protocols.single_shot_classification(),
        nshots=int(1e3),
        targets=targets,
    )
    return


@app.cell(hide_code=True, expand_output=True)
def _(executor, targets):
    # dispersive shift
    executor.submit(
        protocols.dispersive_shift(
            freq_width=5e6,
            freq_step=0.05e6,
        ),
        nshots=500,
        targets=targets,
    )
    return


@app.cell(hide_code=True, expand_output=True)
def _(executor, targets):
    # readout amplitude optimization
    executor.submit(
        protocols.ro_amplitude(
            amplitude_range=(0.01, 0.2, 0.01),
        ),
        nshots=500,
        targets=targets,
    )
    return


@app.cell(hide_code=True, expand_output=True)
def _(executor, targets):
    # readout amplitude optimization
    executor.submit(
        protocols.ro_amplitude_frequency(
            amplitude_range=("lincenter", 0.04, 20),
            frequency_range=("lincenter", 0.8e6, 30),
        ),
        nshots=1000,
        targets=targets,
    )
    return


@app.cell
def _(executor):
    executor.platform_state.update(
        {
            "parameters.configs.4/probe.frequency": 7.809323e9,
            "parameters.native_gates.single_qubit.4.MZ.0.1.probe.amplitude": 0.104,
        }
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ### Single-qubit gate
    """)
    return


@app.cell(hide_code=True, expand_output=True)
def _(executor, targets):
    # rabi amplitude signal
    executor.submit(
        protocols.rabi_amplitude_signal(
            min_amp=0.05,
            max_amp=0.8,
            step_amp=0.01,
        ),
        nshots=100,
        targets=targets,
    )
    return


@app.cell(hide_code=True, expand_output=True)
def _(executor, targets):
    # rabi amplitude
    executor.submit(
        protocols.rabi_amplitude(min_amp=0.01, max_amp=0.5, step_amp=0.01),
        nshots=100,
        targets=targets,
    )
    return


@app.cell(hide_code=True, expand_output=True)
def _(executor, targets):
    # ramsey
    executor.submit(
        protocols.ramsey(
            delay=(10, 20e3, 0.30e3),
            detuning=0.5e6,
        ),
        nshots=500,
        targets=targets,
    )
    return


@app.cell(hide_code=True, expand_output=True)
def _(executor, targets):
    # drag simple
    executor.submit(
        protocols.drag_simple(
            beta_start=-2,
            beta_end=2,
            beta_step=0.1,
        ),
        nshots=300,
        targets=targets,
    )
    return


@app.cell(hide_code=True, expand_output=True)
def _(executor, targets):
    # flipping
    executor.submit(
        protocols.flipping(
            delta_amplitude=0.04,
            nflips_max=30,
            nflips_step=1,
        ),
        nshots=300,
        targets=targets,
    )
    return


@app.cell(hide_code=True, expand_output=True)
def _(executor, targets):
    # allxy
    executor.submit(
        protocols.allxy(),
        nshots=300,
        targets=targets,
    )
    return


@app.cell(hide_code=True, expand_output=True)
def _(executor, targets):
    # standard rb
    executor.submit(
        protocols.standard_rb(
            depths=[2**i for i in range(1, 10)],
            niter=20,
        ),
        nshots=200,
        targets=targets,
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ### Coherences
    """)
    return


@app.cell(hide_code=True)
def _(executor, targets):
    # t1
    executor.submit(
        protocols.t1(
            delay_before_readout_start=1e3,
            delay_before_readout_end=20e3,
            delay_before_readout_step=0.5e3,
        ),
        nshots=200,
        targets=targets,
    )
    return


@app.cell(hide_code=True)
def _(executor, targets):
    # t2
    executor.submit(
        protocols.t2(
            delay_between_pulses_start=1e3,
            delay_between_pulses_end=20e3,
            delay_between_pulses_step=0.5e3,
        ),
        nshots=200,
        targets=targets,
    )
    return


@app.cell(hide_code=True)
def _(executor, targets):
    # t1 flux
    executor.submit(
        protocols.t1_flux(
            delay_min=1e3,
            delay_max=60e3,
            delay_step=2e3,
            amplitude_min=0.08,
            amplitude_max=0.4,
            amplitude_step=0.01,
        ),
        nshots=1000,
        targets=targets,
    )
    return


@app.cell(hide_code=True)
def _(executor, targets):
    # t2 flux
    executor.submit(
        protocols.t2_flux(
            delay_min=0.2e3,
            delay_max=15e3,
            delay_step=0.3e3,
            amplitude_min=0.0,
            amplitude_max=0.1,
            amplitude_step=0.005,
        ),
        nshots=1000,
        targets=targets,
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ### Flux calibration
    """)
    return


@app.cell(hide_code=True, expand_output=True)
def _(executor, targets):
    # flux-amplitude frequency
    executor.submit(
        protocols.flux_amplitude_frequency(
            amplitude_min=0.0,
            amplitude_max=0.1,
            amplitude_step=0.005,
            duration=200,
        ),
        nshots=300,
        targets=targets,
    )
    return


@app.cell(hide_code=True)
def _(executor, targets):
    executor.submit(
        protocols.cryoscope(
            duration_max=80,
            fir=30,
            iir=False,
            flux_pulse_amplitude=0.1,
        ),
        nshots=300,
        relaxation_time=5e3,
        targets=targets,
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ### Two-qubit interactions
    """)
    return


@app.cell(hide_code=True)
def _(executor, targets):
    # ramsey zz
    executor.submit(
        protocols.ramsey_zz(
            delay_range=(10, 2e3, 50),
            detuning=0.5e6,
        ),
        nshots=400,
        targets=targets,
    )
    return


@app.cell(hide_code=True)
def _(executor, targets):
    # jazz
    executor.submit(
        protocols.jazz(delay_range=(10, 2e3, 50)),
        nshots=400,
        targets=targets,
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ### Two-qubit gates
    """)
    return


@app.cell(hide_code=True)
def _():
    # draft
    # for q in targets:
    #     crl = e.cr_length(
    #         duration_range=[10, 400, 10],
    #         pulse_amplitude=0.3,
    #         echo=False,
    #         nshots=1000,
    #         targets=[tuple(q)],
    #     )

    # cra = e.cr_amplitude(
    #     amplitude_range=[0.01, 0.5, 0.01],
    #     pulse_duration=161,
    #     echo=False,
    #     nshots=1000,
    #     targets=[tuple(q)],
    # )

    # cpt = e.cancellation_phase_tuning(
    #     duration_range=[10, 400, 20],
    #     phase_range=[0.0, 6.2, 0.5],
    #     pulse_duration=161,
    #     echo=False,
    #     nshots=1000,
    #     targets=[tuple(q)],
    # )

    # co = e.correct_virtual_z_phases(
    #     theta_start=0,
    #     theta_end=-6.28,
    #     theta_step=-0.1,
    #     nshots=200,
    #     sweep=True,
    # )
    return


@app.cell(hide_code=True)
def _(executor):
    # chevron
    executor.submit(
        protocols.chevron(
            amplitude_min=0.01,
            amplitude_max=0.2,
            amplitude_step=0.01,
            duration_min=8.0,
            duration_max=80.0,
            duration_step=4.0,
            dt=4,
        ),
        nshots=100,
        # targets=targets,
        targets=[[2, 4]],
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ### Qutrits
    """)
    return


@app.cell(hide_code=True)
def _():
    # draft

    # qse = e.qubit_spectroscopy_ef(
    #     frequency=("lincenter", 60e6, 200),
    #     drive_duration=2e3,
    #     drive_amplitude=0.3,
    #     nshots=1000,
    #     relaxation_time=20e3,
    #     targets=[q],
    # )

    # rae = e.rabi_amplitude_ef(
    #     min_amp=0.05,
    #     max_amp=0.8,
    #     step_amp=0.01,
    #     pulse_length=40,
    #     nshots=500,
    #     targets=[q],
    # )

    # sse = e.qutrit_classification(
    #     nshots=int(2e3),
    #     targets=[q],
    # )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## 5. Platform State

    Platform holds a state...

    ### Explore

    It can be explored, and edited, as a local one. Edits travel with
    the next acquisitions.
    """)
    return


@app.cell
def _(executor):
    executor.platform_state.explore(editable=True)
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ### Save

    Persist the platform state in the folder it was loaded from.
    """)
    return


@app.cell
def _():
    # this is not safe to be executed every time, decomment when needed
    # executor.platform_state.save()
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ### Diff

    Platform diffs from start, or other relevant checkpoints.

    /// tip | Scheduling
    Uncomment the `mo.stop()` line to schedule the diff behind an execution. Just assign `pending` to the result value of the execution to obtain the handle to wait for.
    To still the spinner and results, just output it right below the call as well, i.e.
    ```py
    pending = executor.submit(...)
    pending
    ```
    ///
    """)
    return


@app.cell
def _(executor, start):
    assert start is not None

    # mo.stop(pending() is None, mo.md("*Waiting for job…*"))
    executor.platform_state.diff(start)
    return


@app.cell(hide_code=True)
def _():
    mo.md("""
    ## 6. The queue

    While acquisitions wait in the queue, it can be followed from here: the
    whole partition, with your jobs highlighted and the runner's tagged. The
    monitor refreshes periodically while displayed.
    """)
    return


@app.cell
def _(remote):
    remote.monitor(interval=30)
    return


if __name__ == "__main__":
    app.run()

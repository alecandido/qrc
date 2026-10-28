import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium")

with app.setup(hide_code=True):
    import json
    import os
    import shutil
    from pathlib import Path

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
def _(datetime, remote):
    path = (
        HERE.parent
        / "var"
        / "remote"
        / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    )

    executor = Executor(
        None,
        path=path,
        update=True,
        runner=remote,
        frontends=[Marimo()],
    )
    executor.path
    return (executor,)


@app.cell(hide_code=True)
def _():
    mo.md("""
    The platform state is asked to the remote machine, the first time it is
    needed: it can be explored, and edited, as a local one. Edits travel with
    the next acquisitions.
    """)
    return


@app.cell
def _(executor):
    start = executor.platform_state.snapshot()
    executor.platform_state.explore()
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
    ### Spectroscopies
    """)
    return


@app.cell
def _(executor):
    executor.submit(
        protocols.qubit_flux(
            frequency=("lincenter", 100e6, 30),
            bias=("lincenter", 0.3, 30),
        ),
        nshots=int(1e3),
        reuse=True,
        targets=[4],
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ### Single-qubit gate
    """)
    return


@app.cell
def _(executor):
    executor.submit(
        protocols.single_shot_classification(),
        nshots=int(1e3),
        reuse=True,
        targets=[4],
    )
    return


@app.cell
def _(executor):
    executor.submit(
        protocols.rabi_amplitude(min_amp=0.01, max_amp=0.5, step_amp=0.01),
        nshots=100,
        reuse=True,
        targets=[4],
    )
    return


@app.cell
def _(executor):
    executor.submit(
        protocols.ramsey(delay=(10, 50e3, 1.5e3)),
        nshots=500,
        reuse=True,
        targets=[4],
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ### Two-qubit gates
    """)
    return


@app.cell
def _(executor):
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
        reuse=True,
        targets=[[2, 4]],
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## 5. Diffs

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

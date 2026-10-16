import signal
from dataclasses import replace

import marimo as mo
import numpy as np
import pandas as pd
from qibocal import create_calibration_platform


def calibration_platform(name: str):
    """Create the platform, keeping the process signal handlers.

    Qibolab replaces SIGINT/SIGTERM handlers with one raising ``RuntimeError``,
    which prevents interrupting or shutting down the Marimo kernel.
    """
    handlers = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
    platform = create_calibration_platform(name)
    for s, handler in handlers.items():
        signal.signal(s, handler)
    return platform


def save(completed, path):
    """Dump data and results, which the executor does not persist."""
    path.mkdir(parents=True, exist_ok=True)
    completed = replace(completed, path=path)
    completed.dump_data()
    completed.dump_results()
    return completed


def show_qubits(platform):
    """Calibration relevant for flux and qutrit routines."""
    rows = []
    for q, qubit in platform.qubits.items():
        cal = platform.calibration.single_qubits[q].qubit
        flux = platform.parameters.configs.get(qubit.flux)
        rows.append(
            {
                "qubit": q,
                "flux offset": getattr(flux, "offset", None),
                "sweetspot": cal.sweetspot,
                "flux_coefficients": cal.flux_coefficients,
                "frequency_12": cal.frequency_12,
                "drive12": qubit.drive_extra.get((1, 2)),
                "RX12": platform.natives.single_qubit[q].RX12 is not None,
            }
        )
    return mo.ui.table(pd.DataFrame(rows), selection=None)


def show_data(data):
    tables = {}
    for target, records in data.data.items():
        array = np.asarray(records)
        tables[f"Raw data: {target}"] = (
            mo.ui.table(pd.DataFrame(records))
            if array.dtype.names or array.ndim <= 2
            # e.g. single shots of t1_flux/t2_flux
            else mo.md(f"`{array.dtype}` array of shape `{array.shape}`")
        )
    return mo.accordion(tables)


def show_reports(reports):
    outputs = {}
    for target, (figures, table) in reports.items():
        plots = [mo.ui.plotly(figure) for figure in figures]
        if table:
            plots.append(mo.Html(table))
        outputs[f"Target {target}"] = mo.vstack(plots)
    return mo.accordion(outputs)

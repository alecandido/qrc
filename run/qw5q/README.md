# `qw5q_platinum`: coherence vs flux and qutrit routines

Marimo notebook (`coherence_flux.py`) running Qibocal routines on `qw5q_platinum`,
with a few display utilities (`helpers.py`). Not run on hardware yet.

## Requirements

- `marimo`, `qibocal` (with `qibolab`) and `pandas`, on Python `>=3.11,<3.14`;
- the platform drivers: `qblox-instruments` and `lark` (Qblox cluster), `qcodes`
  and `qcodes_contrib_drivers` (TWPA pump);
- `$QIBOLAB_PLATFORMS` pointing to `qibolab_platforms_qrc`.

Written against `qibocal` 0.2.7, `qibolab` 0.2.18 and platforms `e77ac724`.
The submodules of this repository cannot load `qw5q_platinum` at their current
pins (pinned `qibolab` 0.2.16 rejects the current platform parameters).

## Usage

Edit the `parameters` cell (Qibocal units: Hz, ns, a.u.; fill the `None`), pick
a routine and click **Run**. Instruments are connected only during that
execution (`with executor:`), which disconnects at the end, also on failures.

- Results go to `var/qw5q/<date>_<time>/`, one folder per notebook session.
- Updates are off by default. When enabled, they only change the in-memory
  platform, to chain routines; the platform folder is never written, the updated
  copy is in the output folder.
- Suggested order: `single_shot_classification` (if needed),
  `flux_amplitude_frequency` with updates (it writes `flux_coefficients`), then
  `t1_flux` / `t2_flux`.

## Platform status (`e77ac724`)

- `flux_coefficients` are missing on q0/q1 (required by `t1_flux`/`t2_flux`), and
  q3/q4 still have the February values, although the sweetspots changed.
- No `drive12` channel and no RX12 on any qubit: all qutrit routines fail. Add
  `drive_extra[(1, 2)]` in `qw5q_platinum/platform.py` (as `qpu169` does), with
  IQ configs near `frequency_12`. Then `qubit_spectroscopy_ef` and
  `rabi_amplitude_ef` (rectangular pulse of `pulse_length`) bootstrap RX12, which
  `dispersive_shift_qutrit` and `qutrit_classification` need.

## Qibocal caveats

- `t1_flux`/`t2_flux` only sweep the flux pulse of the last target: one qubit at a
  time. The amplitude range includes `amplitude_max`, and `np.arange` may add a
  point slightly beyond it (e.g. `0.15000000000000002` for max `0.1`, step `0.05`).
- `flux_amplitude_frequency` also writes a flux crosstalk matrix element.
- `single_shot_classification` writes `qubit<N>/` in the working directory.
- No Qibocal routine measures EF coherence, with or without flux.
- Qibolab replaces the SIGINT/SIGTERM handlers when creating a platform, blocking
  the Marimo kernel shutdown: `calibration_platform` restores them.

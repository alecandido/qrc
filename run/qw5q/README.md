# `qw5q_platinum`: coherence vs flux and qutrit routines

Marimo notebook (`coherence_flux.py`) running Qibocal routines on `qw5q_platinum`,
with a few display utilities (`helpers.py`). Not run on hardware yet.

## Requirements

- `marimo`, `pandas` and Qibocal with the protocol interface of
  [qiboteam/qibocal#1722](https://github.com/qiboteam/qibocal/pull/1722)
  (not merged yet, written against `ae0e797a`):

  ```sh
  pip install "qibocal @ git+https://github.com/qiboteam/qibocal.git@protodev"
  ```

- `qibolab` 0.2.18 or later: the current platform parameters need it;
- the platform drivers: `qblox-instruments` and `lark` (Qblox cluster), `qcodes`
  and `qcodes_contrib_drivers` (TWPA pump);
- `$QIBOLAB_PLATFORMS` pointing to `qibolab_platforms_qrc` (written against
  `e77ac724`).

The submodules of this repository cannot load `qw5q_platinum` at their current
pins (pinned `qibolab` 0.2.16 rejects the current platform parameters).

## Usage

Edit the `parameters` cell (Qibocal units: Hz, ns, a.u.; fill the `None`), pick
a routine and click **Acquire**. Instruments are connected only during the
acquisition (`with executor:`), which disconnects at the end, also on failures.
Fit and report follow, without hardware.

- Each notebook session writes to `var/qw5q/<date>_<time>/`, with a
  `<time>_<routine>/` folder per acquisition holding data and fit results (the
  executor does not save them by itself).
- Updates are only applied by **Update the in-memory platform**, and only change
  the platform held by the notebook, to chain routines: the platform folder is
  never written, the updated copy is dumped in the session folder.
- Suggested order: `single_shot_classification` (if needed),
  `flux_amplitude_frequency` and update (it writes `flux_coefficients`), then
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

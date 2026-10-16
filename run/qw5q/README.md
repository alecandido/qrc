# `qw5q_platinum`: coherence vs flux and qutrit routines

Marimo notebook (`coherence_flux.py`, with `helpers.py`) to run coherence-vs-flux
and qutrit characterization on `qw5q_platinum`.
Never run on hardware so far.

## Requirements

- `marimo` and `qibocal` (with `qibolab`), on Python `>=3.11,<3.14`;
- the platform drivers: `qblox-instruments` and `lark` (Qblox cluster), `qcodes`
  and `qcodes_contrib_drivers` (TWPA pump);
- `$QIBOLAB_PLATFORMS` pointing to a `qibolab_platforms_qrc` checkout.

The notebook was written against `qibocal` 0.2.7 / `qibolab` 0.2.18 and platforms
`e77ac724` (older versions are flagged).
The submodules of this repository cannot load `qw5q_platinum` at their current
pins: pinned `qibolab` 0.2.16 rejects the platform parameters of platforms `main`
(`scale_q`, qiboteam/qibolab#1593), and the pinned platforms use a `bounds` config
kind no longer supported.

## Workflow

1. **Environment** and **platform** are loaded offline: opening the notebook or
   editing widgets never connects.
2. **Preflight** per qubit, refreshed after every run: natives, discrimination,
   flux channel and offset vs sweetspot, `flux_coefficients`, drive12 channel,
   `frequency_12`, state-1 readout frequency, RX12. A table summarizes which
   routines are ready.
3. **Plan**: pick a routine, fill the form, submit. The preview shows the exact
   swept values, fixed amplitudes, the largest amplitude played, scan centres,
   predicted detunings, and a duration lower bound.
4. **Confirmation**: confirm the ranges, acknowledge warnings, accept any
   amplitude beyond the declared bounds, type the confirmation code.
5. **Run**: each click runs at most once.

Suggested order: `single_shot_classification` (if needed) ->
`flux_amplitude_frequency` (`update=True` to chain) -> `t1_flux` / `t2_flux`.

## Routines

Scan fields are blank by default (no range is assumed safe), in Qibocal units.
`nshots` and `relaxation_time` default to the platform settings.

| Routine                      | Fields                                                                     | Targets | Update (if enabled)                      |
| ---------------------------- | -------------------------------------------------------------------------- | ------- | ---------------------------------------- |
| `single_shot_classification` | `classifiers_list` (blank: `qubit_fit`)                                    | any     | threshold, IQ angle, centroids, fidelity |
| `flux_amplitude_frequency`   | `amplitude_{min,max,step}` [a.u.], `duration` [ns], `crosstalk_qubit`, `flux_pulse_amplitude` | any | `flux_coefficients`, crosstalk element |
| `t1_flux`, `t2_flux`         | `delay_{min,max,step}` [ns], `amplitude_{min,max,step}` [a.u.]             | one     | none                                     |
| `qubit_spectroscopy_ef`      | `freq_width`, `freq_step` [Hz], `drive_duration` [ns], `drive_amplitude` [a.u.] | any | drive12 frequency, `frequency_12`   |
| `rabi_amplitude_ef`          | `{min,max,step}_amp` [a.u.], `pulse_length` [ns]                           | any     | RX12                                     |
| `dispersive_shift_qutrit`    | `freq_width`, `freq_step` [Hz]                                             | any     | none                                     |
| `qutrit_classification`      | none                                                                       | any     | none                                     |

- In crosstalk mode, `flux_amplitude_frequency` sweeps the crosstalk qubit's flux
  line and plays `flux_pulse_amplitude` on the targets' lines: both are previewed.
- Classifier names are checked against the installed Qibocal (`qubit_fit`,
  `qblox_fit`); `naive_bayes` & co., still in Qibocal docstrings, no longer exist.

### Amplitudes

- Amplitudes outside [-1, 1] (swept, fixed, or in native pulses) are rejected:
  Qibolab normalises amplitudes to that range. This is not a device safety limit.
- Qibocal sweeps use `np.arange`, whose floating point end points may play values
  beyond the declared bound: `t1_flux` with `amplitude_max=0.1`, step `0.05`,
  plays `0.15000000000000002`; an exclusive `(0.1, 0.4, 0.1)` plays `0.4`. Such
  points block the run unless explicitly accepted, and a corrected bound is
  suggested.

### Calibration on platforms `e77ac724`

| Qubit | `flux_coefficients`  | Readout fidelity |
| ----- | -------------------- | ---------------- |
| 0     | missing              | 0.71             |
| 1     | missing              | 0.72             |
| 2     | set                  | 0.94             |
| 3     | set, likely stale \* | 0.84             |
| 4     | set, likely stale \* | 0.90             |

\* identical to the February values, although the sweetspots changed since, and
with positive curvature.

`t1_flux`/`t2_flux` need coefficients; without them, `flux_amplitude_frequency`
requires `amplitude_min=0` and no crosstalk qubit.

## Hardware safety

- Instruments are only connected for a new click on the run button, and only if
  hardware access is enabled, all confirmations are given, the environment has
  no errors, and the plan rebuilt against the in-memory platform is identical.
- The confirmation code covers parameters, the exact preview and the platform
  state of the involved qubits (configs, natives, calibration): e.g. new flux
  coefficients or frequencies require a new code.
- `update=False` by default; `update=True` only changes the platform in memory,
  to chain routines. `$QIBOLAB_PLATFORMS` is never written: each run dumps
  `platform/` and `new_platform/` to its output folder, promoting is manual.
- Each run gets a new folder `var/qw5q/<date>/<time>_<routine>_<targets>_<code>`
  (nothing is overwritten or deleted), including `qw5q_run.json` with plan,
  outcome, in-memory changes and environment.
- The platform is disconnected after every run, also on failures, interruptions
  and SIGTERM. Qibolab replaces the process SIGINT/SIGTERM handlers on platform
  creation, which blocks marimo kernels: the notebook keeps the host handlers.

## Qutrit support

| Routine                   | drive12 channel | RX12                                         |
| ------------------------- | --------------- | -------------------------------------------- |
| `qubit_spectroscopy_ef`   | required        | not needed                                   |
| `rabi_amplitude_ef`       | required        | optional (else rectangular, `pulse_length`)  |
| `dispersive_shift_qutrit` | required        | required                                     |
| `qutrit_classification`   | required        | required                                     |

On the stock `qw5q_platinum` all four are blocked: `platform.py` defines no
`drive_extra[(1, 2)]` (no `{i}/drive12` channel or config), and RX12 is null for
all qubits. The notebook never patches channels: add `drive12` in
`qibolab_platforms_qrc`, sharing drive port, LO and mixer as `qpu169` does, with
IQ configs near `frequency_12`.

Qibocal has no EF coherence routines, with or without flux: `t1`, `t2`,
`ramsey`, `spin_echo`, `cpmg`, `zeno` and variants only address 0-1.

## Caveats

- `t1_flux`/`t2_flux` only sweep the flux pulse of the last target: one qubit at a
  time. Their Qibocal plots fail if any fit fails, so the notebook plots raw P(1)
  maps and the successful fits.
- `t2_flux` applies no software detuning: fits near zero detuning may fail.
- `flux_amplitude_frequency` also writes a flux crosstalk matrix element.
- A poor `rabi_amplitude_ef` fit may store an RX12 amplitude above 1: preflight
  then blocks the routines using it.

# `qw5q_platinum` coherence-vs-flux notebook: prerequisites

Planning notes for a Marimo notebook (to follow, not yet implemented) running
coherence-vs-flux and qutrit characterization on `qw5q_platinum`.
Everything below was verified offline on 2026-10-16, without hardware access.

## Verified versions

The notebook targets the following upstream revisions, **not** the submodule
pointers currently recorded in this repository (which are left untouched):

| Repository              | Pinned here | Verified upstream `main`                   |
| ----------------------- | ----------- | ------------------------------------------ |
| `qibocal`               | `1b23725f`  | `539a32f86ef40b8b3f14858623f973ddf2751d2c` |
| `qibolab`               | `fcdc193b`  | `004c14b4f622448f593476a9e0a80714954ceed6` |
| `qibolab_platforms_qrc` | `40fe9443`  | `e77ac724ccac2c3d98baf2e310ff6794a8823646` |

That is `qibolab` 0.2.18 and `qibocal` 0.2.7 (which requires `qibolab>=0.2.17`).

### Pinned incompatibility

The current pins cannot load `qw5q_platinum`:

- pinned `qibolab` (0.2.16) rejects platforms `main` parameters (`configs.*.scale_q`:
  extra input, introduced by qiboteam/qibolab#1593);
- both pinned and `main` `qibolab` reject the pinned platform parameters (unknown
  `bounds` config kind).

Only the three `main` revisions above load the platform successfully.
Updating the submodules is a separate, explicit decision.

## Notebook scope

1. Offline prerequisites report, per qubit: `flux_coefficients`, readout
   fidelity, `RX12`, `drive_extra[(1, 2)]`.
2. Optional `single_shot_classification` refresh (all routines below acquire in
   discrimination mode; q0/q1 fidelities are ~0.71/0.72).
3. `flux_amplitude_frequency` (first run with `amplitude_min=0`, no
   `crosstalk_qubit`): the only routine writing `flux_coefficients`.
4. `t1_flux` / `t2_flux` (`delay_{min,max,step}`, `amplitude_{min,max,step}`), one
   qubit per call.
5. Qutrit section (`qubit_spectroscopy_ef`, `rabi_amplitude_ef`,
   `dispersive_shift_qutrit`, `qutrit_classification`): blocked, see below.

### Calibration prerequisites (platforms `main`)

| Qubit | `flux_coefficients`  | Readout fidelity |
| ----- | -------------------- | ---------------- |
| 0     | missing              | 0.71             |
| 1     | missing              | 0.72             |
| 2     | set                  | 0.94             |
| 3     | set, likely stale \* | 0.84             |
| 4     | set, likely stale \* | 0.90             |

\* identical to the February values, although the sweetspots changed since.

`t1_flux` and `t2_flux` assert on missing coefficients.

### Known routine caveats

- `t1_sequence` only sweeps the flux pulse of the last target: run `t1_flux` and
  `t2_flux` with a single target.
- `t1_flux`/`t2_flux` have no update function; their plots may fail if any single
  fit fails, so the notebook will plot from the acquired data.
- `flux_amplitude_frequency` always updates the flux crosstalk matrix element too.

## Hardware safety

- `Executor.open()` connects to the instruments immediately: hardware cells will be
  gated behind explicit run buttons, never executed on notebook load.
- Executor updates default to on: the notebook will default to `update=False`.
- Updated parameters are only dumped to the output folder (`platform/`,
  `new_platform/`), never to `$QIBOLAB_PLATFORMS`; promoting them is manual.
- `force=True` deletes the output folder: outputs go to fresh paths under `var/`.
- Development and checks use the `qibocal` `mock` platform only (all seven
  routines above run there).

## Qutrit blockers: `drive12` / `RX12`

- `RX12` is `null` for all five qubits, both at the pin and on platforms `main`.
- `qw5q_platinum/platform.py` builds qubits with `Qubit.default(i)`, so
  `drive_extra` is empty and no `{i}/drive12` channel or config exists.
- All four qutrit routines access `platform.qubits[q].drive_extra[1, 2]` and fail
  with a `KeyError` before acquisition.
- Fix: in `qibolab_platforms_qrc`, add `drive_extra[(1, 2)] = f"{i}/drive12"`
  sharing the drive port, LO and mixer (as `qpu169/platform.py` does), plus
  `{i}/drive12` IQ configs at `frequency_12` (already in `calibration.json`).

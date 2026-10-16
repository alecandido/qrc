# `qw5q_platinum` coherence-vs-flux notebook

Marimo notebook for coherence-vs-flux and qutrit characterization on
`qw5q_platinum`.
Facts below were verified offline on 2026-10-16, without hardware access.

**Status:** validated offline only (see [Validation](#validation)), pending review;
never run on hardware.

| File                     | Content                                                  |
| ------------------------ | -------------------------------------------------------- |
| `qw5q_coherence_flux.py` | Marimo notebook                                          |
| `qw5q_helpers.py`        | preflight, plan validation, gated execution and plots    |
| `test_qw5q_helpers.py`   | mandatory offline safety tests                           |
| `qw5q_validate.bash`     | mandatory offline validation entry point                 |
| `qw5q_guard/`            | hardware guard used by the validation                    |
| `qw5q_env.bash`          | isolated environment at the verified revisions           |
| `qw5q_constraints.txt`   | exact package versions of the tested environment         |

## Setup and validation

```sh
nix shell nixpkgs#uv nixpkgs#python313   # or any git + uv + Python 3.13
run/qw5q_env.bash /tmp/qw5q-env          # clones and installs outside the repo
. /tmp/qw5q-env/env.bash                 # venv, QIBOLAB_PLATFORMS, QIBO_BACKEND
run/qw5q_validate.bash                   # mandatory, offline
marimo edit run/qw5q_coherence_flux.py
```

`qw5q_env.bash`:

- clones Qibocal, Qibolab and the platforms at the verified commits, and **stops**
  if an existing checkout has modified or untracked files (local work is never
  reset or deleted);
- **recreates** the virtual environment on every run, with the exact pins of
  `qw5q_constraints.txt`, so that stale or extra packages never survive;
- finally runs the notebook's environment verification, and fails unless it
  passes.

`qw5q_validate.bash` fails on an unverified environment, on any failed or
**skipped** test (or fewer than expected), on `marimo check --strict` findings,
on any connection attempt or hang during headless notebook exports, and on lint.
The tests themselves fail, rather than skip, when Qibocal, its `mock` platform or
the verified platforms checkout are missing.
This repository has no CI: the entry point has to be run manually.

### Environment verification

The notebook (and both scripts) compare the running environment with the tested
one, and require an explicit opt-in to run on anything else:

- Python must be in `[3.11, 3.14)`, as required by Qibocal and Qibolab `main`;
  any version other than the tested 3.13.15 is flagged as untested.
  The repository `pyproject.toml` allows `<3.15`: that does not apply here.
- `qibocal`, `qibolab` and `qibolab_platforms_qrc` must be **clean** Git
  checkouts (no modified, staged or untracked files) at the verified commits.
- `qibo` must be the pinned 0.3.6, and every pin of `qw5q_constraints.txt` must
  match the installed version. Extra packages are not detected by the notebook:
  `qw5q_env.bash` prevents them by recreating the environment.

## Verified versions

The notebook targets the following upstream revisions, **not** the submodule
pointers recorded in this repository (which are left untouched):

| Repository              | Pinned here | Verified upstream `main`                   |
| ----------------------- | ----------- | ------------------------------------------ |
| `qibocal`               | `1b23725f`  | `539a32f86ef40b8b3f14858623f973ddf2751d2c` |
| `qibolab`               | `fcdc193b`  | `004c14b4f622448f593476a9e0a80714954ceed6` |
| `qibolab_platforms_qrc` | `40fe9443`  | `e77ac724ccac2c3d98baf2e310ff6794a8823646` |

That is `qibolab` 0.2.18 and `qibocal` 0.2.7 (which requires `qibolab>=0.2.17`).

The current pins cannot load `qw5q_platinum`:

- pinned `qibolab` (0.2.16) rejects platforms `main` parameters (`configs.*.scale_q`:
  extra input, introduced by qiboteam/qibolab#1593);
- both pinned and `main` `qibolab` reject the pinned platform parameters (unknown
  `bounds` config kind).

Updating the submodules is a separate, explicit decision.

## Workflow

1. **Environment** and **platform** are loaded offline (`create_calibration_platform`
   never connects).
2. **Preflight** per qubit, refreshed after every run: RX/MZ natives (including
   amplitudes outside [-1, 1]), discrimination threshold and fidelity, flux channel
   and offset vs sweetspot, `flux_coefficients` (missing, unusable, or suspicious),
   drive12 channel and config, `frequency_12`, state-1 readout frequency, RX12.
   A routine support table summarizes readiness for each qubit.
3. **Plan**: pick a routine, fill the form and submit it.
   The plan holds deep, read-only copies of the submitted values; Qibocal
   parameters are instantiated to preview the *exact* swept values, every fixed
   amplitude, the largest amplitude played, scan centres, predicted detunings, and
   a duration lower bound.
4. **Confirmation**: confirm the ranges, acknowledge warnings, accept any amplitude
   beyond the declared bounds (see [Amplitude end points](#amplitude-end-points)),
   type the plan code.
5. **Run**: one click, one execution.

Suggested order: `single_shot_classification` (if needed) ->
`flux_amplitude_frequency` (`update=True` to chain) -> `t1_flux` / `t2_flux`.

## Routines

All scan fields are blank by default (no limit is assumed safe), in Qibocal units.
`nshots` and `relaxation_time` default to the platform settings.

| Routine                      | Fields                                                                     | Targets | Update (if enabled)                           |
| ---------------------------- | -------------------------------------------------------------------------- | ------- | --------------------------------------------- |
| `single_shot_classification` | `classifiers_list` (blank: `qubit_fit`)                                    | any     | threshold, IQ angle, centroids, fidelity      |
| `flux_amplitude_frequency`   | `amplitude_{min,max,step}` [a.u.], `duration` [ns], `crosstalk_qubit`, `flux_pulse_amplitude` | any | `flux_coefficients`, crosstalk element |
| `t1_flux`, `t2_flux`         | `delay_{min,max,step}` [ns], `amplitude_{min,max,step}` [a.u.]             | one     | none                                          |
| `qubit_spectroscopy_ef`      | `freq_width`, `freq_step` [Hz], `drive_duration` [ns], `drive_amplitude` [a.u.] | any | drive12 frequency, `frequency_12`        |
| `rabi_amplitude_ef`          | `{min,max,step}_amp` [a.u.], `pulse_length` [ns]                           | any     | RX12                                          |
| `dispersive_shift_qutrit`    | `freq_width`, `freq_step` [Hz]                                             | any     | none                                          |
| `qutrit_classification`      | none                                                                       | any     | none                                          |

- `qubit_spectroscopy_ef` always requires `drive_amplitude` and `drive_duration`,
  instead of silently using Qibocal's defaults (1.0 and 4000 ns).
- In crosstalk mode, `flux_amplitude_frequency` sweeps the crosstalk qubit's flux
  line and plays `flux_pulse_amplitude` on the targets' lines: both are previewed,
  and the crosstalk qubit's flux channel and DC config are checked like the
  targets' ones.
- Classifier names are checked against the installed Qibocal (`qubit_fit`,
  `qblox_fit`): the `naive_bayes`, `nn`, ... models listed in Qibocal docstrings
  no longer exist. `qutrit_classification` trains no classifier, so it has no
  field.

### Amplitudes

Any amplitude outside [-1, 1] (swept, fixed, or in a native pulse) is an error:
Qibolab normalises amplitudes to that range and the Qblox driver rejects others.
This is a **representability** bound, not a device safety limit: no safe range is
assumed, the operator confirms the previewed values.

### Amplitude end points

Qibocal builds amplitude sweeps with `np.arange`, whose floating point end points
may play amplitudes beyond the declared bound: `t1_flux`/`t2_flux` (bound
included, `np.arange(min, max + step, step)`) play `0, 0.05, 0.1,
0.15000000000000002` for `amplitude_max=0.1`, and exclusive bounds
(`flux_amplitude_frequency`, `rabi_amplitude_ef`) play `0.4` for
`(0.1, 0.4, 0.1)`. These are the values the Qblox driver plays (its loops have
`len(sweeper)` iterations from `irange`), and tests check that the previewed
values equal the acquired sweeps.

The preview lists the exact values, and any point beyond the declared bound
**blocks** the run unless the operator explicitly accepts it. The message
suggests a bound, verified against Qibocal's range, ending at the intended
amplitude (e.g. `amplitude_max=0.09999999999999999` ends at `0.1`).

### Calibration prerequisites (platforms `e77ac724`)

| Qubit | `flux_coefficients`  | Readout fidelity |
| ----- | -------------------- | ---------------- |
| 0     | missing              | 0.71             |
| 1     | missing              | 0.72             |
| 2     | set                  | 0.94             |
| 3     | set, likely stale \* | 0.84             |
| 4     | set, likely stale \* | 0.90             |

\* identical to the February values, although the sweetspots changed since; the
preflight also flags their positive curvature.

- `t1_flux` and `t2_flux` are blocked without coefficients.
- `flux_amplitude_frequency` without coefficients needs `amplitude_min=0` and no
  crosstalk qubit.

## Hardware safety

- Nothing connects on opening the notebook or editing widgets.
  Connection happens only inside `HardwareSession.trigger`, for a click that is
  *new* (the button counter is a nonce: the first observed value only sets the
  baseline, and each value is consumed once, so reactive re-execution never
  re-triggers), and only if:
  - hardware access is enabled,
  - the scan ranges are confirmed,
  - the typed code matches the plan fingerprint,
  - plan warnings are acknowledged,
  - amplitudes beyond the declared bounds, if any, are explicitly accepted,
  - the environment is verified, or explicitly allowed,
  - the plan, rebuilt against the current in-memory platform, is identical:
    parameters, preview, platform state, errors, warnings and end points.
- The fingerprint (6 hexadecimal characters, a typed confirmation rather than a
  cryptographic check) covers parameters, the exact preview and a digest of the
  execution-relevant platform state of the involved qubits (targets, and the
  crosstalk qubit): settings, channels and their configs (including LO, mixer and
  TWPA), natives and calibration. Changing e.g. valid flux coefficients, the
  drive, drive12 or state-1 readout frequencies requires a new code. Changes to
  other qubits, including the flux crosstalk matrix, do not.
- Confirmations are recreated with every plan, and after every run.
- Parameters are validated by Qibocal *before* opening the `Executor` (which
  connects immediately).
- `update=False` by default; `update=True` only changes the platform in memory,
  for chaining. `$QIBOLAB_PLATFORMS` is never written: each run dumps
  `platform/` and `new_platform/` to its output folder, promoting is manual.
  Qibocal may store fitted values outside [-1, 1] (e.g. an RX12 amplitude from
  a poor `rabi_amplitude_ef` fit): the preflight then blocks routines using them.
- Each run uses a new folder `var/qw5q/<date>/<time>_<routine>_<targets>_<code>`;
  `force` is never used, nothing is deleted. It also holds `qw5q_run.json`, with
  plan, fingerprint, state digest, outcome, in-memory changes and environment
  (including dirty state). Routines run with that folder as working directory,
  since Qibocal's classifier fit writes `qubit<N>/` relative to it.
- The platform, and any instrument left connected by a failed connection, is
  disconnected at the end of every run, also on failures and interruptions
  (recorded as `interrupted`).
- Creating a Qibolab platform replaces the process SIGINT/SIGTERM handlers with
  one raising `RuntimeError`, which made marimo kernels impossible to interrupt or
  shut down (e.g. `marimo export` hung). The notebook keeps the host handlers, and
  during runs SIGTERM disconnects first, then delegates to the host handler.

## Qutrit support

| Routine                   | drive12 channel | RX12                                   |
| ------------------------- | --------------- | -------------------------------------- |
| `qubit_spectroscopy_ef`   | required        | not needed (bootstrap)                 |
| `rabi_amplitude_ef`       | required        | optional: without it, `pulse_length` is required (rectangular bootstrap pulse) |
| `dispersive_shift_qutrit` | required        | required                               |
| `qutrit_classification`   | required        | required                               |

On the stock `qw5q_platinum` all four are blocked (and a test asserts it):

- `qw5q_platinum/platform.py` builds qubits with `Qubit.default(i)`, so
  `drive_extra` is empty and no `{i}/drive12` channel or config exists;
- `RX12` is `null` for all five qubits, both at the pin and on platforms `main`.

The notebook does not create or patch channels.
Fix in `qibolab_platforms_qrc`: add `drive_extra[(1, 2)] = f"{i}/drive12"`
sharing the drive port, LO and mixer (as `qpu169/platform.py` does), plus
`{i}/drive12` IQ configs near `frequency_12` (already in `calibration.json`).

Not supported by Qibocal (`main` registry, 76 routines): EF coherence, with or
without flux. `t1`, `t2`, `ramsey`, `spin_echo`, `cpmg`, `zeno` and their
`_signal`/`_flux` variants only address the 0-1 transition. Routines driving 1-2
are `qubit_spectroscopy_ef`, `rabi_amplitude_ef` and `two_levels_crossing` (not
exposed here); `dispersive_shift_qutrit` and `qutrit_classification` prepare state
2 with RX12. The state-1 readout frequency is written by `dispersive_shift`.

## Known caveats

- `t1_flux`/`t2_flux` build a single sweep for all targets, which only covers the
  flux pulse of the last one: they run one qubit at a time.
- Their Qibocal plots fail if any single fit fails: the notebook plots raw P(1)
  maps and the successful fits itself.
- `t2_flux` applies no software detuning: fits close to zero detuning may fail.
- `flux_amplitude_frequency` also writes a flux crosstalk matrix element.

## Validation

Performed on 2026-10-16, offline only, on macOS 27.0.1 (arm64, Darwin 27.0.0)
with Python 3.13.15 and Qibo 0.3.6. **Linux and other Python versions were not
tested**, and `qw5q_constraints.txt` is a macOS freeze.

- `run/qw5q_env.bash` in a new directory, with an empty uv cache, inside
  `nix shell nixpkgs#uv nixpkgs#python313`: checked out the three verified
  commits and its final verification passed. Reruns: an unpinned planted package
  (`cowsay`) was removed and a downgraded pin (`tabulate` 0.9.0) restored; with
  an untracked file in a source checkout, the script stopped (exit 1) and left the
  file in place.
- `run/qw5q_validate.bash` in that environment: all steps passed, including 65
  tests (0 skipped) on Qibocal's `mock` platform and the stock `qw5q_platinum`.
  With a modified source file, it failed at the environment step. Without
  Qibocal, the tests fail at collection with an actionable message.
- Test coverage includes:
  - all 8 routines, with `update` on and off, through the real execution helper;
  - the RX12-absent bootstrap of `qubit_spectroscopy_ef` and `rabi_amplitude_ef`
    (rectangular RX12 stored on drive12), executed on the dummy instrument;
  - all qutrit plans blocked on the stock `qw5q_platinum`, without connections;
  - confirmation invalidated by changes to flux coefficients, drive, drive12 and
    state-1 readout frequencies; immutable plans;
  - crosstalk fixed amplitude preview, representability, channel and DC config
    checks; previewed amplitudes equal to the acquired sweeps;
  - nonce, reactive re-runs and gates, also replayed through the notebook cells
    (`app.run` with widget overrides);
  - amplitude end points, failed fits, interruption, SIGTERM, partial connection
    failures, working directory, run metadata, dirty checkouts, package pins and
    Python version checks.
- `marimo check --strict`: clean; dependency graph: 14 cells, no cycles.
- `marimo export html`, for `qw5q_platinum` (platforms `e77ac724`) and `mock`,
  with `qw5q_guard/` failing any `Platform.connect`, instrument `connect` or
  non-loopback socket: exit 0 in a few seconds, no output, no guard violation.
- `ruff check`, `ruff format --check` (ruff 0.17.1), `bash -n`, `shellcheck`
  0.11.0.

Not validated: browser interaction (clicks were replayed by overriding widget
values), real instruments, Qibocal HTML reports on hardware data, Linux, and
Python versions other than 3.13.15.

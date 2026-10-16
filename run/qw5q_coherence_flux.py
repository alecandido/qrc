import marimo

# marimo cells end with a bare output expression and `return`
# ruff: noqa: B018, PLR1711

__generated_with = "0.25.1"
app = marimo.App(width="medium", app_title="qw5q_platinum coherence vs flux")


@app.cell
def _():
    import sys
    from pathlib import Path

    import marimo as mo

    here = mo.notebook_dir() or Path(__file__).parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))

    import qw5q_helpers as h

    return h, here, mo


@app.cell
def _(h, mo):
    mo.md(
        f"""
        # `{h.PLATFORM}`: coherence vs flux and qutrit routines

        Opening this notebook, or editing any widget, **never** connects to the
        instruments: environment, platform and preflight are inspected offline.
        Hardware is only accessed after

        1. enabling hardware access,
        2. submitting a plan (immutable once submitted) and reviewing its preview,
        3. confirming the scan ranges and typing the plan confirmation code,
        4. clicking **Run on hardware**: each click runs at most once.

        Executions default to `update=False`. With `update=True`, fitted results
        only change the platform held in memory by this notebook (to chain
        routines): files in `$QIBOLAB_PLATFORMS` are never written, and promoting
        an output `new_platform/` folder is a manual step.
        Every run gets a fresh folder under `var/qw5q/`, nothing is overwritten,
        and the platform is disconnected at the end of each run.
        See `run/qw5q_calibration.md`.
        """
    )
    return


@app.cell
def _(mo):
    get_platform_version, set_platform_version = mo.state(0)
    get_run_count, set_run_count = mo.state(0)
    return get_platform_version, get_run_count, set_platform_version, set_run_count


@app.cell
def _(h, mo):
    components = h.check_environment()
    environment_ok = h.environment_verified(components)
    mo.vstack(
        [
            mo.md("## 1. Environment"),
            mo.callout(
                mo.md(
                    "All components match the verified revisions."
                    if environment_ok
                    else "**The environment differs from the verified revisions.** "
                    "Use `run/qw5q_env.bash`, or explicitly allow it when running."
                ),
                kind="success" if environment_ok else "warn",
            ),
            mo.ui.table(h.environment_rows(components), selection=None),
        ]
    )
    return (environment_ok,)


@app.cell
def _(h, mo):
    platform = None
    _error = None
    try:
        platform = h.load_platform()
    except Exception as _exc:  # noqa: BLE001
        _error = f"{type(_exc).__name__}: {_exc}"
    mo.stop(
        platform is None,
        mo.callout(
            mo.md(
                f"**Cannot load `{h.PLATFORM}` offline.**\n\n`{_error}`\n\n"
                "Check the environment above and `$QIBOLAB_PLATFORMS`."
            ),
            kind="danger",
        ),
    )
    mo.md(
        f"Platform `{platform.name}` loaded offline "
        f"(connected: `{platform.is_connected}`)."
    )
    return (platform,)


@app.cell
def _(h, here, platform):
    session = h.HardwareSession(platform, output_root=here.parent / "var" / "qw5q")
    return (session,)


@app.cell
def _(get_platform_version, h, mo, session):
    get_platform_version()
    checks = h.preflight(session.platform)
    mo.vstack(
        [
            mo.md(
                "## 2. Preflight (offline, in-memory platform)\n\n"
                "Refreshed after each run, so that in-memory updates are reflected."
            ),
            mo.ui.table(h.preflight_rows(checks), selection=None, page_size=20),
            mo.md("### Routine support"),
            mo.ui.table(h.support_rows(checks), selection=None),
            mo.accordion(
                {
                    "Calibration review": mo.md(
                        "- `t1_flux`/`t2_flux` convert amplitudes to frequency with "
                        "`flux_coefficients`: missing ones block them, suspicious ones "
                        "(e.g. non-negative curvature) are flagged for review.\n"
                        "- On platforms `e77ac724`, the q3/q4 coefficients are identical "
                        "to the February ones, although the sweetspots changed since: "
                        "consider re-running `flux_amplitude_frequency` first.\n"
                        "- Discrimination thresholds are required by the flux routines, "
                        "assignment fidelities are shown for review only."
                    ),
                    "Unsupported and bootstrap limitations": mo.md(
                        "\n".join(f"- {n}" for n in h.UNSUPPORTED)
                    ),
                }
            ),
        ]
    )
    return (checks,)


@app.cell
def _(h, mo):
    routine_picker = mo.ui.dropdown(
        {f"{r.group}: {r.name}": r.name for r in h.ROUTINES.values()},
        value=next(f"{r.group}: {r.name}" for r in h.ROUTINES.values()),
        label="Routine",
    )
    hardware_consent = mo.ui.switch(
        value=False, label="Enable hardware access for this session"
    )
    mo.vstack([mo.md("## 3. Action"), routine_picker, hardware_consent])
    return hardware_consent, routine_picker


@app.cell
def _(h, mo, routine_picker, session):
    _spec = h.ROUTINES[routine_picker.value]
    _qubits = {f"q{q}": q for q in session.platform.qubits}
    _elements = {
        "targets": mo.ui.multiselect(
            _qubits,
            label="Target qubits" + (" (one at a time)" if _spec.single_target else ""),
            max_selections=1 if _spec.single_target else None,
        )
    }
    for _f in (*_spec.fields, *h.COMMON_FIELDS):
        _label = f"{_f.label}" + (f" [{_f.unit}]" if _f.unit else "")
        if _f.kind == "qubit":
            _elements[_f.name] = mo.ui.dropdown(
                {"none": None} | _qubits, value="none", label=_label
            )
        else:
            _hint = "required" if _f.required else "optional"
            _elements[_f.name] = mo.ui.text(
                value=_f.default,
                placeholder=f"{_hint}{f', {_f.help}' if _f.help else ''}",
                label=_label,
            )
    _elements["update"] = mo.ui.checkbox(
        value=False,
        label="update=True: apply fitted results to the in-memory platform",
    )
    plan_form = mo.ui.dictionary(_elements).form(
        submit_button_label="Build plan (offline)", bordered=True
    )
    mo.vstack(
        [
            mo.md(f"### {_spec.title}"),
            mo.md(
                "No scan default is assumed safe: every range is entered and "
                "confirmed by the operator. Units are those of Qibocal (Hz, ns, a.u.)."
            ),
            plan_form,
        ]
    )
    return (plan_form,)


@app.cell
def _(checks, h, mo, plan_form, routine_picker, session):
    plan = None
    if plan_form.value is not None:
        _values = dict(plan_form.value)
        _targets = _values.pop("targets") or []
        _update = bool(_values.pop("update"))
        plan = h.build_plan(
            session.platform, routine_picker.value, _values, _targets, _update, checks
        )

    if plan is None:
        _out = mo.md("## 4. Plan preview\n\nSubmit the form to build a plan.")
    else:
        _items = [
            mo.md("## 4. Plan preview"),
            mo.ui.table(
                [{"item": k, "value": v} for k, v in plan.preview],
                selection=None,
                page_size=30,
            ),
        ]
        if plan.errors:
            _items.append(
                mo.callout(
                    mo.md("\n".join(f"- {e}" for e in plan.errors)),
                    kind="danger",
                    title="Errors: this plan cannot run",
                )
            )
        if plan.warnings:
            _items.append(
                mo.callout(
                    mo.md("\n".join(f"- {w}" for w in plan.warnings)),
                    kind="warn",
                    title="Warnings: acknowledge before running",
                )
            )
        if plan.overshoot:
            _items.append(
                mo.callout(
                    mo.md("\n".join(f"- {o}" for o in plan.overshoot)),
                    kind="danger",
                    title="Amplitudes beyond the declared bounds: blocked unless "
                    "explicitly accepted (or adjust the bounds)",
                )
            )
        if plan.ok:
            _items.append(mo.md(f"Confirmation code: **`{plan.fingerprint}`**"))
        _out = mo.vstack(_items)
    _out
    return (plan,)


@app.cell
def _(mo, plan):
    # recreated with every plan: confirmations never carry over
    _ = plan
    ranges_confirmed = mo.ui.checkbox(
        label="I confirm the previewed scan ranges and amplitudes are safe for this device"
    )
    warnings_reviewed = mo.ui.checkbox(label="I reviewed the plan warnings")
    overshoot_accepted = mo.ui.checkbox(
        label=(
            "I accept playing the amplitudes beyond the declared bounds listed above"
            if plan is not None and plan.overshoot
            else "No amplitude beyond the declared bounds"
        ),
        disabled=plan is None or not plan.overshoot,
    )
    confirmation = mo.ui.text(
        placeholder="confirmation code", label="Type the confirmation code"
    )
    allow_unverified = mo.ui.checkbox(
        label="Run despite an environment differing from the verified revisions"
    )
    write_report = mo.ui.checkbox(value=True, label="Write the Qibocal HTML report")
    mo.vstack(
        [
            mo.md("## 5. Confirmation"),
            ranges_confirmed,
            warnings_reviewed,
            overshoot_accepted,
            confirmation,
            allow_unverified,
            write_report,
        ]
    )
    return (
        allow_unverified,
        confirmation,
        overshoot_accepted,
        ranges_confirmed,
        warnings_reviewed,
        write_report,
    )


@app.cell
def _(mo):
    # independent of any other cell: its click counter is the run nonce
    run_button = mo.ui.button(
        value=0,
        on_click=lambda count: count + 1,
        label="Run on hardware",
        kind="danger",
    )
    return (run_button,)


@app.cell
def _(
    allow_unverified,
    confirmation,
    environment_ok,
    h,
    hardware_consent,
    mo,
    overshoot_accepted,
    plan,
    ranges_confirmed,
    run_button,
    session,
    set_platform_version,
    set_run_count,
    warnings_reviewed,
    write_report,
):
    _gate = h.Gate(
        hardware_consent=hardware_consent.value,
        ranges_confirmed=ranges_confirmed.value,
        confirmation=confirmation.value,
        warnings_reviewed=warnings_reviewed.value,
        overshoot_accepted=overshoot_accepted.value,
        allow_unverified_environment=allow_unverified.value,
    )
    _reasons = h.blocking_reasons(plan, _gate, environment_ok)
    _seen = len(session.records)
    _record = None
    try:
        _record = session.trigger(
            run_button.value, plan, _gate, environment_ok, report=write_report.value
        )
    finally:
        # also after interruptions, which are recorded before re-raising
        if len(session.records) > _seen:
            set_run_count(len(session.records))
            if session.records[-1].status != "blocked":
                # rebuild preflight and plan from the in-memory platform
                set_platform_version(len(session.records))

    if _record is not None and _record.status == "blocked":
        _status = mo.callout(
            mo.md("\n".join(f"- {r}" for r in _record.reasons)),
            kind="danger",
            title="Click ignored, nothing executed",
        )
    elif _reasons:
        _status = mo.callout(
            mo.md("\n".join(f"- {r}" for r in _reasons)),
            kind="neutral",
            title="Run disabled",
        )
    else:
        _status = mo.callout(
            mo.md(
                f"Clicking connects to `{plan.platform}` and runs `{plan.routine}` "
                f"on {', '.join(f'q{q}' for q in plan.targets)} once."
            ),
            kind="warn",
            title="Ready",
        )
    mo.vstack([mo.md("## 6. Run"), run_button, _status])
    return


@app.cell
def _(get_run_count, h, mo, session):
    get_run_count()
    _executed = [r for r in session.records if r.status != "blocked"]
    _history = [
        {
            "started": str(r.started),
            "routine": r.plan.routine,
            "targets": ", ".join(f"q{q}" for q in r.plan.targets),
            "update": r.plan.update,
            "status": r.status,
            "disconnected": r.disconnected,
            "changes": len(r.changes),
            "output": str(r.path),
        }
        for r in _executed
    ]
    if not _executed:
        _out = mo.md("## 7. Results\n\nNo action executed in this session.")
    else:
        _last = _executed[-1]
        _figures, _notes = h.record_figures(_last)
        _items = [
            mo.md("## 7. Results"),
            mo.ui.table(_history, selection=None),
            mo.md(
                f"### Last: `{_last.plan.routine}` ({_last.status})\n\n"
                f"Output folder: `{_last.path}`  \n"
                f"Disconnected: `{_last.disconnected}`  \n"
                + (f"Report: `{_last.report}`" if _last.report else "")
                + (
                    f"Report failed: `{_last.report_error}`"
                    if _last.report_error
                    else ""
                )
            ),
        ]
        if _last.error:
            _items.append(
                mo.callout(
                    mo.md(f"`{_last.error}`"),
                    kind="danger",
                    title="Execution failed",
                )
            )
        _items.append(
            mo.accordion(
                {
                    f"In-memory platform changes ({len(_last.changes)})": mo.md(
                        "Not written to `$QIBOLAB_PLATFORMS`; the output "
                        "`new_platform/` folder holds the updated copy.\n\n"
                        + "\n".join(f"- `{c}`" for c in _last.changes)
                    ),
                    **(
                        {"Traceback": mo.plain_text(_last.traceback)}
                        if _last.traceback
                        else {}
                    ),
                }
            )
        )
        _items += [mo.callout(mo.md(n), kind="warn") for n in _notes]
        _items += _figures
        _out = mo.vstack(_items)
    _out
    return


if __name__ == "__main__":
    app.run()

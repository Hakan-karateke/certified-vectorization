"""Gerçek Tk olay döngüsünde üç ürünlü pilot kayıt ve araştırma ekranı."""

import json
import time
import tkinter as tk
from pathlib import Path

import pytest

from sekilden_denkleme.gui import AnalysisWindow
from sekilden_denkleme.pilot import REQUIRED, load_study, summarize
from sekilden_denkleme.project import load_project

ROOT = Path(__file__).parents[1]


def test_pilot_desktop_records_three_products_saves_reopens_and_reports(tmp_path, monkeypatch):
    """Deneme verisi insan sonucu olmaz; ana model ve kaydedilmemiş veriler korunur."""
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(str(error))
    root.withdraw()
    app = AnalysisWindow(root)
    errors = []
    monkeypatch.setattr(
        "sekilden_denkleme.pilot_gui.messagebox.showerror", lambda *a, **k: errors.append(a)
    )
    monkeypatch.setattr("sekilden_denkleme.pilot_gui.messagebox.askyesno", lambda *a, **k: True)
    app.set_result(load_project(ROOT / "examples/cad_validation/ring/model.json"))
    original = app.result
    app.open_pilot()
    pilot = app.pilot_window

    def finish():
        deadline = time.monotonic() + 120
        ticks = [0]

        def tick():
            ticks[0] += 1
            if pilot.future is None or time.monotonic() > deadline:
                root.quit()
            else:
                root.after(10, tick)

        root.after(10, tick)
        root.mainloop()
        assert pilot.future is None and not errors, errors
        return ticks[0]

    try:
        pilot.start_timer()
        root.after(60, root.quit)
        root.mainloop()
        assert pilot.timer.elapsed() > 0
        pilot.timing.set("Elle ölçüm")
        assert pilot.timer.started is None
        pilot.fields["seconds"].set("1.5")
        root.after(300, root.quit)
        root.mainloop()
        assert pilot.fields["seconds"].get() == "1.5"
        for product in ("FreeCAD", "AutoCAD", "SolidWorks"):
            for key, value in {
                "participant": "TK-DEMO",
                "product": product,
                "product_version": "ui-test-only",
                "experience": "automated test",
                "baseline_method": "fixture",
                "case_id": "test-ring",
                "seconds": "1.5",
            }.items():
                pilot.fields[key].set(value)
            pilot.timing.set("Elle ölçüm")
            pilot.task_status.set("Tamamlandı")
            # Kalite kutularını işaretlemeden başarı kaydı eklenemez.
            pilot.record()
            assert errors and not any(t.product == product for t in pilot.study.trials)
            errors.clear()
            for key in REQUIRED["import"]:
                pilot.check_vars[key].set("Evet")
            pilot.record()
            root.update()
        assert len(pilot.study.trials) == 3
        assert summarize(pilot.study)["human_participants"] == 0
        assert app.result is original
        app.close()
        assert not app.closed and pilot.dirty
        saved = tmp_path / "pilot.json"
        monkeypatch.setattr(
            "sekilden_denkleme.pilot_gui.filedialog.asksaveasfilename", lambda **k: str(saved)
        )
        pilot.save()
        assert finish() > 0 and saved.exists() and not pilot.dirty
        assert len(load_study(saved).trials) == 3
        pilot.tree.selection_set(pilot.study.trials[0].id)
        root.update()
        assert pilot.editing_id == pilot.study.trials[0].id
        pilot.notes.insert("end", "field change")
        root.update()
        assert pilot.form_dirty
        pilot.record()
        root.update()
        assert len(pilot.study.trials) == 3
        pilot.save()
        finish()
        monkeypatch.setattr(
            "sekilden_denkleme.pilot_gui.filedialog.askopenfilename", lambda **k: str(saved)
        )
        pilot.open()
        finish()
        monkeypatch.setattr(
            "sekilden_denkleme.pilot_gui.filedialog.askdirectory",
            lambda **k: str(tmp_path / "report"),
        )
        pilot.export()
        finish()
        assert (tmp_path / "report/pilot.html").exists()
        pilot.report_current()
        finish()
        assert (tmp_path / "report/model-comparison.html").exists()
        assert app.result is original
    finally:
        pilot.close(force=True)
        app.close()


def test_pilot_desktop_freecad_real_background_product_check(tmp_path, monkeypatch):
    """Gerçek FreeCAD süreci ve Tk olay döngüsü birlikte çalışır; insan kaydı oluşmaz."""
    commands = list((ROOT / ".tmp/freecad").glob("*/bin/freecadcmd.exe"))
    if not commands:
        pytest.skip("Ayrı FreeCADCmd kurulu değil.")
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(str(error))
    root.withdraw()
    app = AnalysisWindow(root)
    app.open_pilot()
    pilot = app.pilot_window
    errors = []
    monkeypatch.setattr(
        "sekilden_denkleme.pilot_gui.messagebox.showerror", lambda *a, **k: errors.append(a)
    )
    try:
        pilot.freecad_path.set(str(commands[0]))
        pilot.cad_path.set(str(ROOT / "examples/cad_validation/ring/reconstruction.step"))
        monkeypatch.setattr(
            "sekilden_denkleme.pilot_gui.filedialog.askdirectory", lambda **k: str(tmp_path)
        )
        pilot.run_compatibility()
        ticks = [0]
        deadline = time.monotonic() + 120

        def tick():
            ticks[0] += 1
            if pilot.future is None or time.monotonic() > deadline:
                root.quit()
            else:
                root.after(10, tick)

        root.after(10, tick)
        root.mainloop()
        assert not errors and pilot.future is None and ticks[0] > 1
        report = next(tmp_path.glob("freecad-*/compatibility.json"))
        assert json.loads(report.read_text())["evaluation"]["status"] == "passed"
        assert "passed" in pilot.status.get() and not pilot.study.trials
    finally:
        pilot.close(force=True)
        app.close()


def test_program_preparation_persistence_and_two_consecutive_cancellations(tmp_path, monkeypatch):
    """Kaydedilmemiş ayarlar/katılımcı onayı korunur; iptal düğmesi her yeni işte çalışır."""
    from sekilden_denkleme.cad_setup import load_programs
    from sekilden_denkleme.fitting import AnalysisCancelled

    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(str(error))
    root.withdraw()
    app = AnalysisWindow(root)
    app.open_pilot()
    pilot = app.pilot_window
    prep = pilot.preparation
    prep.settings_path = tmp_path / "programs.json"
    errors = []
    monkeypatch.setattr(
        "sekilden_denkleme.pilot_gui.messagebox.showerror", lambda *a, **k: errors.append(a)
    )
    monkeypatch.setattr("sekilden_denkleme.pilot_gui.messagebox.askyesno", lambda *a, **k: False)

    def finish():
        deadline = time.monotonic() + 15

        def tick():
            if pilot.future is None or time.monotonic() > deadline:
                root.quit()
            else:
                root.after(10, tick)

        root.after(10, tick)
        root.mainloop()
        assert pilot.future is None and not errors, errors

    try:
        exe = tmp_path / "acad.exe"
        exe.write_bytes(b"path fixture only")
        prep.paths["AutoCAD"].set(str(exe))
        prep.versions["AutoCAD"].set("test-fixture")
        prep.confirmed["AutoCAD"].set(True)
        assert prep.dirty
        pilot.close()
        assert not pilot.closed
        prep.save()
        finish()
        assert not prep.dirty
        assert load_programs(prep.settings_path).programs["AutoCAD"].first_launch_confirmed
        prep.paths["AutoCAD"].set(str(tmp_path / "other/acad.exe"))
        assert not prep.confirmed["AutoCAD"].get() and not prep.versions["AutoCAD"].get()
        pilot.fields["participant"].set("person-a")
        pilot.consent.set(True)
        pilot.fields["participant"].set("person-b")
        assert not pilot.consent.get()
        events = []

        def worker():
            current = pilot.cancel_event
            events.append(current)
            if not current.wait(5):
                raise RuntimeError("Cancel button did not signal running job")
            raise AnalysisCancelled("cancel regression confirmed")

        for _ in range(2):
            pilot.job(worker, cancellable=True)
            root.after(50, pilot.cancel_button.invoke)
            finish()
            assert events[-1].is_set() and "cancel regression confirmed" in pilot.status.get()
        assert events[0] is not events[1]
        assert not pilot.study.trials
    finally:
        pilot.close(force=True)
        app.close()


def test_desktop_builds_nine_cad_files_loads_plan_and_applies_unknown_quality_task(
    tmp_path, monkeypatch
):
    """Gerçek Tk paket üretimi/yeniden açma/form akışı; sahte insan/süre/başarı oluşturmaz."""
    from sekilden_denkleme.cad import available_formats
    from sekilden_denkleme.pilot_pack import load_pack

    if not all(available_formats().values()):
        pytest.skip("CAD ekleri kurulu değil.")
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(str(error))
    root.withdraw()
    app = AnalysisWindow(root)
    app.open_pilot()
    pilot = app.pilot_window
    prep = pilot.preparation
    errors = []
    monkeypatch.setattr(
        "sekilden_denkleme.pilot_gui.messagebox.showerror", lambda *a, **k: errors.append(a)
    )
    monkeypatch.setattr("sekilden_denkleme.pilot_gui.messagebox.askyesno", lambda *a, **k: True)
    monkeypatch.setattr(
        "sekilden_denkleme.pilot_preparation_gui.filedialog.askdirectory", lambda **k: str(tmp_path)
    )

    def finish():
        ticks = [0]
        deadline = time.monotonic() + 120

        def tick():
            ticks[0] += 1
            if pilot.future is None or time.monotonic() > deadline:
                root.quit()
            else:
                root.after(10, tick)

        root.after(10, tick)
        root.mainloop()
        assert pilot.future is None and not errors, errors
        return ticks[0]

    try:
        prep.build()
        assert finish() > 5
        path = prep.plan_path
        assert path and len(prep.tasks.get_children()) == 54
        assert len(load_pack(path)["assets"]) == 34
        monkeypatch.setattr(
            "sekilden_denkleme.pilot_preparation_gui.filedialog.askopenfilename",
            lambda **k: str(path),
        )
        prep.open_plan()
        finish()
        pilot.fields["participant"].set("UI-DEMO")
        pilot.fields["baseline_method"].set("test-only workflow")
        for product in ("FreeCAD", "AutoCAD", "SolidWorks"):
            prep.versions[product].set("ui-test-only")
            for method in ("generated", "baseline"):
                task = next(
                    t
                    for t in prep.plan["tasks"]
                    if t["product"] == product
                    and t["method"] == method
                    and t["case"] == "ring"
                    and t["task"] == "edit"
                )
                prep.tasks.selection_set(task["id"])
                root.update()
                prep.apply_task()
                finish()
                assert pilot.fields["product"].get() == product
                assert pilot.fields["seconds"].get() == "0" and pilot.timer.started is None
                assert pilot.fields["participant"].get() == "UI-DEMO"
                assert pilot.kind.get().startswith("Eğitim") and not pilot.consent.get()
                assert all(v.get() == "Bilinmiyor" for v in pilot.check_vars.values())
                assert pilot.task_status.get() == "Başarısız"
                assert "yarıçap" in pilot.required_hint.get()
                assert not pilot.study.trials and pilot.evidence == {}
        old_plan = prep.plan
        (path.parent / "ring/reconstruction.dxf").write_bytes(b"corrupt")
        prep.open_plan()
        deadline = time.monotonic() + 30
        while pilot.future is not None and time.monotonic() < deadline:
            root.update()
            time.sleep(0.01)
        assert errors and prep.plan is old_plan and not pilot.study.trials
    finally:
        pilot.close(force=True)
        app.close()

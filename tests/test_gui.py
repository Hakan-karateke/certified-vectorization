"""Gerçek Tk olay döngüsünde temel masaüstü kabul akışı (ekran varsa)."""

import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import pytest
from PIL import Image

from sekilden_denkleme.gui import VIEWS, AnalysisWindow


def test_desktop_end_to_end_preview_cancel_save_reopen_and_export(tmp_path, monkeypatch):
    """Gerçek widget komutlarını çalıştırır; sistem dosya kutularını deterministik seçer."""
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk ekranı kullanılamıyor: {error}")
    root.withdraw()
    app = AnalysisWindow(root)
    errors = []
    monkeypatch.setattr(
        "sekilden_denkleme.gui.messagebox.showerror", lambda *args, **kwargs: errors.append(args)
    )

    def finish():
        """Pencerenin gerçekten yanıt verdiği olay döngüsünde işi bekler."""
        deadline = time.monotonic() + 90
        ticks = 0

        def tick():
            nonlocal ticks
            ticks += 1
            if app.future is None or time.monotonic() >= deadline:
                root.quit()
            else:
                root.after(10, tick)

        root.after(10, tick)
        root.mainloop()
        root.update()
        assert app.future is None, "Masaüstü işi zamanında tamamlanmadı."
        assert not errors, errors
        return ticks

    try:
        image = tmp_path / "square.png"
        Image.new("L", (100, 100), 0).save(image)
        monkeypatch.setattr(
            "sekilden_denkleme.gui.filedialog.askopenfilename", lambda **_: str(image)
        )
        app.choose_image()
        assert finish() > 0
        assert "Ön izleme" in app.status.get()
        app.family.set("Kesin piksel sınırı")
        app.search.set("Bütçeli simüle tavlama")
        app.search_budget.set("4")
        app.seed.set("17")
        app.workers.set("2")
        app.certificate.set("Sertifikalı sonuç zorunlu")
        app.run()
        finish()
        assert app.result is not None
        assert app.result.config.search_strategy == "annealing"
        assert app.result.config.evaluation_workers == 2
        assert app.result.selected.metrics["certification"]["status"] == "proven"
        assert len(app.piece_tree.get_children()) == 4
        for view in VIEWS:
            app.view.set(view)
            app.draw()
        app.piece_tree.selection_set("0")
        app.inspect_piece()
        assert "r(t)" in app.piece_detail.get("1.0", "end")
        project = tmp_path / "saved.json"
        monkeypatch.setattr(
            "sekilden_denkleme.gui.filedialog.asksaveasfilename", lambda **_: str(project)
        )
        app.save_project_dialog()
        finish()
        assert project.is_file()
        original = app.result
        app.run()
        app.cancel()
        finish()
        assert app.result is original
        monkeypatch.setattr(
            "sekilden_denkleme.gui.filedialog.askopenfilename", lambda **_: str(project)
        )
        app.open_project()
        finish()
        assert app.result.selected_id == original.selected_id
        assert app.seed.get() == "17" and app.search_budget.get() == "4"
        assert app.workers.get() == "2"
        app.candidate_tree.selection_set(app.result.selected_id)
        app.use_candidate()
        assert app.future is not None
        assert finish() > 0
        assert "Kullanıcı" in app.result.provenance["selection_reason"]
        output = tmp_path / "exports"
        monkeypatch.setattr(
            "sekilden_denkleme.gui.filedialog.askdirectory", lambda **_: str(output)
        )
        app.save()
        dialogs = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
        assert len(dialogs) == 1

        def descendants(widget):
            """Kayıt düğmesini gerçek widget ağacından bulur."""
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)

        button = next(
            w
            for w in descendants(dialogs[0])
            if isinstance(w, ttk.Button) and w.cget("text") == "Seçilen çıktıları kaydet"
        )
        button.invoke()
        finish()
        assert {p.suffix for p in Path(output).iterdir()} == {
            ".pdf",
            ".png",
            ".jpg",
            ".svg",
            ".json",
            ".txt",
        }
        assert "doğrulandı" in app.status.get()
        # Veri taraması mevcut modele dokunmadan aynı arka plan/iptal kanalını kullanır.
        manifest = tmp_path / "manifest.json"
        model_before_stress = app.result
        monkeypatch.setattr(
            "sekilden_denkleme.gui.filedialog.askopenfilename", lambda **_: str(manifest)
        )

        def grid(manifest_path, directory, *, cancel, progress):
            assert manifest_path == str(manifest) and directory == str(output)
            assert cancel is app.cancel_event
            progress("1/1 test taraması")
            return output / "results.json"

        monkeypatch.setattr("sekilden_denkleme.stress.run_grid", grid)
        app.run_stress()
        assert app.future is not None
        assert finish() > 0
        assert app.result is model_before_stress
    finally:
        app.close()


def test_desktop_cad_dialog_exports_three_real_formats_and_preserves_model(tmp_path, monkeypatch):
    """Gerçek Tk CAD kutusundan üç dosyayı fiziksel birimle, arayüzü kilitlemeden yazar."""
    import json

    from sekilden_denkleme import analyze
    from sekilden_denkleme.cad import available_formats

    if not all(available_formats().values()):
        pytest.skip("CAD eklentisi kurulu değil.")
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(str(error))
    root.withdraw()
    app = AnalysisWindow(root)
    errors = []
    monkeypatch.setattr(
        "sekilden_denkleme.gui.messagebox.showerror", lambda *a, **k: errors.append(a)
    )
    monkeypatch.setattr("sekilden_denkleme.gui.filedialog.askdirectory", lambda **_: str(tmp_path))

    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)

    try:
        result = analyze(Path(__file__).parents[1] / "examples/square.png")
        app.set_result(result)
        app.cad_button.invoke()
        dialog = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
        children = list(descendants(dialog))
        combo = next(w for w in children if isinstance(w, ttk.Combobox))
        combo.set("cm")
        entries = [
            w for w in children if isinstance(w, ttk.Entry) and not isinstance(w, ttk.Combobox)
        ]
        entries[0].delete(0, "end")
        entries[0].insert(0, "0.1")
        button = next(
            w
            for w in children
            if isinstance(w, ttk.Button) and w.cget("text") == "Seçilen CAD biçimlerini kaydet"
        )
        button.invoke()
        assert app.future is not None and str(app.cad_button.cget("state")) == "disabled"
        deadline = time.monotonic() + 90
        ticks = 0

        def tick():
            nonlocal ticks
            ticks += 1
            if app.future is None or time.monotonic() > deadline:
                root.quit()
            else:
                root.after(10, tick)

        root.after(10, tick)
        root.mainloop()
        assert app.future is None and ticks > 0
        assert not errors, errors
        assert app.result is result
        for kind in ["step", "iges", "dxf"]:
            path = tmp_path / f"reconstruction.{kind}"
            assert path.is_file()
            metadata = json.loads(
                path.with_name(path.name + ".cad.json").read_text(encoding="utf8")
            )
            assert (
                metadata["cad_options"]["unit"] == "cm" and metadata["cad_options"]["scale"] == 0.1
            )
        assert "doğrulandı" in app.status.get()
    finally:
        app.close()

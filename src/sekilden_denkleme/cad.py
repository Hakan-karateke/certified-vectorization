"""CAD dosyası ve denklem eşleme kaydını doğrulayıp birlikte güvenle yayımlar."""

import hashlib
import importlib.util
import json
import os
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path
from threading import RLock

from .cad_geometry import CadOptions, prepare_geometry, validate_roundtrip
from .curves import equation
from .models import AnalysisResult

CAD_LOCK = RLock()
CAD_FORMATS = ("dxf", "step", "iges")


def available_formats() -> dict[str, bool]:
    """Ağır CAD kütüphanelerini yüklemeden kurulmuş biçim desteğini sorgular."""
    return {
        "dxf": importlib.util.find_spec("ezdxf") is not None,
        "step": importlib.util.find_spec("OCP") is not None,
        "iges": importlib.util.find_spec("OCP") is not None,
    }


def export_cad(
    result: AnalysisResult, path: str | Path, kind: str, options: CadOptions | None = None
) -> Path:
    """Gerçek CAD dosyasını yeniden açar; CAD+JSON çifti başarısızsa hedefleri korur.

    Eşlik eden .cad.json denklemleri, asıl katsayı/aralıkları, fiziksel eşlemeyi,
    kaynak ve aktarım denetimlerinin ayrı kapsamlarını içerir. OCCT birim ayarları
    süreç genelinde olduğundan bütün CAD işlemi tek kilit altında yürütülür.
    """
    if kind not in CAD_FORMATS:
        raise ValueError("CAD biçimi dxf, step veya iges olmalıdır.")
    if not available_formats()[kind]:
        raise ValueError(
            "CAD desteği kurulu değil. kur_cad_windows.cmd ile CAD eklentisini kurun; teknik kurulum: pip install -e '.[cad]'."
        )
    options = options or CadOptions()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sidecar = path.with_name(path.name + ".cad.json")
    with CAD_LOCK, tempfile.TemporaryDirectory(prefix=".cad-", dir=path.parent) as work:
        work = Path(work)
        temp = work / path.name
        meta = work / sidecar.name
        curves, reference = prepare_geometry(result, options)
        if kind == "dxf":
            from .cad_dxf import read_dxf, write_dxf

            mapping = write_dxf(curves, temp, options)
            rings, reader = read_dxf(temp, options)
        else:
            from .cad_occt import read_occt, write_occt

            mapping = write_occt(curves, temp, kind, options, reference)
            rings, reader = read_occt(temp, kind, options)
        if not temp.is_file() or not temp.stat().st_size:
            raise OSError("CAD dosyası boş.")
        validation = validate_roundtrip(reference, rings, options, reader["max_join_gap"])
        proof = result.selected.metrics.get("certification", {})
        source_upper = (
            proof.get("hausdorff_upper_bound") if proof.get("status") == "proven" else None
        )
        metadata = {
            "schema_version": "1.0",
            "application_version": result.to_dict()["application_version"],
            "format": kind,
            "cad_file": path.name,
            "cad_sha256": hashlib.sha256(temp.read_bytes()).hexdigest(),
            "cad_options": asdict(options),
            "coordinate_contract": {
                "plane": "XY; z=0",
                "axis": "x_right_y_up",
                "mapping": "CAD coordinates = working coordinates * scale; origin unchanged",
                "physical_calibration": "user_assigned_scale_not_inferred_from_image",
            },
            "representation": "DXF: grouped planar curves; STEP/IGES: planar faces with hole wires; no solids or native dimensional constraint/history tree",
            "orientation_contract": "STEP/IGES face normal +Z, outer wires CCW and hole wires CW; source traversal remains in selected_model, face reversals in entity_mapping. Readers may reparameterize native curves.",
            "selected_model": {
                "id": result.selected.id,
                "family": result.selected.family,
                "pieces": [asdict(p) for p in result.selected.pieces],
                "equations": [equation(p) for p in result.selected.pieces],
                "complexity": result.selected.complexity,
                "metrics": result.selected.metrics,
            },
            "topology": result.topology,
            "normalization": result.normalization,
            "source": {
                "sha256": result.provenance.get("source_sha256"),
                "path": result.provenance.get("source_path"),
            },
            "implicit_polynomial": asdict(result.polynomial) if result.polynomial else None,
            "entity_mapping": mapping,
            "native_curves": [asdict(c) for c in curves],
            "cad_complexity": {
                "native_curve_count": len(curves),
                "native_control_points": sum(len(c.params.get("controls", [])) for c in curves),
                "polyline_vertices": sum(len(c.params.get("points", [])) for c in curves),
                "reader_edge_or_entity_count": reader.get("edge_count", reader.get("entity_count")),
                "cad_file_bytes": temp.stat().st_size,
                "source_model_score_bits": result.selected.complexity.get("score_bits"),
            },
            "approximated_source_pieces": sorted(
                {c.source_piece for c in curves if c.kind == "polyline"}
            ),
            "reader": reader,
            "transfer_validation": validation,
            "physical_error_summary": {
                "unit": options.unit,
                "source_verified_upper_scaled": source_upper * options.scale
                if source_upper is not None
                else None,
                "cad_transfer_upper_estimate": validation["transfer_upper_estimate"],
                "combined_pixel_boundary_upper_estimate": source_upper * options.scale
                + validation["transfer_upper_estimate"]
                if source_upper is not None
                else None,
                "combined_verified_numerical_certificate": False,
                "ideal_object_error_known": False,
            },
            "original_model_certificate_scope": "source model and normalized pixel reference; does not certify the CAD file",
        }
        meta.write_text(
            json.dumps(metadata, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf8"
        )
        if (
            json.loads(meta.read_text(encoding="utf8"))["cad_sha256"]
            != hashlib.sha256(temp.read_bytes()).hexdigest()
        ):
            raise ValueError("CAD eşleme kaydı hash doğrulamasını geçemedi.")
        targets = [(temp, path), (meta, sidecar)]
        backups = {}
        for _, target in targets:
            if target.exists():
                backup = work / (target.name + ".backup")
                shutil.copy2(target, backup)
                backups[target] = backup
        replaced = []
        try:
            for source, target in targets:
                os.replace(source, target)
                replaced.append(target)
        except OSError:
            for target in reversed(replaced):
                if target in backups:
                    os.replace(backups[target], target)
                else:
                    target.unlink(missing_ok=True)
            raise
    return path

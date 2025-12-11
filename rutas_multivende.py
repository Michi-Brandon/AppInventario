"""Resuelve rutas base, de archivos y de salidas (Movimientos/Etiquetas)."""

from __future__ import annotations

import os
from typing import Dict


def resolver_rutas_multivende(config: Dict[str, str]) -> Dict[str, str]:
    """
    Devuelve las rutas relevantes para multivende:
    - archivos: donde se leen los Excel descargados.
    - base: carpeta padre para salidas (Movimientos/Etiquetas).
    Permite que config["carpeta_multivende"] apunte a "Archivos" sin anidar las salidas.
    """
    raw_dir = (config.get("carpeta_multivende") or "").strip()
    base_override = (config.get("carpeta_multivende_base") or "").strip()
    archivos_override = (config.get("carpeta_multivende_archivos") or "").strip()

    base_dir = os.path.normpath(base_override) if base_override else ""
    archivos_dir = os.path.normpath(archivos_override) if archivos_override else ""

    if not archivos_dir:
        archivos_dir = os.path.normpath(raw_dir) if raw_dir else ""

    if not base_dir:
        base_dir = os.path.normpath(raw_dir) if raw_dir else ""

    # Si el path de archivos termina en "Archivos" y no hay override para base,
    # usa la carpeta padre para Movimientos/Etiquetas.
    if archivos_dir and not base_override:
        nombre_final = os.path.basename(archivos_dir).lower()
        if nombre_final == "archivos":
            base_dir = os.path.dirname(archivos_dir) or archivos_dir

    if not base_dir and archivos_dir:
        base_dir = os.path.dirname(archivos_dir) or archivos_dir

    movimientos_dir = os.path.join(base_dir, "Movimientos") if base_dir else ""
    etiquetas_dir = os.path.join(base_dir, "Etiquetas") if base_dir else ""

    return {
        "base": base_dir,
        "archivos": archivos_dir,
        "movimientos": movimientos_dir,
        "movimientos_excel": os.path.join(movimientos_dir, "movimientos.xlsx") if movimientos_dir else "",
        "etiquetas": etiquetas_dir,
        "registro_impresiones": os.path.join(etiquetas_dir, "registro_impresiones.xlsx") if etiquetas_dir else "",
    }

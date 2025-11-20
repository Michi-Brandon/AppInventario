"""
Cliente simple para Zipnova:
- Busca envíos por external_id.
- Busca envíos por nombre de destinatario (recorriendo páginas).
- Descarga etiquetas/documentación en formato ZPL (body en base64).

Requiere variables en .env (mismo archivo que usa ml_api_client):
    ZIPNOVA_API_TOKEN
    ZIPNOVA_API_SECRET
Opcionales:
    ZIPNOVA_API_DOMAIN   (por defecto zipnova.cl)
    ZIPNOVA_ACCOUNT_ID   (para acotar búsqueda)
    ZIPNOVA_ORIGIN_ID    (para acotar búsqueda)
"""

from __future__ import annotations

import base64
import os
from typing import Any, Dict, Iterable, Tuple

import requests

from ml_api_client import ensure_keys, load_env


class ZipnovaAPIError(RuntimeError):
    """Errores de uso de la API de Zipnova."""


def _load_zipnova_env(env_path: str | None = None) -> Tuple[Dict[str, str], str]:
    # Capturamos también SystemExit que puede lanzar ensure_keys para evitar cerrar la app.
    try:
        env = load_env(env_path)
        ensure_keys(env, ["ZIPNOVA_API_TOKEN", "ZIPNOVA_API_SECRET"])
    except BaseException as exc:  # noqa: BLE001, B036
        raise ZipnovaAPIError(f"Error leyendo credenciales Zipnova: {exc}") from exc
    domain = env.get("ZIPNOVA_API_DOMAIN", "zipnova.cl")
    return env, domain


def _build_session(env: Dict[str, str]) -> requests.Session:
    session = requests.Session()
    session.auth = (env["ZIPNOVA_API_TOKEN"], env["ZIPNOVA_API_SECRET"])
    session.headers.update({"Accept": "application/json"})
    return session


def _guardar_en_descargas(nombre: str, contenido: bytes, fmt: str, file_name: str | None = None) -> str:
  downloads = os.path.join(os.path.expanduser("~"), "Downloads")
  os.makedirs(downloads, exist_ok=True)
  etiqueta = file_name or nombre
  nombre_archivo = f"label_{etiqueta}.{fmt}"
  ruta = os.path.join(downloads, nombre_archivo)
  with open(ruta, "wb") as fh:
    fh.write(contenido)
    return ruta


def _descargar_label(
    session: requests.Session, base_url: str, shipment_id: int, fmt: str = "zpl"
) -> bytes:
    resp = session.get(
        f"{base_url}/shipments/{shipment_id}/documentation",
        params={"what": "label", "format": fmt},
        timeout=30,
    )
    try:
        resp.raise_for_status()
    except requests.RequestException as exc:  # noqa: BLE001
        raise ZipnovaAPIError(f"Error al descargar documentación de Zipnova: {exc}") from exc
    body = resp.json()
    label_b64 = body.get("body")
    if not label_b64:
        raise ZipnovaAPIError("La respuesta no contiene 'body' con el archivo en base64.")
    try:
        return base64.b64decode(label_b64)
    except Exception as exc:  # noqa: BLE001
        raise ZipnovaAPIError(f"Error decodificando base64: {exc}") from exc


def _filtra_por_tokens(texto: str, tokens: Iterable[str]) -> bool:
    texto_l = (texto or "").lower()
    return all(tok in texto_l for tok in tokens)


def buscar_envio_por_external_id(external_id: str, env_path: str | None = None) -> Dict[str, Any]:
    env, domain = _load_zipnova_env(env_path)
    session = _build_session(env)
    base_url = f"https://api.{domain}/v2"

    params: Dict[str, Any] = {"external_id": external_id}
    if env.get("ZIPNOVA_ACCOUNT_ID"):
        params["account_id"] = env["ZIPNOVA_ACCOUNT_ID"]
    if env.get("ZIPNOVA_ORIGIN_ID"):
        params["origin_id"] = env["ZIPNOVA_ORIGIN_ID"]

    try:
        resp = session.get(f"{base_url}/shipments", params=params, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:  # noqa: BLE001
        raise ZipnovaAPIError(f"Error consultando envíos Zipnova: {exc}") from exc
    data = resp.json().get("data", [])
    if not data:
        raise ZipnovaAPIError(f"No se encontraron envíos con external_id={external_id}")
    envio = data[0]
    envio["_session"] = session
    envio["_base_url"] = base_url
    return envio


def buscar_envio_por_nombre(
    nombre_cliente: str, env_path: str | None = None, max_pages: int = 5, per_page: int = 50
) -> Dict[str, Any]:
    tokens = [t.lower() for t in nombre_cliente.strip().split() if t]
    if not tokens:
        raise ZipnovaAPIError("Nombre de cliente vacío para búsqueda en Zipnova.")

    env, domain = _load_zipnova_env(env_path)
    session = _build_session(env)
    base_url = f"https://api.{domain}/v2"

    params_base: Dict[str, Any] = {}
    if env.get("ZIPNOVA_ACCOUNT_ID"):
        params_base["account_id"] = env["ZIPNOVA_ACCOUNT_ID"]
    if env.get("ZIPNOVA_ORIGIN_ID"):
        params_base["origin_id"] = env["ZIPNOVA_ORIGIN_ID"]

    for page in range(1, max_pages + 1):
        params = dict(params_base)
        params.update({"page": page, "per_page": per_page})
        try:
            resp = session.get(f"{base_url}/shipments", params=params, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:  # noqa: BLE001
            raise ZipnovaAPIError(f"Error consultando envíos Zipnova: {exc}") from exc
        body = resp.json()
        for envio in body.get("data", []):
            dest_name = (envio.get("destination") or {}).get("name", "")
            if _filtra_por_tokens(dest_name, tokens):
                envio["_session"] = session
                envio["_base_url"] = base_url
                return envio

        links = body.get("links") or {}
        if not links.get("next"):
            break

    raise ZipnovaAPIError(f"No se encontraron envíos para cliente '{nombre_cliente}'.")


def descargar_etiqueta_zipnova_por_external_id(
    external_id: str, fmt: str = "zpl", env_path: str | None = None, file_name: str | None = None
) -> str:
  envio = buscar_envio_por_external_id(external_id, env_path=env_path)
  session: requests.Session = envio.pop("_session")
  base_url: str = envio.pop("_base_url")
  label = _descargar_label(session, base_url, int(envio["id"]), fmt=fmt)
  return _guardar_en_descargas(external_id, label, fmt, file_name=file_name)


def descargar_etiqueta_zipnova_por_nombre(
    nombre_cliente: str, fmt: str = "zpl", env_path: str | None = None, file_name: str | None = None
) -> str:
  envio = buscar_envio_por_nombre(nombre_cliente, env_path=env_path)
  session: requests.Session = envio.pop("_session")
  base_url: str = envio.pop("_base_url")
  external_id = envio.get("external_id") or str(envio.get("id"))
  label = _descargar_label(session, base_url, int(envio["id"]), fmt=fmt)
  return _guardar_en_descargas(external_id, label, fmt, file_name=file_name)

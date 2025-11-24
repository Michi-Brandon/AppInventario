"""
Cliente ligero para descargar etiquetas ZPL desde Envíame.

Soporta:
- Descarga por delivery_id único (ej: Paris / Ripley) usando /s2/v2/deliveries/{id}.
- Descarga por número de envío (shipping_number/imported_id) listando los envíos del seller
  y bajando cada etiqueta asociada (ej: Walmart multibulto).

Variables esperadas en .env (una por canal, con fallback a ENVIAME_API_KEY):
  ENVIAME_API_KEY_WALMART
  ENVIAME_API_KEY_PARIS
  ENVIAME_API_KEY_RIPLEY
  ENVIAME_API_KEY           # fallback común
  ENVIAME_SELLER_ID        # requerido para listar deliveries
Opcionales:
  ENVIAME_API_BASE         # default https://api.enviame.io/api
  ENVIAME_LABEL_OUTPUT_DIR # default ~/Downloads
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


ENV_FILENAME = ".env"


def _base_path() -> Path:
  if getattr(sys, "frozen", False):
    return Path(sys.executable).parent
  return Path(__file__).resolve().parent


def load_env(path: Optional[str] = None) -> Dict[str, str]:
  env_path = Path(path) if path else _base_path() / ENV_FILENAME
  env: Dict[str, str] = {}
  if env_path.exists():
    with open(env_path, "r", encoding="utf-8") as fh:
      for line in fh:
        striped = line.strip()
        if not striped or striped.startswith("#") or "=" not in striped:
          continue
        key, val = striped.split("=", 1)
        env[key.strip()] = val.strip().strip('"').strip("'")
  return env


def ensure_keys(env: Dict[str, str], keys: List[str]) -> None:
  missing = [k for k in keys if not env.get(k)]
  if missing:
    raise RuntimeError(f"Faltan variables en .env: {', '.join(missing)}")


def http_get(url: str, headers: Optional[Dict[str, str]] = None) -> str:
  req = Request(url, headers=headers or {})
  try:
    with urlopen(req, timeout=60) as resp:
      return resp.read().decode("utf-8")
  except HTTPError as err:
    details = err.read().decode("utf-8", errors="ignore")
    raise RuntimeError(f"Error {err.code} al llamar {url} -> {details}") from err
  except URLError as err:
    raise RuntimeError(f"No se pudo conectar a {url}: {err}") from err


def _classify_zpl(zpl_value: Any) -> Dict[str, str] | None:
  if not zpl_value:
    return None
  if isinstance(zpl_value, str):
    trimmed = zpl_value.strip()
    return {"raw": trimmed} if trimmed.startswith("^XA") else {"url": trimmed}
  if isinstance(zpl_value, dict):
    raw = zpl_value.get("raw")
    url = zpl_value.get("url") or zpl_value.get("href")
    result: Dict[str, str] = {}
    if isinstance(raw, str) and raw.strip():
      result["raw"] = raw.strip()
    if isinstance(url, str) and url.strip():
      result["url"] = url.strip()
    return result or None
  return None


def _download_zpl_from_source(source: Dict[str, str]) -> Dict[str, str]:
  if source.get("raw"):
    return {"content": source["raw"], "origin": "raw"}
  if source.get("url"):
    content = http_get(source["url"])
    return {"content": content, "origin": source["url"]}
  raise RuntimeError("No se encontró contenido ZPL.")


def _output_dir(env: Dict[str, str]) -> Path:
  raw = env.get("ENVIAME_LABEL_OUTPUT_DIR")
  if raw:
    path = Path(raw)
    if not path.is_absolute():
      path = _base_path() / path
  else:
    path = Path.home() / "Downloads"
  path.mkdir(parents=True, exist_ok=True)
  return path


def _api_key_for_channel(env: Dict[str, str], canal: str) -> str:
  key = env.get(f"ENVIAME_API_KEY_{canal.upper()}")
  if key:
    return key
  if env.get("ENVIAME_API_KEY"):
    return env["ENVIAME_API_KEY"]
  raise RuntimeError(f"Falta ENVIAME_API_KEY_{canal.upper()} o ENVIAME_API_KEY en .env")


def _api_base(env: Dict[str, str]) -> str:
  base = env.get("ENVIAME_API_BASE", "https://api.enviame.io/api").rstrip("/")
  return base


def _seller_id(env: Dict[str, str]) -> str:
  sid = env.get("ENVIAME_SELLER_ID")
  if not sid:
    raise RuntimeError("Falta ENVIAME_SELLER_ID en .env")
  return sid


def _fetch_delivery(api_key: str, api_base: str, delivery_id: str) -> Dict[str, Any]:
  url = f"{api_base}/s2/v2/deliveries/{quote(str(delivery_id), safe='')}"
  body = http_get(url, headers={"api-key": api_key, "Accept": "application/json"})
  return json.loads(body)


def descargar_etiqueta_enviame_por_delivery(
  delivery_id: str,
  canal: str,
  env_path: Optional[str] = None,
) -> str:
  """
  Descarga la etiqueta ZPL de un delivery_id único.
  Retorna la ruta del archivo guardado.
  """
  env = load_env(env_path)
  api_key = _api_key_for_channel(env, canal)
  api_base = _api_base(env)
  out_dir = _output_dir(env)

  payload = _fetch_delivery(api_key, api_base, delivery_id)
  label = payload.get("data", {}).get("label")
  source = _classify_zpl(label.get("ZPL") if isinstance(label, dict) else label)
  if not source:
    raise RuntimeError(f"No se encontró etiqueta ZPL para el envío {delivery_id}")

  zpl = _download_zpl_from_source(source)
  dest = out_dir / f"{delivery_id}.zpl"
  dest.write_text(zpl["content"], encoding="utf-8")
  return str(dest)


def _collect_matches_shipment(
  shipping_number: str,
  api_key: str,
  api_base: str,
  seller_id: str,
  max_pages: int = 50,
  limit: int = 100,
  stop_after_first_match: bool = False,
) -> List[Dict[str, Any]]:
  matches: List[Dict[str, Any]] = []
  found_page: Optional[int] = None

  for page in range(1, max_pages + 1):
    url = f"{api_base}/s2/v2/companies/{quote(seller_id)}/deliveries?page={page}&limit={limit}"
    body = http_get(url, headers={"api-key": api_key, "Accept": "application/json"})
    data = json.loads(body)
    items = data.get("data", [])
    if not isinstance(items, list) or not items:
      break

    for item in items:
      if not isinstance(item, dict):
        continue
      if str(item.get("tracking_number")) == shipping_number or str(item.get("imported_id")) == shipping_number:
        matches.append(item)
        if found_page is None:
          found_page = page

    if found_page is not None:
      if stop_after_first_match:
        break
      if page >= found_page+1:
        break

    if len(items) < limit:
      break

  return matches


def descargar_etiquetas_enviame_por_shipping(
  shipping_number: str,
  canal: str,
  env_path: Optional[str] = None,
  stop_after_first_match: bool = False,
) -> List[str]:
  """
  Lista los deliveries del seller y descarga todas las etiquetas ZPL
  que coincidan con tracking_number/imported_id == shipping_number.

  Retorna lista de rutas guardadas.
  """
  env = load_env(env_path)
  api_key = _api_key_for_channel(env, canal)
  api_base = _api_base(env)
  seller_id = _seller_id(env)
  out_dir = _output_dir(env)

  deliveries = _collect_matches_shipment(shipping_number, api_key, api_base, seller_id, stop_after_first_match=stop_after_first_match)
  if not deliveries:
    raise RuntimeError(
      f"No se encontraron fletes para el numero de envio {shipping_number}. "
      "Verifica tracking_number/imported_id y que el seller_id sea correcto."
    )

  saved: List[str] = []
  for d in deliveries:
    imported_id = d.get("imported_id") or shipping_number
    tracking = d.get("tracking_number") or d.get("identifier") or d.get("id")
    candidates = [d.get("identifier"), d.get("tracking_number"), d.get("id"), d.get("delivery_id")]
    tried = set()
    success = False
    for cid in candidates:
      if not cid or cid in tried:
        continue
      tried.add(cid)
      try:
        payload = _fetch_delivery(api_key, api_base, str(cid))
        label = payload.get("data", {}).get("label")
        source = _classify_zpl(label.get("ZPL") if isinstance(label, dict) else label)
        if not source:
          continue
        zpl = _download_zpl_from_source(source)
        name_part = tracking or cid
        dest = out_dir / f"{imported_id}-{name_part}.zpl"
        dest.write_text(zpl["content"], encoding="utf-8")
        saved.append(str(dest))
        success = True
        break
      except Exception:
        continue
    if not success:
      raise RuntimeError(f"No se pudo obtener etiqueta para el envio {d}")

  return saved


__all__ = [
  "descargar_etiquetas_enviame_por_shipping",
  "descargar_etiqueta_enviame_por_delivery",
]


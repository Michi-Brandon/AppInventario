"""
Cliente para descargar etiquetas ZPL de Paris (Cencosud) sin pasar por Enviame.

Flujo:
1) Obtiene/renueva access token usando un bearer estatico (4h por defecto).
2) Llama a /orders/{orderNumber}.
3) Busca etiqueta ZPL (url) dentro de subOrders y la descarga a la carpeta destino.

Variables en .env:
- CENCOSUD_STATIC_BEARER (requerido)
- AUTH_URL (default: https://api-developers.ecomm-stg.cencosud.com/v1/auth/apiKey)
- ORDERS_BASE_URL (default: https://api-developers.ecomm.cencosud.com/v1)
- TOKEN_TTL_HOURS opcional (default: 4)
- LABEL_OUTPUT_DIR o CENCOSUD_LABEL_OUTPUT_DIR opcional (default: ~/Downloads)
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import requests

ENV_FILENAME = ".env"
PROD_AUTH_URL = "https://api-developers.ecomm.cencosud.com/v1/auth/apiKey"
STG_AUTH_URL = "https://api-developers.ecomm-stg.cencosud.com/v1/auth/apiKey"
DEFAULT_ORDERS_BASE_URL = "https://api-developers.ecomm.cencosud.com/v1"
DEFAULT_TTL_HOURS = 4
EXPIRY_SKEW_SECONDS = 120  # refresca 2 minutos antes


def _base_path() -> Path:
  if getattr(__import__("sys"), "frozen", False):
    return Path(__import__("sys").executable).parent
  return Path(__file__).resolve().parent


def _load_env(path: Optional[str] = None) -> Dict[str, str]:
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
  # Merge with current environment (gives priority to OS env vars)
  merged = {**env, **os.environ}
  return merged


def _output_dir(env: Dict[str, str]) -> Path:
  raw = env.get("LABEL_OUTPUT_DIR") or env.get("CENCOSUD_LABEL_OUTPUT_DIR")
  if raw:
    path = Path(raw)
    if not path.is_absolute():
      path = _base_path() / path
  else:
    path = Path.home() / "Downloads"
  path.mkdir(parents=True, exist_ok=True)
  return path


def _token_cache_path() -> Path:
  return _base_path() / ".cache" / "cencosud-token.json"


def _auth_url(env: Dict[str, str]) -> str:
  if env.get("AUTH_URL"):
    return env["AUTH_URL"]
  orders_base = (env.get("ORDERS_BASE_URL") or DEFAULT_ORDERS_BASE_URL).lower()
  return STG_AUTH_URL if "ecomm-stg" in orders_base else PROD_AUTH_URL


def _read_cached_token() -> Optional[str]:
  cache_path = _token_cache_path()
  if not cache_path.exists():
    return None
  try:
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    access_token = data.get("accessToken")
    expires_at_str = data.get("expiresAt")
    if not access_token or not expires_at_str:
      return None
    expires_at = datetime.fromisoformat(expires_at_str)
    if datetime.utcnow() + timedelta(seconds=EXPIRY_SKEW_SECONDS) < expires_at:
      return access_token
  except Exception:
    return None
  return None


def _cache_token(token: str, expires_at: datetime) -> None:
  cache_path = _token_cache_path()
  cache_path.parent.mkdir(parents=True, exist_ok=True)
  payload = {"accessToken": token, "expiresAt": expires_at.isoformat()}
  cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _request_new_token(env: Dict[str, str]) -> str:
  static_bearer = env.get("CENCOSUD_STATIC_BEARER")
  if not static_bearer:
    raise RuntimeError("Falta CENCOSUD_STATIC_BEARER en .env")

  primary_url = _auth_url(env)
  fallback_url = PROD_AUTH_URL if primary_url == STG_AUTH_URL else STG_AUTH_URL
  urls_to_try = [primary_url]
  if primary_url != fallback_url and not env.get("AUTH_URL"):
    urls_to_try.append(fallback_url)

  last_error = None
  for url in urls_to_try:
    response = requests.post(url, headers={"Authorization": f"Bearer {static_bearer}"}, timeout=60)
    if response.ok:
      data = response.json()
      access_token = data.get("accessToken") or data.get("token") or data.get("access_token")
      if not access_token:
        raise RuntimeError("Auth response did not include an access token (accessToken/token/access_token).")

      expires_in_seconds = data.get("expiresIn") or data.get("expires_in")
      if expires_in_seconds is None:
        expires_in_seconds = int(env.get("TOKEN_TTL_HOURS", DEFAULT_TTL_HOURS)) * 60 * 60
      expires_at = datetime.utcnow() + timedelta(seconds=int(expires_in_seconds))
      _cache_token(access_token, expires_at)
      return access_token

    last_error = f"Auth request failed ({response.status_code}) url={url}: {response.text}"

  raise RuntimeError(last_error or "Auth request failed and no more URLs to try.")


def _get_access_token(env: Dict[str, str]) -> str:
  cached = _read_cached_token()
  if cached:
    return cached
  return _request_new_token(env)


def _fetch_order(order_number: str, token: str, env: Dict[str, str], allow_retry: bool = True) -> Dict[str, Any]:
  base_url = (env.get("ORDERS_BASE_URL") or DEFAULT_ORDERS_BASE_URL).rstrip("/")
  url = f"{base_url}/orders/{order_number}"
  response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=60)

  if response.status_code in (401, 403) and allow_retry:
    refreshed = _request_new_token(env)
    return _fetch_order(order_number, refreshed, env, allow_retry=False)

  if not response.ok:
    raise RuntimeError(f"Order request failed ({response.status_code}): {response.text}")

  return response.json()


def _normalize_labels(raw_label: Any) -> list:
  if raw_label is None:
    return []
  if isinstance(raw_label, list):
    return raw_label
  return [raw_label]


def _pick_label(order: Dict[str, Any]) -> Dict[str, Any]:
  sub_orders = order.get("subOrders") or []
  for sub in sub_orders:
    labels = _normalize_labels(sub.get("label"))
    if not labels:
      continue
    preferred = next(
      (l for l in labels if str(l.get("format") or "").lower().strip() == "zpl"),
      labels[0],
    )
    url = preferred.get("url")
    if url:
      return {
        "url": url,
        "format": preferred.get("format") or "zpl",
        "subOrderNumber": sub.get("subOrderNumber") or sub.get("originOrderNumber"),
        "labelId": sub.get("labelId") or sub.get("label_id"),
      }
  raise RuntimeError("No se encontro etiqueta con URL en la respuesta de orden.")


def _download_label(label_info: Dict[str, Any], token: str, env: Dict[str, str]) -> Path:
  headers = {"Authorization": f"Bearer {token}"} if token else {}
  response = requests.get(label_info["url"], headers=headers, timeout=60)
  if not response.ok:
    raise RuntimeError(f"Label download failed ({response.status_code}): {response.text}")

  content = response.content
  extension_from_format = (label_info.get("format") or "").lower() or "zpl"
  extension_from_url = ""
  try:
    extension_from_url = Path(label_info["url"]).suffix.replace(".", "")
  except Exception:
    extension_from_url = ""
  extension = extension_from_url or extension_from_format or "bin"

  filename_parts = [
    "label",
    label_info.get("subOrderNumber") or "order",
    label_info.get("labelId") or extension,
  ]
  filename = "_".join(str(part) for part in filename_parts if part) + f".{extension}"

  out_dir = _output_dir(env)
  out_path = out_dir / filename
  out_path.write_bytes(content)
  return out_path


def _order_number_for_api(order_number: str) -> str:
  # Los pedidos de Paris vienen como subOrden (terminan en un dígito extra).
  # La API de /orders/{id} espera el número base sin el último carácter.
  return order_number[:-1] if len(order_number) > 1 else order_number


def descargar_etiqueta_paris_cencosud(order_number: str, env_path: Optional[str] = None) -> str:
  """
  Obtiene la etiqueta ZPL de Paris Cencosud por numero de venta y la guarda en Disco.
  Retorna la ruta del archivo.
  """
  env = _load_env(env_path)
  token = _get_access_token(env)
  order_number_api = _order_number_for_api(order_number)
  order = _fetch_order(order_number_api, token, env)
  label_info = _pick_label(order)
  out_path = _download_label(label_info, token, env)
  return str(out_path)


__all__ = ["descargar_etiqueta_paris_cencosud"]

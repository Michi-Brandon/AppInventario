"""
Cliente ligero para descargar etiquetas de MercadoLibre desde la UI.

Basado en el flujo CLI compartido:
- Refresca access_token con refresh_token
- Busca la orden (orders/{id} o packs/{id})
- Obtiene shipping_id y descarga etiqueta ZPL/PDF

Uso principal desde la UI:
    descargar_etiqueta_mercadolibre(order_id: str, ... ) -> str (ruta del archivo guardado)

Requiere variables en .env (en la raíz de la app o del ejecutable):
    ML_CLIENT_ID
    ML_CLIENT_SECRET
    ML_REFRESH_TOKEN
Opcional:
    ML_SELLER_ID
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, Optional, Tuple


ENV_FILENAME = ".env"
TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
ORDER_URL = "https://api.mercadolibre.com/orders/{order_id}"
PACK_URL = "https://api.mercadolibre.com/packs/{pack_id}"
LABEL_URL = (
    "https://api.mercadolibre.com/shipment_labels?shipment_ids={shipment_id}"
    "&response_type={response_type}"
)


class NonPrintableError(RuntimeError):
    """Señala que la etiqueta no es imprimible (ej: ya se generó)."""


def _base_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def load_env(path: Optional[str] = None) -> Dict[str, str]:
    env_path = Path(path) if path else _base_path() / ENV_FILENAME
    if not env_path.exists():
        raise FileNotFoundError(
            f"No se encontró {env_path}. Copia .env.example a {env_path} y completa tus credenciales."
        )
    env: Dict[str, str] = {}
    with open(env_path, "r", encoding="utf-8") as fh:
        for line in fh:
            striped = line.strip()
            if not striped or striped.startswith("#") or "=" not in striped:
                continue
            key, val = striped.split("=", 1)
            env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def ensure_keys(env: Dict[str, str], keys: list[str]) -> None:
    missing = [k for k in keys if not env.get(k)]
    if missing:
        raise SystemExit(f"Faltan variables en .env: {', '.join(missing)}")


def http_request(
    method: str, url: str, headers: Optional[Dict[str, str]] = None, data: Optional[bytes] = None
) -> bytes:
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:  # noqa: BLE001
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} en {url} - cuerpo: {body}") from exc


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> Dict[str, str]:
    payload = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }
    data = urllib.parse.urlencode(payload).encode("utf-8")
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    raw = http_request("POST", TOKEN_URL, headers=headers, data=data)
    token_info = json.loads(raw.decode("utf-8"))
    if "access_token" not in token_info:
        raise RuntimeError(f"Respuesta inesperada al refrescar token: {token_info}")
    return token_info


def get_order(order_id: str, access_token: str) -> Tuple[Dict, str]:
    url = ORDER_URL.format(order_id=order_id)
    headers = {"Authorization": f"Bearer {access_token}"}
    raw = http_request("GET", url, headers=headers)
    return json.loads(raw.decode("utf-8")), url


def get_pack(pack_id: str, access_token: str) -> Tuple[Dict, str]:
    url = PACK_URL.format(pack_id=pack_id)
    headers = {"Authorization": f"Bearer {access_token}"}
    raw = http_request("GET", url, headers=headers)
    return json.loads(raw.decode("utf-8")), url


def matches_identifier(order: Dict, identifier: str) -> bool:
    return str(order.get("id")) == identifier or str(order.get("pack_id")) == identifier


def find_order_any(order_identifier: str, access_token: str, seller_id: Optional[str] = None):
    """
    Busca el pedido intentando (devuelve order_dict):
    1) GET /orders/{order_identifier}
    2) GET /packs/{order_identifier}
    """
    # 1) orders/{id}
    try:
        order, _ = get_order(order_identifier, access_token)
        if matches_identifier(order, order_identifier):
            return order
    except Exception:
        pass

    # 2) packs/{id}
    try:
        pack, _ = get_pack(order_identifier, access_token)
        if matches_identifier(pack, order_identifier):
            return pack
    except Exception:
        pass

    raise RuntimeError(
        f"No se encontró la orden usando id/pack_id = {order_identifier}. "
        "Verifica seller_id y que el id sea correcto."
    )


def extract_shipping_id(order: Dict) -> int:
  shipping = order.get("shipping") or {}
  shipping_id = shipping.get("id")
  if not shipping_id:
    shipment = order.get("shipment") or {}
    shipping_id = shipment.get("id")
    if not shipping_id:
        raise RuntimeError("El order/pack no tiene shipping_id disponible.")
  return shipping_id


def obtener_shipping_id(order_id: str, env_path: Optional[str] = None) -> int:
  """
  Devuelve el shipping_id de una orden o pack de Mercado Libre.
  Reutiliza el refresh_token y find_order_any (orders/{id} o packs/{id}).
  """
  env = load_env(env_path)
  ensure_keys(env, ["ML_CLIENT_ID", "ML_CLIENT_SECRET", "ML_REFRESH_TOKEN"])
  seller_id = env.get("ML_SELLER_ID")

  token_info = refresh_access_token(
      env["ML_CLIENT_ID"], env["ML_CLIENT_SECRET"], env["ML_REFRESH_TOKEN"]
  )
  access_token = token_info["access_token"]

  order = find_order_any(order_id, access_token, seller_id=seller_id)
  return extract_shipping_id(order)


def download_label(shipment_id: int, access_token: str, response_type: str = "zpl2") -> bytes:
    url = LABEL_URL.format(shipment_id=shipment_id, response_type=response_type)
    headers = {"Authorization": f"Bearer {access_token}"}
    return http_request("GET", url, headers=headers)


def is_zip(data: bytes) -> bool:
    return data.startswith(b"PK\x03\x04")


def descargar_etiqueta_mercadolibre(
    order_id: str,
    response_type: str = "zpl2",
    save_to_downloads: bool = True,
    save_path: Optional[str] = None,
    env_path: Optional[str] = None,
) -> str:
    """
    Descarga la etiqueta del order_id/pack_id dado y la guarda en disco.

    Retorna la ruta del archivo guardado.
    Lanza NonPrintableError si la API indica NOT_PRINTABLE_STATUS.
    """
    env = load_env(env_path)
    ensure_keys(env, ["ML_CLIENT_ID", "ML_CLIENT_SECRET", "ML_REFRESH_TOKEN"])
    seller_id = env.get("ML_SELLER_ID")

    token_info = refresh_access_token(
        env["ML_CLIENT_ID"], env["ML_CLIENT_SECRET"], env["ML_REFRESH_TOKEN"]
    )
    access_token = token_info["access_token"]

    order = find_order_any(order_id, access_token, seller_id=seller_id)
    shipping_id = extract_shipping_id(order)

    try:
        label_bytes = download_label(shipping_id, access_token, response_type=response_type)
    except RuntimeError as exc:
        msg = str(exc)
        if "NOT_PRINTABLE_STATUS" in msg:
            raise NonPrintableError(
                f"La etiqueta del envío {shipping_id} ya fue generada o no es imprimible (estado de ML)."
            ) from exc
        raise

    target_dir = Path(save_path) if save_path else (Path.home() / "Downloads" if save_to_downloads else _base_path())
    target_dir.mkdir(parents=True, exist_ok=True)
    if response_type.lower() == "pdf":
        filename = f"ML_{order_id}.pdf"
    else:
        filename = f"ML_{order_id}.zip" if is_zip(label_bytes) else f"ML_{order_id}.zpl"
    target_path = target_dir / filename
    with open(target_path, "wb") as fh:
        fh.write(label_bytes)

    return str(target_path)


__all__ = [
  "descargar_etiqueta_mercadolibre",
  "NonPrintableError",
  "obtener_shipping_id",
]

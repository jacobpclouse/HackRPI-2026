"""AISStream WebSocket client.

Confirmed 2026-11-07 from https://aisstream.io/documentation and the
ais-message-models repo:

- URL: ``wss://stream.aisstream.io/v0/stream``
- Send one JSON subscription within 3 seconds of connect. Field names are
  PascalCase: ``APIKey``, ``BoundingBoxes``, ``FilterMessageTypes``.
- Bounding boxes are pairs of [lat, lon] corners. World:
  ``[[[-90, -180], [90, 180]]]``.
- Filter to ``PositionReport`` and ``ShipStaticData``.
- Frames are binary UTF-8 JSON. Envelope: ``MessageType``, ``MetaData``
  (MMSI, ShipName, Latitude, Longitude), ``Message.<Type>`` payload
  (Sog/Cog/TrueHeading; Type/Name/Destination/Dimension for static).
- Skip missing MMSI/lat/lon; reject outside ±90/±180, exactly 0,0, and the
  AIS "not available" sentinels lat 91 / lon 181.

The API key is never logged.
"""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

import certifi

logger = logging.getLogger("darkwatch.ais.stream")

WS_URL = "wss://stream.aisstream.io/v0/stream"
WORLD_BBOX = [[[-90, -180], [90, 180]]]
FILTER_TYPES = ["PositionReport", "ShipStaticData"]
HEADING_NA = 511
SOG_NA = 102.3


@dataclass
class Ship:
    mmsi: str
    name: str = ""
    lat: float = 0.0
    lon: float = 0.0
    sog: float | None = None
    cog: float | None = None
    heading: float | None = None
    type_code: int | None = None
    category: str = "other"
    last_report: str = ""
    length_m: float | None = None
    destination: str = ""
    has_position: bool = False

    def to_row(self) -> list:
        return [
            self.mmsi,
            self.name,
            round(self.lat, 4),
            round(self.lon, 4),
            None if self.sog is None else round(float(self.sog), 1),
            None if self.cog is None else round(float(self.cog), 1),
            None if self.heading is None else round(float(self.heading), 1),
            self.category,
            self.last_report,
        ]


@dataclass
class PullResult:
    ships: dict[str, Ship] = field(default_factory=dict)
    n_position_reports: int = 0
    error: str | None = None


def category_for(type_code: int | None) -> str:
    if type_code is None:
        return "other"
    code = int(type_code)
    if 70 <= code <= 79:
        return "cargo"
    if 80 <= code <= 89:
        return "tanker"
    if 60 <= code <= 69:
        return "passenger"
    if code == 30:
        return "fishing"
    if code in (31, 32, 52):
        return "tug"
    if code == 35:
        return "military"
    if code in (36, 37):
        return "pleasure"
    return "other"


def _meta(msg: dict) -> dict:
    return msg.get("MetaData") or msg.get("metadata") or {}


def _payload(msg: dict, kind: str) -> dict:
    block = msg.get("Message") or msg.get("message") or {}
    return block.get(kind) or block.get(kind[0].lower() + kind[1:]) or {}


def _num(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _report_time(meta: dict) -> str:
    for key in ("time_utc", "TimeUTC", "timeUTC", "timestamp"):
        raw = meta.get(key)
        if not raw:
            continue
        text = str(raw).replace(" ", "T")
        if text.endswith("+00:00"):
            text = text[:-6] + "Z"
        if not text.endswith("Z") and "T" in text:
            text += "Z"
        return text
    return _iso_now()


def coords_ok(lat: float | None, lon: float | None) -> bool:
    if lat is None or lon is None:
        return False
    if lat == 0.0 and lon == 0.0:
        return False
    if lat == 91.0 or lon == 181.0:
        return False
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return False
    return True


def parse_message(msg: dict, ships: dict[str, Ship]) -> str | None:
    """Apply one envelope to ``ships``. Return 'position' | 'static' | None."""
    kind = msg.get("MessageType") or msg.get("messageType") or ""
    meta = _meta(msg)
    mmsi = meta.get("MMSI") or meta.get("mmsi")
    if mmsi is None:
        body = _payload(msg, kind)
        mmsi = body.get("UserID") or body.get("userID")
    if mmsi is None:
        return None
    mmsi = str(mmsi).strip()
    if not mmsi:
        return None
    ship = ships.get(mmsi) or Ship(mmsi=mmsi)
    name = (meta.get("ShipName") or meta.get("shipName") or "").strip()
    if name:
        ship.name = name

    if kind == "PositionReport":
        body = _payload(msg, "PositionReport")
        lat = _num(meta.get("Latitude") if meta.get("Latitude") is not None else meta.get("latitude"))
        lon = _num(meta.get("Longitude") if meta.get("Longitude") is not None else meta.get("longitude"))
        if lat is None:
            lat = _num(body.get("Latitude") if body.get("Latitude") is not None else body.get("latitude"))
        if lon is None:
            lon = _num(body.get("Longitude") if body.get("Longitude") is not None else body.get("longitude"))
        if not coords_ok(lat, lon):
            return None
        ship.lat = float(lat)
        ship.lon = float(lon)
        ship.has_position = True
        sog = _num(body.get("Sog") if body.get("Sog") is not None else body.get("sog"))
        cog = _num(body.get("Cog") if body.get("Cog") is not None else body.get("cog"))
        heading = _num(body.get("TrueHeading") if body.get("TrueHeading") is not None else body.get("trueHeading"))
        if sog is not None and sog < SOG_NA:
            ship.sog = sog
        if cog is not None and 0 <= cog <= 360:
            ship.cog = cog
        if heading is not None and heading != HEADING_NA and 0 <= heading <= 360:
            ship.heading = heading
        ship.last_report = _report_time(meta)
        ships[mmsi] = ship
        return "position"

    if kind == "ShipStaticData":
        body = _payload(msg, "ShipStaticData")
        static_name = (body.get("Name") or body.get("name") or "").strip()
        if static_name:
            ship.name = static_name
        type_code = body.get("Type") if body.get("Type") is not None else body.get("type")
        if type_code is not None:
            try:
                ship.type_code = int(type_code)
                ship.category = category_for(ship.type_code)
            except (TypeError, ValueError):
                pass
        dest = (body.get("Destination") or body.get("destination") or "").strip()
        if dest:
            ship.destination = dest
        dim = body.get("Dimension") or body.get("dimension") or {}
        a, b = _num(dim.get("A") if dim.get("A") is not None else dim.get("a")), _num(
            dim.get("B") if dim.get("B") is not None else dim.get("b")
        )
        if a is not None and b is not None:
            ship.length_m = a + b
        ships[mmsi] = ship
        return "static"
    return None


def _decode(raw) -> dict | None:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    if isinstance(raw, dict):
        return raw
    return None


def _ssl_context() -> ssl.SSLContext:
    """python.org macOS builds do not ship a CA bundle; certifi does."""
    return ssl.create_default_context(cafile=certifi.where())


async def pull(api_key: str, listen_s: float, bbox_world: bool = True, on_progress=None) -> PullResult:
    """Connect, subscribe, listen ``listen_s`` seconds, return latest ship per MMSI."""
    import websockets

    result = PullResult()
    if not api_key:
        result.error = "no API key"
        return result
    bbox = WORLD_BBOX if bbox_world else WORLD_BBOX
    sub = {
        "APIKey": api_key,
        "BoundingBoxes": bbox,
        "FilterMessageTypes": FILTER_TYPES,
    }
    try:
        async with websockets.connect(
            WS_URL,
            ssl=_ssl_context(),
            compression="deflate",
            max_size=2**22,
            open_timeout=10,
            close_timeout=2,
        ) as ws:
            await ws.send(json.dumps(sub))
            logger.info("AISStream subscribed world PositionReport+ShipStaticData listen_s=%s", listen_s)
            loop = asyncio.get_running_loop()
            deadline = loop.time() + float(listen_s)
            last_progress = loop.time()

            async def _read():
                nonlocal last_progress
                async for raw in ws:
                    msg = _decode(raw)
                    if not msg:
                        continue
                    kind = parse_message(msg, result.ships)
                    if kind == "position":
                        result.n_position_reports += 1
                    now = loop.time()
                    if on_progress and now - last_progress >= 30:
                        last_progress = now
                        on_progress(result.n_position_reports, len(result.ships))

            try:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    remaining = 0.1
                await asyncio.wait_for(_read(), timeout=remaining)
            except TimeoutError:
                pass
            try:
                await ws.close()
            except Exception:
                pass
    except asyncio.CancelledError:
        result.error = "cancelled"
        raise
    except Exception as exc:
        result.error = f"connection failed: {type(exc).__name__}"
        logger.warning("AISStream pull failed: %s", result.error)
    positioned = {mmsi: ship for mmsi, ship in result.ships.items() if ship.has_position}
    result.ships = positioned
    return result


def ship_from_row(fields: list[str], row: list) -> Ship:
    item = dict(zip(fields, row, strict=False))
    return Ship(
        mmsi=str(item.get("mmsi") or ""),
        name=item.get("name") or "",
        lat=float(item.get("lat") or 0),
        lon=float(item.get("lon") or 0),
        sog=item.get("sog"),
        cog=item.get("cog"),
        heading=item.get("heading"),
        category=item.get("category") or "other",
        last_report=item.get("last_report") or "",
        has_position=True,
    )


def ship_dict(ship: Ship) -> dict:
    data = asdict(ship)
    data.pop("has_position", None)
    return data

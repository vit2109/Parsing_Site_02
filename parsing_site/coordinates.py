"""
Координаты и расстояния.

Режимы:
  screen / map_relative / percent — пиксели (плывут при зуме);
  latlng — широта/долгота и километры (haversine), устойчиво к зуму и сдвигу.

Если живой Leaflet недоступен, lat/lng восстанавливаются из .leaflet-proxy
по проекции Web Mercator (EPSG:3857).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import asin, atan, cos, degrees, log, log2, pi, radians, sin, sinh, sqrt
from typing import Any, Literal

CoordinateMode = Literal["screen", "map_relative", "percent", "latlng"]
GeoSource = Literal["leaflet", "proxy3857", "none"]

EARTH_RADIUS_M = 6_371_000.0
MAX_LATITUDE = 85.0511287798
TILE_SIZE = 256.0


@dataclass(slots=True)
class Point2D:
    """Точка: экранные x/y и опционально широта/долгота."""

    x: float
    y: float
    lat: float | None = None
    lng: float | None = None

    @property
    def has_geo(self) -> bool:
        """Показывает, что у точки есть обе географические координаты."""
        return self.lat is not None and self.lng is not None


@dataclass(slots=True)
class CssTransform:
    """CSS transform: translate3d(x, y) и необязательный scale (leaflet-proxy)."""

    x: float
    y: float
    scale: float = 1.0


@dataclass(slots=True)
class MapView:
    """Текущий вид Leaflet: размер контейнера + proxy (для пересчёта при зуме/пане)."""

    width: float
    height: float
    zoom: float | None = None
    proxy_x: float | None = None
    proxy_y: float | None = None
    proxy_scale: float | None = None
    has_leaflet: bool = False
    geo_source: GeoSource = "none"
    center_lat: float | None = None
    center_lng: float | None = None

    @property
    def can_unproject(self) -> bool:
        """Показывает, достаточно ли данных вида карты для пересчёта координат."""
        return (
            self.zoom is not None
            and self.width > 0
            and self.height > 0
            and (
                (self.proxy_x is not None and self.proxy_y is not None)
                or (self.center_lat is not None and self.center_lng is not None)
            )
        )


def distance_between(a: Point2D, b: Point2D, mode: CoordinateMode) -> float:
    """Километры (latlng) или пиксели (остальные режимы)."""
    if mode == "latlng":
        if not a.has_geo or not b.has_geo:
            raise ValueError("Для режима latlng нужны lat/lng у обеих точек.")
        return haversine_km(a.lat, a.lng, b.lat, b.lng)
    return euclidean(a.x, b.x, a.y, b.y)


def euclidean(x1: float, x2: float, y1: float, y2: float) -> float:
    """Вычисляет прямое расстояние между двумя точками на плоскости."""
    return sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Вычисляет ортодромическое расстояние между WGS-84 точками в метрах."""
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlmb = radians(lng2 - lng1)
    h = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(h))


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Ортодромия между двумя WGS-84 точками, километры."""
    return haversine_meters(lat1, lng1, lat2, lng2) / 1000.0


def normalize_mode(value: str) -> CoordinateMode:
    """Нормализует название режима, заменяя неизвестное значение на ``screen``."""
    text = (value or "screen").strip().lower()
    if text in {"screen", "map_relative", "percent", "latlng"}:
        return text  # type: ignore[return-value]
    return "screen"


def distance_unit(mode: CoordinateMode) -> str:
    """Возвращает единицу измерения для выбранного режима координат."""
    return "km" if mode == "latlng" else "px"


def static_to_point(
    item: dict[str, Any] | Any,
    *,
    mode: CoordinateMode,
    map_size: tuple[float, float] | None = None,
    map_view: MapView | None = None,
) -> Point2D:
    """Преобразует настроенную статичную точку в координаты текущего вида карты."""
    lat = _optional_float(_get(item, "lat"))
    lng = _optional_float(_get(item, "lng"))
    x = float(_get(item, "x", 0))
    y = float(_get(item, "y", 0))

    if mode == "latlng":
        view = map_view
        if lat is not None and lng is not None:
            if view and view.can_unproject:
                projected = latlng_to_container(lat, lng, view)
                if projected is not None:
                    x, y = projected
            return Point2D(x=x, y=y, lat=lat, lng=lng)
        if view and view.can_unproject:
            geo = container_to_latlng(x, y, view)
            if geo is not None:
                lat, lng = geo
        if lat is None or lng is None:
            raise ValueError(
                f"Статичная точка '{_get(item, 'name', '?')}': "
                "в режиме latlng нужны lat и lng либо x/y при известном виде карты."
            )
        return Point2D(x=x, y=y, lat=lat, lng=lng)

    if mode == "percent":
        width, height = map_size or (100.0, 100.0)
        return Point2D(x=width * x / 100.0, y=height * y / 100.0, lat=lat, lng=lng)

    return Point2D(x=x, y=y, lat=lat, lng=lng)


def dynamic_to_point(item: dict[str, Any], mode: CoordinateMode) -> Point2D:
    """Создаёт точку из сырых данных динамического маркера."""
    return Point2D(
        x=float(item["x"]),
        y=float(item["y"]),
        lat=_optional_float(item.get("lat")),
        lng=_optional_float(item.get("lng")),
    )


def parse_translate3d(style: str) -> tuple[float, float] | None:
    """Извлекает смещение X/Y из CSS ``translate3d``."""
    transform = parse_css_transform(style)
    if transform is None:
        return None
    return transform.x, transform.y


def parse_css_transform(style: str) -> CssTransform | None:
    """Разбирает CSS ``translate3d`` и необязательный ``scale``."""
    text = style or ""
    marker = "translate3d("
    if marker not in text:
        return None
    chunk = text.split(marker, 1)[1].split(")", 1)[0]
    parts = [part.strip() for part in chunk.split(",")]
    if len(parts) < 2:
        return None
    try:
        x = float(parts[0].replace("px", ""))
        y = float(parts[1].replace("px", ""))
    except ValueError:
        return None
    scale = 1.0
    scale_marker = "scale("
    if scale_marker in text:
        raw = text.split(scale_marker, 1)[1].split(")", 1)[0].strip()
        try:
            scale = float(raw)
        except ValueError:
            scale = 1.0
    return CssTransform(x=x, y=y, scale=scale)


def infer_webmercator_zoom(proxy: CssTransform) -> float | None:
    """Zoom из leaflet-proxy: scale(2^z) или scale(2^(z-1)) в зависимости от версии Leaflet."""
    if proxy.scale <= 0:
        return None
    log_scale = log2(proxy.scale)
    candidates = (
        (log_scale, TILE_SIZE * proxy.scale),
        (log_scale + 1.0, TILE_SIZE * proxy.scale * 2.0),
    )
    for zoom, world in candidates:
        if 0 <= proxy.x <= world and 0 <= proxy.y <= world:
            lat, lng = unproject_3857(proxy.x, proxy.y, zoom)
            if abs(lat) <= MAX_LATITUDE and abs(lng) <= 180:
                return zoom
    for zoom, world in candidates:
        lat, lng = unproject_3857(proxy.x, proxy.y, zoom)
        if abs(lat) <= MAX_LATITUDE and abs(lng) <= 180:
            return zoom
    return None


def unproject_3857(x: float, y: float, zoom: float) -> tuple[float, float]:
    """Переводит мировые пиксели Web Mercator в широту и долготу."""
    scale = TILE_SIZE * (2**zoom)
    lng = x / scale * 360.0 - 180.0
    y_norm = y / scale
    lat = degrees(atan(sinh(pi * (1.0 - 2.0 * y_norm))))
    return lat, lng


def project_3857(lat: float, lng: float, zoom: float) -> tuple[float, float]:
    """Проецирует широту и долготу в мировые пиксели Web Mercator."""
    scale = TILE_SIZE * (2**zoom)
    x = (lng + 180.0) / 360.0 * scale
    clamped = max(min(lat, MAX_LATITUDE), -MAX_LATITUDE)
    siny = sin(radians(clamped))
    y = (0.5 - log((1.0 + siny) / (1.0 - siny)) / (4.0 * pi)) * scale
    return x, y


def container_to_latlng(
    x: float, y: float, view: MapView
) -> tuple[float, float] | None:
    """Пиксель контейнера карты → lat/lng (Web Mercator, текущий zoom/proxy)."""
    if not view.can_unproject or view.zoom is None:
        return None
    if view.proxy_x is not None and view.proxy_y is not None:
        center_x, center_y = view.proxy_x, view.proxy_y
    elif view.center_lat is not None and view.center_lng is not None:
        center_x, center_y = project_3857(view.center_lat, view.center_lng, view.zoom)
    else:
        return None
    world_x = x + center_x - view.width / 2.0
    world_y = y + center_y - view.height / 2.0
    return unproject_3857(world_x, world_y, view.zoom)


def latlng_to_container(
    lat: float, lng: float, view: MapView
) -> tuple[float, float] | None:
    """lat/lng → пиксель контейнера при текущем зуме и сдвиге карты."""
    if not view.can_unproject or view.zoom is None:
        return None
    if view.proxy_x is not None and view.proxy_y is not None:
        center_x, center_y = view.proxy_x, view.proxy_y
    elif view.center_lat is not None and view.center_lng is not None:
        center_x, center_y = project_3857(view.center_lat, view.center_lng, view.zoom)
    else:
        return None
    world_x, world_y = project_3857(lat, lng, view.zoom)
    x = world_x - center_x + view.width / 2.0
    y = world_y - center_y + view.height / 2.0
    return x, y


def map_view_from_raw(raw: dict[str, Any] | None) -> MapView | None:
    """Валидирует словарь браузерного снимка и создаёт описание вида карты."""
    if not raw:
        return None
    width = float(raw.get("width") or 0)
    height = float(raw.get("height") or 0)
    if width <= 0 or height <= 0:
        return None
    proxy = raw.get("proxy") or {}
    source = str(raw.get("geo_source") or "none")
    if source not in {"leaflet", "proxy3857", "none"}:
        source = "none"
    return MapView(
        width=width,
        height=height,
        zoom=_optional_float(raw.get("zoom") or raw.get("map_zoom")),
        proxy_x=_optional_float(proxy.get("x")),
        proxy_y=_optional_float(proxy.get("y")),
        proxy_scale=_optional_float(proxy.get("scale")),
        has_leaflet=bool(raw.get("has_leaflet")),
        geo_source=source,  # type: ignore[arg-type]
        center_lat=_optional_float((raw.get("center") or {}).get("lat")),
        center_lng=_optional_float((raw.get("center") or {}).get("lng")),
    )


def _optional_float(value: Any) -> float | None:
    """Преобразует заполненное значение в ``float`` и сохраняет отсутствие данных."""
    if value is None or value == "":
        return None
    return float(value)


def _get(item: dict[str, Any] | Any, key: str, default: Any = None) -> Any:
    """Единообразно читает поле из словаря или атрибут объекта."""
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)

"""プリセット地点の定義（地点はここ 1 か所だけで定義する）。

座標は各施設・駅の代表点の概算値（小数点以下 4 桁 ≒ 約 10m 精度）。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    lat: float
    lon: float


PRESETS: tuple[Preset, ...] = (
    Preset("umeda", "梅田（JR大阪駅）", 34.7025, 135.4959),
    Preset("shin-osaka", "新大阪駅", 34.7334, 135.5001),
    Preset("nakanoshima", "中之島（大阪市役所）", 34.6937, 135.5022),
    Preset("osaka-castle", "大阪城公園", 34.6873, 135.5259),
    Preset("kyobashi", "京橋駅", 34.6967, 135.5340),
    Preset("namba", "難波（なんば駅）", 34.6666, 135.5008),
    Preset("tennoji", "天王寺駅", 34.6466, 135.5139),
    Preset("osaka-aquarium", "海遊館", 34.6545, 135.4290),
)

_BY_ID = {p.id: p for p in PRESETS}


def find_preset(preset_id: str) -> Preset | None:
    return _BY_ID.get(preset_id)

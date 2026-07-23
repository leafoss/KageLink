from __future__ import annotations

from pc_agent.game_protocol import normalize_view_mode


def fit_full(image, output_size: tuple[int, int]):
    from PIL import Image

    output_width, output_height = output_size
    source = image.convert("RGB")
    source.thumbnail(output_size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", output_size, (5, 7, 10))
    x = (output_width - source.width) // 2
    y = (output_height - source.height) // 2
    canvas.paste(source, (x, y))
    return canvas


def fit_zoom(
    image,
    output_size: tuple[int, int],
    zoom_factor: float = 2.0,
):
    from PIL import Image

    source = image.convert("RGB")
    safe_zoom = max(1.0, float(zoom_factor))
    crop_width = max(1, int(source.width / safe_zoom))
    crop_height = max(1, int(source.height / safe_zoom))
    output_ratio = output_size[0] / output_size[1]
    crop_ratio = crop_width / crop_height
    if crop_ratio > output_ratio:
        crop_width = max(1, int(crop_height * output_ratio))
    else:
        crop_height = max(1, int(crop_width / output_ratio))
    left = max(0, (source.width - crop_width) // 2)
    top = max(0, (source.height - crop_height) // 2)
    crop = source.crop((left, top, left + crop_width, top + crop_height))
    return crop.resize(output_size, Image.Resampling.LANCZOS)


def transform_frame(
    image,
    mode: str,
    output_size: tuple[int, int] = (960, 540),
):
    if normalize_view_mode(mode) == "zoom":
        return fit_zoom(image, output_size)
    return fit_full(image, output_size)

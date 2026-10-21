"""Immutable PNG originals plus bounded previews usable across SSH."""
import base64
import io
import json
import warnings
from pathlib import Path
from document import digest, atomic_write_bytes
from storage import safe_cache


def save_plot(workspace, folder, encoded):
    return save_image(workspace, folder, base64.b64decode(encoded, validate=True))


def save_image(workspace, folder, data, *, category="outputs"):
    from PIL import Image
    if len(data) > 8_000_000:
        raise ValueError("Image exceeds 8 MB.")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            source = Image.open(io.BytesIO(data))
            if source.width * source.height > 24_000_000:
                raise ValueError("Plot exceeds 24 million pixels. Reduce figure size.")
            source.load()
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
            raise ValueError("Plot dimensions exceed the preview limit.") from error
    from PIL import ImageOps
    source = ImageOps.exif_transpose(source).convert("RGBA")
    normalized = io.BytesIO()
    source.save(normalized, format="PNG")
    data = normalized.getvalue()
    if len(data) > 32_000_000:
        raise ValueError("Decoded image exceeds the 32 MB saved-image limit. Resize it first.")
    prefix = digest(base64.b64encode(data).decode())[:24]
    image = safe_cache(workspace, category, folder.name, prefix + ".png")
    preview = safe_cache(workspace, category, folder.name, prefix + "-preview.png")
    # Content-addressed files are never rewritten after creation.
    if not image.exists() or image.read_bytes() != data:
        atomic_write_bytes(image, data)
    thumb = source.convert("RGBA")
    thumb.thumbnail((2048, 2048))
    while True:
        buf = io.BytesIO()
        thumb.save(buf, format="PNG", optimize=True)
        if buf.tell() <= 1_900_000:
            break
        thumb.thumbnail((max(1, thumb.width // 2), max(1, thumb.height // 2)))
    if not preview.exists() or preview.read_bytes() != buf.getvalue():
        atomic_write_bytes(preview, buf.getvalue())
    preview_width, preview_height = thumb.size
    pixels = safe_cache(workspace, category, folder.name, prefix + "-pixels.json")
    thumb.thumbnail((96, 96))
    packed = json.dumps({"width": thumb.width, "height": thumb.height, "rgba": thumb.tobytes().hex()}).encode()
    if not pixels.exists() or pixels.read_bytes() != packed:
        atomic_write_bytes(pixels, packed)
    return image, {"width": source.width, "height": source.height, "preview": str(preview), "preview_width": preview_width, "preview_height": preview_height, "pixels": str(pixels)}

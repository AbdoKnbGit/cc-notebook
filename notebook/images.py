"""Immutable PNG originals plus bounded previews usable across SSH."""
import base64
import io
import warnings
from pathlib import Path
from document import digest, atomic_write_bytes
from storage import safe_cache


def save_plot(workspace, folder, encoded):
    from PIL import Image
    data = base64.b64decode(encoded, validate=True)
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Expected PNG data.")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            source = Image.open(io.BytesIO(data))
            if source.width * source.height > 24_000_000:
                raise ValueError("Plot exceeds 24 million pixels. Reduce figure size.")
            source.load()
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
            raise ValueError("Plot dimensions exceed the preview limit.") from error
    prefix = digest(encoded)[:24]
    image = safe_cache(workspace, "outputs", folder.name, prefix + ".png")
    preview = safe_cache(workspace, "outputs", folder.name, prefix + "-preview.png")
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
    return image, {"width": source.width, "height": source.height, "preview": str(preview), "preview_width": thumb.width, "preview_height": thumb.height}

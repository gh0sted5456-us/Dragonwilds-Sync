from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageFile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = PROJECT_ROOT / "renderer" / "assets"
ImageFile.LOAD_TRUNCATED_IMAGES = True
LOSSLESS_GROUPS = {"guided", "navigation", "platforms", "rsdw-toolkit"}
LOSSLESS_ROOT_NAMES = {"application-icon.png", "singleplayer-icon.png"}
ANIMATED_SPLASH = ASSET_ROOT / "theme" / "animated-splash.webp"


def _webp_frame_durations(payload: bytes) -> list[int]:
    """Read ANMF durations because Pillow does not expose animated WebP timing."""
    durations: list[int] = []
    offset = 12
    while offset + 8 <= len(payload):
        kind = payload[offset:offset + 4]
        size = int.from_bytes(payload[offset + 4:offset + 8], "little")
        chunk = payload[offset + 8:offset + 8 + size]
        if kind == b"ANMF" and len(chunk) >= 16:
            durations.append(int.from_bytes(chunk[12:15], "little"))
        offset += 8 + size + (size & 1)
    return durations


def optimize_animated_splash() -> int:
    """Keep the splash animation while dropping redundant high-FPS frames."""
    if not ANIMATED_SPLASH.is_file():
        raise FileNotFoundError(f"Animated splash is missing: {ANIMATED_SPLASH}")
    original = ANIMATED_SPLASH.read_bytes()
    durations = _webp_frame_durations(original)
    with Image.open(ANIMATED_SPLASH) as source:
        frame_count = int(getattr(source, "n_frames", 1))
        if frame_count < 2:
            raise RuntimeError("The splash asset is no longer animated.")
        if len(durations) != frame_count:
            durations = [33] * frame_count
        frames: list[Image.Image] = []
        merged_durations: list[int] = []
        for index in range(0, frame_count, 2):
            source.seek(index)
            frames.append(source.convert("RGBA").copy())
            merged_durations.append(sum(durations[index:index + 2]))
    output = BytesIO()
    frames[0].save(
        output,
        format="WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=merged_durations,
        loop=0,
        quality=72,
        method=6,
        minimize_size=True,
    )
    payload = output.getvalue()
    if len(payload) >= len(original):
        raise RuntimeError("Animated splash optimization did not reduce its size.")
    pending = ANIMATED_SPLASH.with_suffix(".webp.pending")
    pending.write_bytes(payload)
    pending.replace(ANIMATED_SPLASH)
    print(
        f"Optimized animated splash: {frame_count} -> {len(frames)} frames, "
        f"{len(original) / 1048576:.2f} MiB -> {len(payload) / 1048576:.2f} MiB"
    )
    return 0


def _webp_bytes(path: Path) -> tuple[bytes, str]:
    relative = path.relative_to(ASSET_ROOT)
    lossless = relative.parts[0] in LOSSLESS_GROUPS or relative.name in LOSSLESS_ROOT_NAMES
    with Image.open(path) as source:
        source.load()
        output = BytesIO()
        options: dict[str, object] = {"format": "WEBP", "method": 4}
        if lossless:
            options["lossless"] = True
        else:
            options["quality"] = 86
        if source.info.get("icc_profile"):
            options["icc_profile"] = source.info["icc_profile"]
        source.save(output, **options)
    return output.getvalue(), "lossless" if lossless else "quality-86"


def convert() -> int:
    pngs = sorted(ASSET_ROOT.rglob("*.png"))
    original = 0
    converted = 0
    for source in pngs:
        payload, mode = _webp_bytes(source)
        destination = source.with_suffix(".webp")
        pending = destination.with_suffix(".webp.pending")
        pending.write_bytes(payload)
        pending.replace(destination)
        original += source.stat().st_size
        converted += len(payload)
        source.unlink()
        print(f"{source.relative_to(PROJECT_ROOT)} -> {destination.relative_to(PROJECT_ROOT)} ({mode})")
    saved = original - converted
    percent = (saved / original * 100.0) if original else 0.0
    print(f"Converted {len(pngs)} PNG assets: {original / 1048576:.2f} MiB -> {converted / 1048576:.2f} MiB ({percent:.1f}% smaller)")
    return 0


def check() -> int:
    remaining = sorted(ASSET_ROOT.rglob("*.png"))
    if remaining:
        print("Packaged PNG assets must be optimized to WebP:")
        for path in remaining:
            print(path.relative_to(PROJECT_ROOT))
        return 1
    print("Packaged raster asset contract: PASS (WebP/SVG with Windows ICO retained)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Optimize packaged Dragonwilds Sync raster assets.")
    parser.add_argument("--check", action="store_true", help="Fail if packaged PNG assets remain.")
    parser.add_argument("--optimize-animation", action="store_true", help="Reduce redundant frames in the packaged splash WebP.")
    args = parser.parse_args()
    if args.check:
        return check()
    if args.optimize_animation:
        return optimize_animated_splash()
    return convert()


if __name__ == "__main__":
    raise SystemExit(main())

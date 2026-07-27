from __future__ import annotations

from pathlib import Path

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = PROJECT_ROOT / "assets" / "character_spritesheet_source.png"
OUTPUT_PATH = PROJECT_ROOT / "assets" / "character_spritesheet.png"
ICON_PATH = PROJECT_ROOT / "assets" / "pet.ico"

CELL_WIDTH = 256
CELL_HEIGHT = 320
BOTTOM_PADDING = 8

# 原图是自由排版的 4×3：角色会跨过 256px 边界，三行高度也不相同。
# 这些边界位于相邻角色之间的透明区域中，用来完整分离每一帧。
SOURCE_ROWS = (
    (0, 336, (0, 291, 528, 761, 1024)),
    (336, 656, (0, 255, 496, 735, 1024)),
    (656, 1024, (0, 257, 502, 762, 1024)),
)


def normalized_frame(source: Image.Image, bounds: tuple[int, int, int, int]) -> Image.Image:
    frame = source.crop(bounds)
    alpha_bounds = frame.getchannel("A").getbbox()
    if alpha_bounds is None:
        raise ValueError(f"空白帧: {bounds}")
    frame = frame.crop(alpha_bounds)

    max_width = CELL_WIDTH - 8
    max_height = CELL_HEIGHT - BOTTOM_PADDING - 4
    scale = min(1.0, max_width / frame.width, max_height / frame.height)
    if scale < 1.0:
        frame = frame.resize(
            (round(frame.width * scale), round(frame.height * scale)),
            Image.Resampling.LANCZOS,
        )

    cell = Image.new("RGBA", (CELL_WIDTH, CELL_HEIGHT), (0, 0, 0, 0))
    x = (CELL_WIDTH - frame.width) // 2
    y = CELL_HEIGHT - BOTTOM_PADDING - frame.height
    cell.alpha_composite(frame, (x, y))
    return cell


def main() -> None:
    source = Image.open(SOURCE_PATH).convert("RGBA")
    if source.size != (1024, 1024):
        raise ValueError(f"素材尺寸应为 1024×1024，实际为 {source.size}")

    output = Image.new(
        "RGBA",
        (CELL_WIDTH * 4, CELL_HEIGHT * 3),
        (0, 0, 0, 0),
    )

    for row_index, (top, bottom, x_edges) in enumerate(SOURCE_ROWS):
        for column_index in range(4):
            bounds = (
                x_edges[column_index],
                top,
                x_edges[column_index + 1],
                bottom,
            )
            frame = normalized_frame(source, bounds)
            output.alpha_composite(
                frame,
                (column_index * CELL_WIDTH, row_index * CELL_HEIGHT),
            )

    output.save(OUTPUT_PATH, optimize=True)
    print(f"已生成: {OUTPUT_PATH} ({output.width}×{output.height})")

    first_frame = output.crop((0, 0, CELL_WIDTH, CELL_HEIGHT))
    icon_canvas = Image.new("RGBA", (320, 320), (0, 0, 0, 0))
    icon_canvas.alpha_composite(first_frame, ((320 - CELL_WIDTH) // 2, 0))
    icon_canvas.save(
        ICON_PATH,
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"已生成: {ICON_PATH}")


if __name__ == "__main__":
    main()

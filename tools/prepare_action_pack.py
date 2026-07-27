from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = PROJECT_ROOT / "assets"
OUTPUT_PATH = ASSETS_DIR / "character_spritesheet.png"

CELL_WIDTH = 256
CELL_HEIGHT = 320
BOTTOM_PADDING = 8
COLUMNS = 4


@dataclass(frozen=True)
class AtlasRow:
    source_name: str
    source_row: int
    layout: str = "normal"
    source_rows: int = 4
    scale: float = 1.0


# Atlas layout used by assets/sprite_manifest.json.
ATLAS_ROWS = (
    AtlasRow("character_unified_actions.png", 0),  # idle
    AtlasRow("character_unified_actions.png", 1),  # walk
    AtlasRow("character_interactions.png", 0),  # click 1-4
    AtlasRow("character_interactions.png", 1),  # click 5-8
    AtlasRow("character_extra_actions_keyed.png", 0),  # gentle idle
    AtlasRow("character_interactions.png", 2),  # wave 1-4
    AtlasRow("character_interactions.png", 3),  # wave 5-8
    AtlasRow("character_unified_actions.png", 3),  # shy
    AtlasRow("character_extra_actions_keyed.png", 3),  # sleepy
    AtlasRow("character_edge_peek_v2.png", 0, "edge_left"),  # left enter
    AtlasRow("character_edge_peek_v2.png", 1, "edge_left"),  # left loop
    AtlasRow("character_edge_peek_v2.png", 2, "edge_right"),  # right enter
    AtlasRow("character_edge_peek_v2.png", 3, "edge_right"),  # right loop
    AtlasRow("character_sleep_actions.png", 0, "sleep_anchor"),  # sit down
    AtlasRow("character_sleep_actions.png", 1, "sleep_anchor"),  # doze off
    AtlasRow("character_sleep_actions.png", 2, "sleep_anchor"),  # sleep loop
    AtlasRow("character_sleep_actions.png", 3, "sleep_anchor"),  # wake up
    AtlasRow("character_drag_actions.png", 0),  # grab and lift
    AtlasRow("character_drag_actions.png", 1),  # held while dragging
    AtlasRow("character_drag_actions.png", 2),  # release and fall
    AtlasRow("character_drag_actions.png", 3),  # soft landing
    AtlasRow("character_run_actions.png", 0, source_rows=2, scale=0.75),  # run 1-4
    AtlasRow("character_run_actions.png", 1, source_rows=2, scale=0.75),  # run 5-8
    AtlasRow("character_peek_exit.png", 0, "peek_exit", source_rows=2, scale=0.90),
    AtlasRow("character_peek_exit.png", 1, "peek_exit", source_rows=2, scale=0.90),
)


def _source_cell(
    image: Image.Image,
    row: int,
    column: int,
    source_rows: int,
) -> Image.Image:
    x_edges = [round(index * image.width / COLUMNS) for index in range(COLUMNS + 1)]
    y_edges = [
        round(index * image.height / source_rows)
        for index in range(source_rows + 1)
    ]
    return image.crop(
        (
            x_edges[column],
            y_edges[row],
            x_edges[column + 1],
            y_edges[row + 1],
        )
    )


def _normalize_frame(
    frame: Image.Image,
    layout: str,
    scale: float,
    frame_index: int,
) -> Image.Image:
    frame = frame.convert("RGBA")
    if layout == "normal":
        # Generated sheets can let a few pixels from the neighbouring cell cross
        # the mathematical grid boundary. Keep the dominant horizontal subject
        # run so one stray lock of hair cannot shrink the whole frame.
        alpha = frame.getchannel("A")
        x_projection, _ = alpha.getprojection()
        runs: list[tuple[int, int]] = []
        start: int | None = None
        for x, occupied in enumerate(x_projection):
            if occupied and start is None:
                start = x
            elif not occupied and start is not None:
                runs.append((start, x))
                start = None
        if start is not None:
            runs.append((start, frame.width))
        if runs:
            run = max(
                runs,
                key=lambda bounds: sum(
                    value * count
                    for value, count in enumerate(
                        alpha.crop(
                            (bounds[0], 0, bounds[1], alpha.height)
                        ).histogram()
                    )
                ),
            )
            frame = frame.crop((run[0], 0, run[1], frame.height))

    alpha = frame.getchannel("A")
    alpha_bounds = alpha.getbbox()
    if alpha_bounds is None:
        raise ValueError("动作素材中存在空白帧")
    if layout == "sleep_anchor":
        meaningful_bottom = _meaningful_alpha_bottom(alpha)
        alpha_bounds = (
            alpha_bounds[0],
            alpha_bounds[1],
            alpha_bounds[2],
            min(alpha_bounds[3], meaningful_bottom),
        )
    frame = frame.crop(alpha_bounds)

    # Sleep bubbles and isolated antialias pixels must not move the character.
    # Keep them visible, but calculate placement from the central 94% of the
    # opaque subject mass so only the actual character controls the anchor.
    robust_bounds: tuple[int, int, int, int] | None = None
    if layout == "sleep_anchor":
        robust_bounds = _robust_alpha_bounds(frame.getchannel("A"))

    # Never fit every frame independently.  Doing so makes compact poses such
    # as sitting, dozing and landing grow larger than standing poses.  Each
    # source pack now has one fixed scale, so head/body size remains stable
    # throughout an animation and only the pose silhouette changes.
    max_width = CELL_WIDTH - 8
    max_height = CELL_HEIGHT - 12
    if scale <= 0:
        raise ValueError("动作素材缩放比例必须大于 0")
    if frame.width * scale > max_width or frame.height * scale > max_height:
        raise ValueError(
            "动作素材超出单元格；请为整套素材统一调小 scale，"
            f"不要单独缩放当前帧 ({frame.width}×{frame.height}, scale={scale})"
        )
    frame = frame.resize(
        (round(frame.width * scale), round(frame.height * scale)),
        Image.Resampling.LANCZOS,
    )

    cell = Image.new("RGBA", (CELL_WIDTH, CELL_HEIGHT), (0, 0, 0, 0))
    if layout == "normal":
        x = (CELL_WIDTH - frame.width) // 2
        y = CELL_HEIGHT - BOTTOM_PADDING - frame.height
    elif layout == "sleep_anchor":
        if robust_bounds is None:
            raise ValueError("睡眠帧缺少主体锚点")
        left, _top, right, _bottom = robust_bounds
        robust_center_x = (left + right) / 2 * scale
        x = round(CELL_WIDTH / 2 - robust_center_x)
        y = CELL_HEIGHT - BOTTOM_PADDING - frame.height
    elif layout == "edge_left":
        x = 4
        y = (CELL_HEIGHT - frame.height) // 2
    elif layout == "edge_right":
        x = CELL_WIDTH - 4 - frame.width
        y = (CELL_HEIGHT - frame.height) // 2
    elif layout == "edge_top":
        x = (CELL_WIDTH - frame.width) // 2
        y = 4
    elif layout == "peek_exit":
        # The first two frames stay attached to the screen boundary. Later
        # frames settle toward the middle while a small vertical arc sells the
        # hop without changing character scale.
        x = 0 if frame_index < 2 else (CELL_WIDTH - frame.width) // 2
        hop_offsets = (0, 0, -4, -14, -20, -10, -3, 0)
        y = CELL_HEIGHT - BOTTOM_PADDING - frame.height + hop_offsets[frame_index]
    else:
        raise ValueError(f"未知布局: {layout}")

    cell.alpha_composite(frame, (x, y))
    return cell


def _robust_alpha_bounds(alpha: Image.Image) -> tuple[int, int, int, int]:
    width, height = alpha.size
    x_counts = [0] * width
    y_counts = [0] * height
    total = 0
    pixels = alpha.load()
    for y in range(height):
        for x in range(width):
            if pixels[x, y] >= 32:
                x_counts[x] += 1
                y_counts[y] += 1
                total += 1
    if total == 0:
        raise ValueError("动作素材中不存在有效主体像素")

    trim = max(1, round(total * 0.03))

    def lower_bound(counts: list[int]) -> int:
        accumulated = 0
        for index, count in enumerate(counts):
            accumulated += count
            if accumulated >= trim:
                return index
        return 0

    def upper_bound(counts: list[int]) -> int:
        accumulated = 0
        for index in range(len(counts) - 1, -1, -1):
            accumulated += counts[index]
            if accumulated >= trim:
                return index + 1
        return len(counts)

    return (
        lower_bound(x_counts),
        lower_bound(y_counts),
        upper_bound(x_counts),
        upper_bound(y_counts),
    )


def _meaningful_alpha_bottom(alpha: Image.Image) -> int:
    width, height = alpha.size
    pixels = alpha.load()
    minimum_row_pixels = max(4, round(width * 0.01))
    for y in range(height - 1, -1, -1):
        occupied = sum(1 for x in range(width) if pixels[x, y] >= 32)
        if occupied >= minimum_row_pixels:
            return y + 1
    raise ValueError("动作素材中不存在有效主体底部")


def main() -> None:
    sources: dict[str, Image.Image] = {}
    for row in ATLAS_ROWS:
        if row.source_name not in sources:
            source_path = ASSETS_DIR / row.source_name
            sources[row.source_name] = Image.open(source_path).convert("RGBA")

    output = Image.new(
        "RGBA",
        (CELL_WIDTH * COLUMNS, CELL_HEIGHT * len(ATLAS_ROWS)),
        (0, 0, 0, 0),
    )

    for output_row, row in enumerate(ATLAS_ROWS):
        source = sources[row.source_name]
        for column in range(COLUMNS):
            frame_index = row.source_row * COLUMNS + column
            frame = _normalize_frame(
                _source_cell(
                    source,
                    row.source_row,
                    column,
                    row.source_rows,
                ),
                row.layout,
                row.scale,
                frame_index,
            )
            output.alpha_composite(
                frame,
                (column * CELL_WIDTH, output_row * CELL_HEIGHT),
            )

    output.save(OUTPUT_PATH, optimize=True)
    print(f"已生成统一帧表: {OUTPUT_PATH} ({output.width}×{output.height})")


if __name__ == "__main__":
    main()

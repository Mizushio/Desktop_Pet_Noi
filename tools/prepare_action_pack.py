from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps


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
    subject_scale: float = 1.0
    x_offsets: tuple[int, int, int, int] = (0, 0, 0, 0)


# Atlas layout used by assets/sprite_manifest.json.
ATLAS_ROWS = (
    # v0.10 uses one visual-size standard across packs.  Generated source
    # sheets have slightly different native character scales, so each pack is
    # normalized here instead of resizing frames independently at runtime.
    # Keep the character anchored while the surprise marks and sigh bubble
    # appear. These two source drawings otherwise sit slightly to the right.
    AtlasRow(
        "character_unified_actions.png",
        0,
        scale=0.965,
    ),  # idle / surprise / sigh
    AtlasRow("character_unified_actions.png", 1, scale=0.725),  # walk
    AtlasRow("character_interactions.png", 0, scale=0.97),  # click 1-4
    AtlasRow("character_interactions.png", 1, scale=0.97),  # click 5-8
    AtlasRow("character_extra_actions_keyed.png", 0, scale=0.975),  # gentle idle
    # 0.97 made the waving body 8-15 px shorter than the neutral idle pose.
    AtlasRow("character_interactions.png", 2, scale=1.005),  # wave 1-4
    AtlasRow("character_interactions.png", 3, scale=1.005),  # wave 5-8
    AtlasRow("character_unified_actions.png", 3, scale=0.965),  # shy
    AtlasRow("character_extra_actions_keyed.png", 3, scale=0.99),  # sleepy
    AtlasRow("character_edge_peek_v2.png", 0, "edge_left", scale=0.97),
    AtlasRow("character_edge_peek_v2.png", 1, "edge_left", scale=0.97),
    # The old right-side drawings were visibly smaller than the left-side
    # drawings. Build the right side from the same artwork so both edges have
    # exactly the same scale, line weight and timing.
    AtlasRow("character_edge_peek_v2.png", 0, "edge_right_mirror", scale=0.97),
    AtlasRow("character_edge_peek_v2.png", 1, "edge_right_mirror", scale=0.97),
    AtlasRow("character_sleep_actions.png", 0, "sleep_anchor", scale=0.96),
    AtlasRow("character_sleep_actions.png", 1, "sleep_anchor", scale=0.96),
    AtlasRow("character_sleep_actions.png", 2, "sleep_anchor", scale=0.96),
    AtlasRow("character_sleep_actions.png", 3, "sleep_anchor", scale=0.96),
    AtlasRow("character_drag_actions.png", 0, scale=1.00),
    AtlasRow("character_drag_actions.png", 1, scale=1.068),
    # The release row contains a separate hand above the character. Enlarge
    # only the character so the hand still fits in the cell and the pet does
    # not shrink while being dropped.
    AtlasRow(
        "character_drag_actions.png",
        2,
        scale=0.96,
        subject_scale=1.22,
    ),
    # Generated landing drawings used a smaller native character. Bring the
    # final standing frame back to the shared 260 px visual height.
    AtlasRow("character_drag_actions.png", 3, scale=1.20),
    AtlasRow("character_run_actions.png", 0, source_rows=2, scale=0.725),
    AtlasRow("character_run_actions.png", 1, source_rows=2, scale=0.725),
    AtlasRow("character_peek_exit.png", 0, "peek_exit", source_rows=2, scale=0.87),
    AtlasRow("character_peek_exit.png", 1, "peek_exit", source_rows=2, scale=0.87),
    AtlasRow("character_gaze_actions.png", 0, scale=0.70, source_rows=2),
    AtlasRow("character_gaze_actions.png", 1, scale=0.70, source_rows=2),
    AtlasRow("character_time_actions.png", 0, scale=0.77, source_rows=3),
    AtlasRow("character_time_actions.png", 1, scale=0.77, source_rows=3),
    AtlasRow("character_time_actions.png", 2, scale=0.77, source_rows=3),
    AtlasRow("character_angry_actions.png", 0, scale=0.82, source_rows=3),
    AtlasRow("character_angry_actions.png", 1, scale=0.82, source_rows=3),
    AtlasRow("character_angry_actions.png", 2, scale=0.82, source_rows=3),
    AtlasRow("character_cute_actions.png", 0, scale=0.97),  # slow heart
    AtlasRow("character_cute_actions.png", 1, scale=0.97),  # seated leg swing
    AtlasRow("character_cute_actions.png", 2, scale=0.97),  # small curtsey
    AtlasRow("character_cute_actions.png", 3, scale=0.97),  # cheek puff / tilt
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
    subject_scale: float,
    frame_index: int,
    x_offset: int,
) -> Image.Image:
    frame = frame.convert("RGBA")
    if layout.endswith("_mirror"):
        frame = ImageOps.mirror(frame)
        layout = layout.removesuffix("_mirror")
    if layout == "normal":
        # Generated grids sometimes leak a tiny outline from the neighbouring
        # row into the first/last scanlines of a cell.  That fragment used to
        # become the "foot" anchor, lifting the real character by tens of
        # pixels at the start of the wave animation.  Remove only small
        # connected components that touch a mathematical cell edge; the main
        # character and deliberate floating hearts remain intact.
        frame = _remove_small_edge_components(frame)

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
    if subject_scale != 1.0:
        frame = _scale_dominant_component(frame, subject_scale)
    if frame.width > CELL_WIDTH or frame.height > CELL_HEIGHT:
        raise ValueError(
            "主体校正后超出单元格: "
            f"{frame.width}×{frame.height}，允许 {CELL_WIDTH}×{CELL_HEIGHT}"
        )

    cell = Image.new("RGBA", (CELL_WIDTH, CELL_HEIGHT), (0, 0, 0, 0))
    if layout == "normal":
        # Anchor the actual character, not the full alpha rectangle. Floating
        # hearts, question marks, sigh puffs and anger marks must stay visible
        # without pushing the character sideways or upward.
        left, _top, right, bottom = _dominant_component_bounds(
            frame.getchannel("A")
        )
        x = round(CELL_WIDTH / 2 - (left + right) / 2)
        y = CELL_HEIGHT - BOTTOM_PADDING - bottom
    elif layout == "sleep_anchor":
        left, _top, right, bottom = _dominant_component_bounds(
            frame.getchannel("A")
        )
        x = round(CELL_WIDTH / 2 - (left + right) / 2)
        y = CELL_HEIGHT - BOTTOM_PADDING - bottom
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

    x += x_offset
    cell.alpha_composite(frame, (x, y))
    return cell


def _remove_small_edge_components(frame: Image.Image) -> Image.Image:
    alpha = frame.getchannel("A")
    width, height = alpha.size
    pixels = alpha.load()
    visited = bytearray(width * height)
    components: list[tuple[list[tuple[int, int]], bool]] = []

    for start_y in range(height):
        for start_x in range(width):
            offset = start_y * width + start_x
            if visited[offset] or pixels[start_x, start_y] < 8:
                continue

            stack = [(start_x, start_y)]
            visited[offset] = 1
            component: list[tuple[int, int]] = []
            touches_edge = False
            while stack:
                x, y = stack.pop()
                component.append((x, y))
                if x <= 1 or y <= 1 or x >= width - 2 or y >= height - 2:
                    touches_edge = True
                for next_y in range(max(0, y - 1), min(height, y + 2)):
                    for next_x in range(max(0, x - 1), min(width, x + 2)):
                        next_offset = next_y * width + next_x
                        if (
                            not visited[next_offset]
                            and pixels[next_x, next_y] >= 8
                        ):
                            visited[next_offset] = 1
                            stack.append((next_x, next_y))
            components.append((component, touches_edge))

    if not components:
        return frame

    largest_area = max(len(component) for component, _ in components)
    removable_limit = max(48, round(largest_area * 0.02))
    cleaned_alpha = alpha.copy()
    cleaned_pixels = cleaned_alpha.load()
    changed = False
    for component, touches_edge in components:
        if not touches_edge or len(component) >= removable_limit:
            continue
        changed = True
        left = max(0, min(x for x, _ in component) - 1)
        top = max(0, min(y for _, y in component) - 1)
        right = min(width, max(x for x, _ in component) + 2)
        bottom = min(height, max(y for _, y in component) + 2)
        for y in range(top, bottom):
            for x in range(left, right):
                cleaned_pixels[x, y] = 0

    if not changed:
        return frame
    cleaned = frame.copy()
    cleaned.putalpha(cleaned_alpha)
    return cleaned


def _alpha_components(
    alpha: Image.Image,
    *,
    threshold: int = 8,
) -> list[list[tuple[int, int]]]:
    width, height = alpha.size
    pixels = alpha.load()
    visited = bytearray(width * height)
    components: list[list[tuple[int, int]]] = []
    for start_y in range(height):
        for start_x in range(width):
            offset = start_y * width + start_x
            if visited[offset] or pixels[start_x, start_y] < threshold:
                continue
            visited[offset] = 1
            stack = [(start_x, start_y)]
            component: list[tuple[int, int]] = []
            while stack:
                x, y = stack.pop()
                component.append((x, y))
                for next_y in range(max(0, y - 1), min(height, y + 2)):
                    for next_x in range(max(0, x - 1), min(width, x + 2)):
                        next_offset = next_y * width + next_x
                        if (
                            not visited[next_offset]
                            and pixels[next_x, next_y] >= threshold
                        ):
                            visited[next_offset] = 1
                            stack.append((next_x, next_y))
            components.append(component)
    return components


def _dominant_component_bounds(alpha: Image.Image) -> tuple[int, int, int, int]:
    components = _alpha_components(alpha, threshold=32)
    if not components:
        raise ValueError("动作素材中不存在有效主体像素")
    component = max(components, key=len)
    xs = [point[0] for point in component]
    ys = [point[1] for point in component]
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def _scale_dominant_component(frame: Image.Image, factor: float) -> Image.Image:
    if factor <= 0:
        raise ValueError("主体缩放比例必须大于 0")
    if factor == 1.0:
        return frame

    alpha = frame.getchannel("A")
    components = _alpha_components(alpha)
    if not components:
        raise ValueError("动作素材中不存在可缩放的主体")
    subject = max(components, key=len)
    left = min(point[0] for point in subject)
    top = min(point[1] for point in subject)
    right = max(point[0] for point in subject) + 1
    bottom = max(point[1] for point in subject) + 1

    mask = Image.new("L", frame.size, 0)
    mask_pixels = mask.load()
    alpha_pixels = alpha.load()
    for x, y in subject:
        mask_pixels[x, y] = alpha_pixels[x, y]

    subject_image = frame.copy()
    subject_image.putalpha(mask)
    subject_image = subject_image.crop((left, top, right, bottom))
    scaled_subject = subject_image.resize(
        (
            round(subject_image.width * factor),
            round(subject_image.height * factor),
        ),
        Image.Resampling.LANCZOS,
    )

    remainder = frame.copy()
    remainder_alpha = remainder.getchannel("A")
    remainder_pixels = remainder_alpha.load()
    for x, y in subject:
        remainder_pixels[x, y] = 0
    remainder.putalpha(remainder_alpha)

    target_width = max(frame.width, scaled_subject.width)
    target_height = max(frame.height, scaled_subject.height)
    result = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))
    base_x = (target_width - frame.width) // 2
    base_y = target_height - frame.height
    result.alpha_composite(remainder, (base_x, base_y))
    result.alpha_composite(
        scaled_subject,
        (
            round(target_width / 2 - scaled_subject.width / 2),
            target_height - scaled_subject.height,
        ),
    )
    return result


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
                row.subject_scale,
                frame_index,
                row.x_offsets[column],
            )
            output.alpha_composite(
                frame,
                (column * CELL_WIDTH, output_row * CELL_HEIGHT),
            )

    output.save(OUTPUT_PATH, optimize=True)
    print(f"已生成统一帧表: {OUTPUT_PATH} ({output.width}×{output.height})")


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "assets" / "sprite_manifest.json"


@dataclass(frozen=True)
class FrameMetrics:
    center_x: float
    top: int
    bottom: int
    width: int
    height: int
    top_run_width: int
    top_pixel_count: int


def alpha_components(
    alpha: Image.Image,
    *,
    threshold: int = 32,
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


def dominant_metrics(frame: Image.Image) -> FrameMetrics:
    components = alpha_components(frame.getchannel("A"))
    if not components:
        raise ValueError("帧中不存在有效角色主体")
    subject = max(components, key=len)
    xs = [point[0] for point in subject]
    ys = [point[1] for point in subject]
    left, right = min(xs), max(xs) + 1
    top, bottom = min(ys), max(ys) + 1
    top_xs = [x for x, y in subject if y == top]
    return FrameMetrics(
        center_x=(left + right) / 2,
        top=top,
        bottom=bottom,
        width=right - left,
        height=bottom - top,
        top_run_width=max(top_xs) - min(top_xs) + 1,
        top_pixel_count=len(top_xs),
    )


def character_core_center_x(frame: Image.Image) -> float:
    alpha = frame.getchannel("A")
    components = alpha_components(alpha)
    if not components:
        raise ValueError("帧中不存在有效角色主体")
    subject = max(components, key=len)
    top = min(y for _x, y in subject)
    bottom = max(y for _x, y in subject) + 1
    cutoff = top + round((bottom - top) * 0.52)
    core = [(x, y) for x, y in subject if y < cutoff]
    pixels = alpha.load()
    total_alpha = sum(pixels[x, y] for x, y in core)
    return sum(x * pixels[x, y] for x, y in core) / total_alpha


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    sheet_name = os.environ.get("PET_SPRITESHEET", manifest["spritesheet"])
    sheet = Image.open(MANIFEST_PATH.parent / sheet_name).convert("RGBA")
    actions = manifest["actions"]

    def frame(rect: list[int]) -> Image.Image:
        x, y, width, height = rect
        return sheet.crop((x, y, x + width, y + height))

    def action_metrics(name: str) -> list[FrameMetrics]:
        return [dominant_metrics(frame(rect)) for rect in actions[name]["frames"]]

    failures: list[str] = []
    idle_frame = actions["idle"]["frames"][0]
    idle = dominant_metrics(frame(idle_frame))

    neutral_transition_actions = (
        "click",
        "cute_idle",
        "wave",
        "shy",
        "sleepy",
        "heart",
        "sit_sway",
        "curtsey",
        "cheek_puff",
        "message_notify",
        "time_morning_motion",
        "time_day_motion",
        "time_night_motion",
    )
    for name in neutral_transition_actions:
        if actions[name]["frames"][0] != idle_frame:
            failures.append(f"{name}: 入口不是无表情待机帧")
        if actions[name]["frames"][-1] != idle_frame:
            failures.append(f"{name}: 出口不是无表情待机帧")

    centered_actions = (
        "idle_motion",
        "walk",
        "click",
        "cute_idle",
        "wave",
        "shy",
        "sleepy",
        "sit_down",
        "doze_off",
        "sleep",
        "wake",
        "time_morning_motion",
        "time_day_motion",
        "time_night_motion",
        "angry_enter",
        "angry_hold",
        "angry_calm",
        "heart",
        "sit_sway",
        "curtsey",
        "cheek_puff",
    )
    for name in centered_actions:
        metrics = action_metrics(name)
        center_span = max(item.center_x for item in metrics) - min(
            item.center_x for item in metrics
        )
        bottom_span = max(item.bottom for item in metrics) - min(
            item.bottom for item in metrics
        )
        if center_span > 1.5:
            failures.append(f"{name}: 主体横向漂移 {center_span:.1f}px")
        if bottom_span > 1:
            failures.append(f"{name}: 落地点漂移 {bottom_span}px")

    message_actions = (
        "message_notify_enter",
        "message_notify_hold",
        "message_notify_exit",
        "message_notify",
    )
    message_cores = [
        character_core_center_x(frame(rect))
        for name in message_actions
        for rect in actions[name]["frames"]
    ]
    if max(message_cores) - min(message_cores) > 1.5:
        failures.append(
            "message_notify: 头部/躯干核心横向漂移 "
            f"{max(message_cores) - min(message_cores):.1f}px"
        )
    message_bottoms = [
        dominant_metrics(frame(rect)).bottom
        for name in message_actions
        for rect in actions[name]["frames"]
    ]
    if max(message_bottoms) - min(message_bottoms) > 1:
        failures.append(
            "message_notify: 落地点漂移 "
            f"{max(message_bottoms) - min(message_bottoms)}px"
        )

    comparable_actions = (
        "walk",
        "click",
        "cute_idle",
        "wave",
        "shy",
        "sleepy",
        "time_morning_motion",
        "time_day_motion",
        "time_night_motion",
        "angry_enter",
        "angry_hold",
        "angry_calm",
        "heart",
        "curtsey",
        "cheek_puff",
        "message_notify_enter",
        "message_notify_exit",
        "message_notify",
    )
    for name in comparable_actions:
        tallest = max(item.height for item in action_metrics(name))
        if abs(tallest - idle.height) > 6:
            failures.append(
                f"{name}: 站立尺度 {tallest}px，与待机 {idle.height}px 不一致"
            )

    # The active wave frames must preserve both the neutral vertical anchor and
    # the rounded head/headband contour.  A generated row once crossed its
    # source-grid boundary; the old height-only test passed even though the
    # missing top pixels left a conspicuously flat crop.
    wave_metrics = action_metrics("wave")[1:-1]
    wave_top_span = max(item.top for item in wave_metrics) - min(
        item.top for item in wave_metrics
    )
    wave_height_span = max(item.height for item in wave_metrics) - min(
        item.height for item in wave_metrics
    )
    if wave_top_span > 2:
        failures.append(f"wave: 头顶纵向漂移 {wave_top_span}px")
    if wave_height_span > 2:
        failures.append(f"wave: 有效帧主体高度波动 {wave_height_span}px")
    for index, metrics in enumerate(wave_metrics, start=1):
        flat_top_limit = max(20, round(metrics.width * 0.15))
        if (
            metrics.top_run_width > flat_top_limit
            or metrics.top_pixel_count > flat_top_limit
        ):
            failures.append(
                f"wave: 第 {index} 个有效帧头顶呈截断直线 "
                f"({metrics.top_run_width}px/{metrics.top_pixel_count}px)"
            )

    landing_metrics = action_metrics("soft_land")
    if abs(landing_metrics[-2].height - idle.height) > 5:
        failures.append("soft_land: 站稳帧没有恢复普通待机尺度")

    for left_name, right_name in (
        ("peek_left_enter", "peek_right_enter"),
        ("peek_left", "peek_right"),
    ):
        for index, (left_rect, right_rect) in enumerate(
            zip(actions[left_name]["frames"], actions[right_name]["frames"])
        ):
            left = frame(left_rect).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            right = frame(right_rect)
            if ImageChops.difference(left, right).getbbox() is not None:
                failures.append(
                    f"{left_name}/{right_name}: 第 {index + 1} 帧不是严格镜像"
                )

    print(
        f"已检查 {sheet_name} 的 {len(actions)} 个动作；参考待机主体 "
        f"{idle.width}×{idle.height}px，中心 x={idle.center_x:.1f}。"
    )
    if failures:
        print("一致性检查失败：")
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)
    print(
        "主体尺度、水平/垂直锚点、头顶完整性、脚底基线、"
        "首尾过渡和左右探头均通过。"
    )


if __name__ == "__main__":
    main()

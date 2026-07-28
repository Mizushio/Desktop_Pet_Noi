from __future__ import annotations

import json
import math
import random
import sys
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSettings,
    QSize,
    Qt,
    QTimer,
)
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QCloseEvent,
    QContextMenuEvent,
    QCursor,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPixmap,
    QPolygon,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import QApplication, QMenu, QWidget


def resource_path(relative_path: str) -> Path:
    """Return a resource path in source mode and in a PyInstaller bundle."""
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return bundle_root / relative_path


@dataclass(frozen=True)
class Action:
    frames: tuple[QRect, ...]
    durations_ms: tuple[int, ...]
    loop: bool


@dataclass(frozen=True)
class PetConfig:
    spritesheet_path: Path
    frame_size: QSize
    display_size: QSize
    actions: dict[str, Action]
    move_interval_ms: int
    move_step_px: int
    auto_walk_delay_ms: tuple[int, int]
    auto_walk_duration_ms: tuple[int, int]
    auto_walk_default: bool
    click_actions: tuple[str, ...]
    random_idle_actions: tuple[str, ...]
    random_idle_weights: dict[str, float]
    random_idle_delay_ms: tuple[int, int]
    animation_render_interval_ms: int
    animation_tween_actions: frozenset[str]
    animation_tween_fraction: float
    sleep_enabled_default: bool
    inactivity_sleep_delay_ms: tuple[int, int]
    sleep_duration_ms: tuple[int, int]
    default_scale_percent: int
    scale_options_percent: tuple[int, ...]
    edge_snap_distance_px: int
    enabled_edges: tuple[str, ...]
    tuck_delay_ms: int
    tuck_animation_ms: int
    peek_motion_delay_ms: tuple[int, int]
    reveal_animation_ms: int
    desktop_layer_default: bool
    gaze_enabled_default: bool
    gaze_radius_px: int
    gaze_poll_interval_ms: int
    gaze_spontaneous_delay_ms: tuple[int, int]
    gaze_duration_ms: tuple[int, int]
    gaze_click_follow_duration_ms: int
    gaze_frames: dict[str, QRect]
    time_state_enabled_default: bool
    time_state_check_interval_ms: int
    workdays: tuple[int, ...]
    morning_start_minute: int
    work_start_minute: int
    lunch_start_minute: int
    lunch_end_minute: int
    work_end_minute: int
    night_start_minute: int
    time_visual_actions: dict[str, str]
    time_motion_actions: dict[str, str]
    anger_click_threshold: int
    anger_click_window_ms: int
    anger_duration_ms: int
    speech_enabled_default: bool
    speech_delay_ms: tuple[int, int]
    speech_bubble_duration_ms: int
    speech_phrases: dict[str, tuple[str, ...]]
    phase_transition_phrases: dict[str, str]

    @classmethod
    def load(cls, manifest_path: Path) -> "PetConfig":
        with manifest_path.open("r", encoding="utf-8") as file:
            raw: dict[str, Any] = json.load(file)

        actions: dict[str, Action] = {}
        for name, action_raw in raw["actions"].items():
            frames = tuple(QRect(*rect) for rect in action_raw["frames"])
            if not frames:
                raise ValueError(f"动作 {name!r} 没有帧")
            if "durations_ms" in action_raw:
                durations_ms = tuple(int(value) for value in action_raw["durations_ms"])
            else:
                durations_ms = (int(action_raw["interval_ms"]),) * len(frames)
            if len(durations_ms) != len(frames) or any(
                value <= 0 for value in durations_ms
            ):
                raise ValueError(f"动作 {name!r} 的逐帧时间配置无效")
            actions[name] = Action(
                frames=frames,
                durations_ms=durations_ms,
                loop=bool(action_raw["loop"]),
            )

        required = {
            "idle",
            "idle_motion",
            "walk",
            "walk_start",
            "walk_stop",
            "click",
            "cute_idle",
            "wave",
            "shy",
            "sleepy",
            "peek_left_enter",
            "peek_left",
            "peek_left_hold",
            "peek_left_exit",
            "peek_right_enter",
            "peek_right",
            "peek_right_hold",
            "peek_right_exit",
            "sit_down",
            "doze_off",
            "sleep",
            "wake",
            "grab_lift",
            "held_drag",
            "release_fall",
            "soft_land",
            "time_morning",
            "time_day",
            "time_night",
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
        }
        missing = required.difference(actions)
        if missing:
            raise ValueError(f"manifest 缺少动作: {', '.join(sorted(missing))}")

        interaction = raw["interaction"]
        click_actions = tuple(interaction["click_actions"])
        random_idle_actions = tuple(interaction["random_idle_actions"])
        referenced_actions = set(click_actions) | set(random_idle_actions)
        unknown = referenced_actions.difference(actions)
        if unknown:
            raise ValueError(f"互动配置引用了未知动作: {', '.join(sorted(unknown))}")
        random_idle_weights = {
            str(name): float(value)
            for name, value in interaction["random_idle_weights"].items()
        }
        if set(random_idle_weights) != set(random_idle_actions):
            raise ValueError("random_idle_weights 必须与 random_idle_actions 完全对应")
        if any(value <= 0 for value in random_idle_weights.values()):
            raise ValueError("random_idle_weights 必须全部大于 0")

        scaling = raw["scaling"]
        scale_options = tuple(sorted({int(value) for value in scaling["options_percent"]}))
        if not scale_options or any(value <= 0 for value in scale_options):
            raise ValueError("尺寸选项必须是正整数")

        delay_range = tuple(int(value) for value in interaction["random_idle_delay_ms"])
        if len(delay_range) != 2 or delay_range[0] > delay_range[1]:
            raise ValueError("random_idle_delay_ms 应为 [最小值, 最大值]")

        animation = raw["animation"]
        render_fps = int(animation["render_fps"])
        if render_fps < 12 or render_fps > 60:
            raise ValueError("animation.render_fps 应在 12～60 之间")
        tween_actions = frozenset(
            str(value) for value in animation["tween_actions"]
        )
        unknown_tween_actions = tween_actions.difference(actions)
        if unknown_tween_actions:
            raise ValueError(
                "补间配置引用了未知动作: "
                + ", ".join(sorted(unknown_tween_actions))
            )
        tween_fraction = float(animation["tween_fraction"])
        if not 0.1 <= tween_fraction <= 1.0:
            raise ValueError("animation.tween_fraction 应在 0.1～1.0 之间")

        movement = raw["movement"]
        auto_walk_delay = tuple(int(value) for value in movement["auto_walk_delay_ms"])
        auto_walk_duration = tuple(
            int(value) for value in movement["auto_walk_duration_ms"]
        )
        for label, values in (
            ("auto_walk_delay_ms", auto_walk_delay),
            ("auto_walk_duration_ms", auto_walk_duration),
        ):
            if len(values) != 2 or values[0] > values[1] or values[0] <= 0:
                raise ValueError(f"{label} 应为两个递增的正整数")

        edge_peek = raw["edge_peek"]
        enabled_edges = tuple(str(value) for value in edge_peek["enabled_edges"])
        if not enabled_edges or not set(enabled_edges) <= {"left", "right"}:
            raise ValueError("enabled_edges 只能包含 left 和 right")
        peek_motion_delay = tuple(
            int(value) for value in edge_peek["motion_delay_ms"]
        )
        if (
            len(peek_motion_delay) != 2
            or peek_motion_delay[0] > peek_motion_delay[1]
            or peek_motion_delay[0] <= 0
        ):
            raise ValueError("motion_delay_ms 应为两个递增的正整数")

        sleep = raw["sleep"]
        sleep_delay = tuple(int(value) for value in sleep["inactivity_delay_ms"])
        if len(sleep_delay) != 2 or sleep_delay[0] > sleep_delay[1]:
            raise ValueError("inactivity_delay_ms 应为 [最小值, 最大值]")
        sleep_duration = tuple(int(value) for value in sleep["duration_ms"])
        if (
            len(sleep_duration) != 2
            or sleep_duration[0] > sleep_duration[1]
            or sleep_duration[0] <= 0
        ):
            raise ValueError("sleep.duration_ms 应为两个递增的正整数")

        gaze = raw["gaze"]
        expected_gaze_directions = {
            "left",
            "upper_left",
            "up",
            "upper_right",
            "right",
            "lower_right",
            "down",
            "lower_left",
        }
        gaze_frames = {
            str(name): QRect(*rect) for name, rect in gaze["frames"].items()
        }
        if set(gaze_frames) != expected_gaze_directions:
            raise ValueError("gaze.frames 必须配置八个注视方向")
        gaze_spontaneous_delay = tuple(
            int(value) for value in gaze["spontaneous_delay_ms"]
        )
        gaze_duration = tuple(int(value) for value in gaze["duration_ms"])
        for label, values in (
            ("gaze.spontaneous_delay_ms", gaze_spontaneous_delay),
            ("gaze.duration_ms", gaze_duration),
        ):
            if len(values) != 2 or values[0] > values[1] or values[0] <= 0:
                raise ValueError(f"{label} 应为两个递增的正整数")
        if int(gaze["click_follow_duration_ms"]) <= 0:
            raise ValueError("gaze.click_follow_duration_ms 必须大于 0")

        time_state = raw["time_state"]
        time_visual_actions = {
            str(name): str(action)
            for name, action in time_state["visual_actions"].items()
        }
        if set(time_visual_actions) != {"morning", "day", "night"}:
            raise ValueError("time_state.visual_actions 必须包含 morning/day/night")
        unknown_time_actions = set(time_visual_actions.values()).difference(actions)
        if unknown_time_actions:
            raise ValueError(
                "时间状态引用了未知动作: "
                + ", ".join(sorted(unknown_time_actions))
            )
        time_motion_actions = {
            str(name): str(action)
            for name, action in time_state["motion_actions"].items()
        }
        if set(time_motion_actions) != {"morning", "day", "night"}:
            raise ValueError("time_state.motion_actions 必须包含 morning/day/night")
        unknown_time_motion_actions = set(time_motion_actions.values()).difference(
            actions
        )
        if unknown_time_motion_actions:
            raise ValueError(
                "时间待机小动作引用了未知动作: "
                + ", ".join(sorted(unknown_time_motion_actions))
            )
        workdays = tuple(int(value) for value in time_state["workdays"])
        if not workdays or any(value < 0 or value > 6 for value in workdays):
            raise ValueError("workdays 只能使用 0（周一）到 6（周日）")

        clock_values = {
            name: cls._parse_clock(time_state[name])
            for name in (
                "morning_start",
                "work_start",
                "lunch_start",
                "lunch_end",
                "work_end",
                "night_start",
            )
        }
        ordered_clock_names = (
            "morning_start",
            "work_start",
            "lunch_start",
            "lunch_end",
            "work_end",
            "night_start",
        )
        ordered_clock_values = [clock_values[name] for name in ordered_clock_names]
        if ordered_clock_values != sorted(ordered_clock_values):
            raise ValueError("time_state 中的时间必须按一天内的先后顺序配置")

        anger = raw["anger"]
        if int(anger["click_threshold"]) < 2:
            raise ValueError("click_threshold 至少为 2")

        speech = raw["speech"]
        speech_delay = tuple(int(value) for value in speech["delay_ms"])
        if (
            len(speech_delay) != 2
            or speech_delay[0] > speech_delay[1]
            or speech_delay[0] <= 0
        ):
            raise ValueError("speech.delay_ms 应为两个递增的正整数")
        speech_phrases = {
            str(phase): tuple(str(text) for text in values)
            for phase, values in speech["phrases"].items()
        }
        required_phases = {
            "early_morning",
            "before_work",
            "work_morning",
            "lunch",
            "work_afternoon",
            "after_work",
            "night",
            "day_off",
            "angry",
        }
        if required_phases.difference(speech_phrases):
            raise ValueError("speech.phrases 缺少必要的时间阶段")
        if any(not values for values in speech_phrases.values()):
            raise ValueError("每个说话阶段至少需要一句台词")

        window_layer = raw["window_layer"]
        return cls(
            spritesheet_path=manifest_path.parent / raw["spritesheet"],
            frame_size=QSize(*raw["frame_size"]),
            display_size=QSize(*raw["display_size"]),
            actions=actions,
            move_interval_ms=int(movement["interval_ms"]),
            move_step_px=int(movement["step_px"]),
            auto_walk_delay_ms=(auto_walk_delay[0], auto_walk_delay[1]),
            auto_walk_duration_ms=(auto_walk_duration[0], auto_walk_duration[1]),
            auto_walk_default=bool(movement["auto_walk_default"]),
            click_actions=click_actions,
            random_idle_actions=random_idle_actions,
            random_idle_weights=random_idle_weights,
            random_idle_delay_ms=(delay_range[0], delay_range[1]),
            animation_render_interval_ms=max(1, round(1000 / render_fps)),
            animation_tween_actions=tween_actions,
            animation_tween_fraction=tween_fraction,
            sleep_enabled_default=bool(sleep["enabled_default"]),
            inactivity_sleep_delay_ms=(sleep_delay[0], sleep_delay[1]),
            sleep_duration_ms=(sleep_duration[0], sleep_duration[1]),
            default_scale_percent=int(scaling["default_percent"]),
            scale_options_percent=scale_options,
            edge_snap_distance_px=int(edge_peek["snap_distance_px"]),
            enabled_edges=enabled_edges,
            tuck_delay_ms=int(edge_peek["delay_ms"]),
            tuck_animation_ms=int(edge_peek["animation_ms"]),
            peek_motion_delay_ms=(
                peek_motion_delay[0],
                peek_motion_delay[1],
            ),
            reveal_animation_ms=int(edge_peek["reveal_animation_ms"]),
            desktop_layer_default=bool(window_layer["desktop_layer_default"]),
            gaze_enabled_default=bool(gaze["enabled_default"]),
            gaze_radius_px=int(gaze["radius_px"]),
            gaze_poll_interval_ms=int(gaze["poll_interval_ms"]),
            gaze_spontaneous_delay_ms=(
                gaze_spontaneous_delay[0],
                gaze_spontaneous_delay[1],
            ),
            gaze_duration_ms=(gaze_duration[0], gaze_duration[1]),
            gaze_click_follow_duration_ms=int(gaze["click_follow_duration_ms"]),
            gaze_frames=gaze_frames,
            time_state_enabled_default=bool(time_state["enabled_default"]),
            time_state_check_interval_ms=int(time_state["check_interval_ms"]),
            workdays=workdays,
            morning_start_minute=clock_values["morning_start"],
            work_start_minute=clock_values["work_start"],
            lunch_start_minute=clock_values["lunch_start"],
            lunch_end_minute=clock_values["lunch_end"],
            work_end_minute=clock_values["work_end"],
            night_start_minute=clock_values["night_start"],
            time_visual_actions=time_visual_actions,
            time_motion_actions=time_motion_actions,
            anger_click_threshold=int(anger["click_threshold"]),
            anger_click_window_ms=int(anger["click_window_ms"]),
            anger_duration_ms=int(anger["duration_ms"]),
            speech_enabled_default=bool(speech["enabled_default"]),
            speech_delay_ms=(speech_delay[0], speech_delay[1]),
            speech_bubble_duration_ms=int(speech["bubble_duration_ms"]),
            speech_phrases=speech_phrases,
            phase_transition_phrases={
                str(phase): str(text)
                for phase, text in speech["phase_transitions"].items()
            },
        )

    @staticmethod
    def _parse_clock(value: object) -> int:
        try:
            hour_text, minute_text = str(value).split(":", 1)
            hour = int(hour_text)
            minute = int(minute_text)
        except (TypeError, ValueError) as error:
            raise ValueError(f"无效时间格式: {value!r}") from error
        if hour not in range(24) or minute not in range(60):
            raise ValueError(f"无效时间: {value!r}")
        return hour * 60 + minute


class SpriteAtlas:
    def __init__(self, config: PetConfig) -> None:
        self._sheet = QPixmap(str(config.spritesheet_path))
        self._cache: dict[tuple[int, int, int, int, bool], QPixmap] = {}
        if self._sheet.isNull():
            raise FileNotFoundError(f"无法读取图片: {config.spritesheet_path}")

        sheet_rect = self._sheet.rect()
        for action_name, action in config.actions.items():
            for frame in action.frames:
                if not sheet_rect.contains(frame):
                    raise ValueError(
                        f"{action_name} 的帧 {frame.getRect()} 超出素材范围 "
                        f"{sheet_rect.getRect()}"
                    )
        for direction, frame in config.gaze_frames.items():
            if not sheet_rect.contains(frame):
                raise ValueError(
                    f"注视方向 {direction} 的帧 {frame.getRect()} 超出素材范围 "
                    f"{sheet_rect.getRect()}"
                )

    def frame(self, rect: QRect, mirrored: bool = False) -> QPixmap:
        key = (*rect.getRect(), mirrored)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        pixmap = self._sheet.copy(rect)
        if mirrored:
            pixmap = pixmap.transformed(
                QTransform().scale(-1.0, 1.0),
                Qt.TransformationMode.SmoothTransformation,
            )
        self._cache[key] = pixmap
        return pixmap


class SpeechBubble(QWidget):
    MAX_TEXT_WIDTH = 226
    HORIZONTAL_PADDING = 16
    VERTICAL_PADDING = 12
    TAIL_HEIGHT = 12

    def __init__(self, owner: "DesktopPet") -> None:
        super().__init__(None)
        self._owner = owner
        self._text = ""
        self._below_owner = False
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFont(QFont("Microsoft YaHei UI", 10))
        self.apply_layer(owner._desktop_layer)

    def apply_layer(self, desktop_layer: bool) -> None:
        was_visible = self.isVisible()
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        if desktop_layer:
            flags |= Qt.WindowType.WindowStaysOnBottomHint
        else:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        if was_visible:
            self.show()
            self.reposition()

    def show_text(self, text: str, duration_ms: int) -> None:
        self._text = text.strip()
        if not self._text:
            return

        metrics = QFontMetrics(self.font())
        text_rect = metrics.boundingRect(
            QRect(0, 0, self.MAX_TEXT_WIDTH, 1000),
            int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
            self._text,
        )
        width = max(126, min(self.MAX_TEXT_WIDTH, text_rect.width()) + 32)
        height = max(54, text_rect.height() + self.VERTICAL_PADDING * 2)
        self.setFixedSize(width, height + self.TAIL_HEIGHT)
        self.reposition()
        self.show()
        self.raise_()
        self._hide_timer.start(duration_ms)
        self.update()

    def dismiss(self) -> None:
        self._hide_timer.stop()
        self._text = ""
        self.hide()

    def reposition(self) -> None:
        owner_rect = self._owner.frameGeometry()
        screen = (
            QApplication.screenAt(owner_rect.center())
            or self._owner.screen()
            or QApplication.primaryScreen()
        )
        if screen is None:
            return
        area = screen.availableGeometry()
        x = owner_rect.center().x() - self.width() // 2
        y = owner_rect.top() - self.height() + 10
        self._below_owner = y < area.top()
        if self._below_owner:
            y = owner_rect.bottom() - 8
        x = min(max(x, area.left()), area.right() - self.width() + 1)
        y = min(max(y, area.top()), area.bottom() - self.height() + 1)
        self.move(x, y)

    def paintEvent(self, event: object) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        tail = self.TAIL_HEIGHT
        if self._below_owner:
            bubble_rect = QRect(1, tail, self.width() - 2, self.height() - tail - 1)
            tip_y = 1
            base_y = tail + 1
        else:
            bubble_rect = QRect(1, 1, self.width() - 2, self.height() - tail - 1)
            tip_y = self.height() - 1
            base_y = self.height() - tail - 1

        painter.setPen(QColor(69, 77, 74, 210))
        painter.setBrush(QColor(255, 255, 250, 242))
        painter.drawRoundedRect(bubble_rect, 13, 13)

        center_x = self.width() // 2
        tail_polygon = QPolygon(
            [
                QPoint(center_x - 9, base_y),
                QPoint(center_x + 9, base_y),
                QPoint(center_x, tip_y),
            ]
        )
        painter.drawPolygon(tail_polygon)

        painter.setPen(QColor(44, 55, 51))
        painter.drawText(
            bubble_rect.adjusted(
                self.HORIZONTAL_PADDING,
                self.VERTICAL_PADDING,
                -self.HORIZONTAL_PADDING,
                -self.VERTICAL_PADDING,
            ),
            int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
            self._text,
        )


class DesktopPet(QWidget):
    DRAG_THRESHOLD = 4

    def __init__(self) -> None:
        super().__init__()

        manifest_path = resource_path("assets/sprite_manifest.json")
        self._config = PetConfig.load(manifest_path)
        self._atlas = SpriteAtlas(self._config)
        self._settings = QSettings()

        self._action_name = "idle"
        self._frame_index = 0
        self._action_queue: list[str] = []
        self._sequence_final_action: str | None = None
        self._sequence_callback: Callable[[], None] | None = None
        self._frame_started_at = time.monotonic()
        self._walking = False
        self._sleeping = False
        self._angry = False
        self._drag_effect_active = False
        self._ignore_release_click = False
        self._dismiss_bubble_on_release = False
        self._interaction_active = False
        self._direction = 1
        self._click_times: deque[float] = deque()
        self._gaze_direction: str | None = None
        self._gaze_active_until = 0.0
        self._next_gaze_at = time.monotonic()
        self._scale_percent = self._load_scale_percent()
        self._auto_walk_enabled = self._load_auto_walk_enabled()
        self._sleep_enabled = self._load_sleep_enabled()
        self._desktop_layer = self._load_desktop_layer()
        self._gaze_enabled = self._load_bool_setting(
            "gaze_enabled", self._config.gaze_enabled_default
        )
        self._time_state_enabled = self._load_bool_setting(
            "time_state_enabled", self._config.time_state_enabled_default
        )
        self._speech_enabled = self._load_bool_setting(
            "speech_enabled", self._config.speech_enabled_default
        )
        self._schedule_next_spontaneous_gaze()
        now = datetime.now()
        self._visual_time_state = self._calculate_visual_time_state(now)
        self._last_work_phase = self._work_phase(now)

        self._mouse_press_global = QPoint()
        self._window_press_position = QPoint()
        self._dragging = False

        self._tucked_edge: str | None = None
        self._pending_tuck_edge: str | None = None
        self._pending_tuck_area = QRect()
        self._post_landing_tuck_edge: str | None = None
        self._reveal_target = QPoint()

        self.setWindowTitle("桌宠")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._apply_window_layer_flags()
        self.setFixedSize(self._scaled_full_size())
        self._speech_bubble = SpeechBubble(self)

        self._animation_timer = QTimer(self)
        self._animation_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._animation_timer.timeout.connect(self._advance_frame)

        self._movement_timer = QTimer(self)
        self._movement_timer.setInterval(self._config.move_interval_ms)
        self._movement_timer.timeout.connect(self._move_one_step)

        self._auto_walk_timer = QTimer(self)
        self._auto_walk_timer.setSingleShot(True)
        self._auto_walk_timer.timeout.connect(self._start_auto_walk)

        self._walk_stop_timer = QTimer(self)
        self._walk_stop_timer.setSingleShot(True)
        self._walk_stop_timer.timeout.connect(self._finish_auto_walk)

        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._trigger_random_idle)

        self._sleep_timer = QTimer(self)
        self._sleep_timer.setSingleShot(True)
        self._sleep_timer.timeout.connect(self._begin_sleep)

        self._auto_wake_timer = QTimer(self)
        self._auto_wake_timer.setSingleShot(True)
        self._auto_wake_timer.timeout.connect(self._wake_from_sleep)

        self._tuck_timer = QTimer(self)
        self._tuck_timer.setSingleShot(True)
        self._tuck_timer.timeout.connect(self._begin_tuck)

        self._tuck_animation = QPropertyAnimation(self, b"pos", self)
        self._tuck_animation.setDuration(self._config.tuck_animation_ms)
        self._tuck_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._tuck_animation.finished.connect(self._finish_tuck)

        self._peek_motion_timer = QTimer(self)
        self._peek_motion_timer.setSingleShot(True)
        self._peek_motion_timer.timeout.connect(self._play_peek_motion)

        self._reveal_animation = QPropertyAnimation(self, b"pos", self)
        self._reveal_animation.setDuration(self._config.reveal_animation_ms)
        self._reveal_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._reveal_animation.finished.connect(self._finish_reveal_animation)

        self._gaze_timer = QTimer(self)
        self._gaze_timer.setInterval(self._config.gaze_poll_interval_ms)
        self._gaze_timer.timeout.connect(self._update_gaze)
        self._gaze_timer.start()

        self._time_state_timer = QTimer(self)
        self._time_state_timer.setInterval(self._config.time_state_check_interval_ms)
        self._time_state_timer.timeout.connect(self._update_time_state)
        self._time_state_timer.start()

        self._anger_timer = QTimer(self)
        self._anger_timer.setSingleShot(True)
        self._anger_timer.timeout.connect(self._calm_down)

        self._speech_timer = QTimer(self)
        self._speech_timer.setSingleShot(True)
        self._speech_timer.timeout.connect(self._trigger_speech)

        self._play_action(self._base_action_name())
        self._schedule_random_idle()
        self._schedule_auto_walk()
        self._schedule_sleep()
        self._schedule_speech()

    def sizeHint(self) -> QSize:
        return self._scaled_full_size()

    def place_at_saved_or_default_position(self) -> None:
        saved = self._settings.value("position")
        if isinstance(saved, QPoint):
            self.move(self._clamp_position_to_screen(saved))
            return

        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        margin = 18
        self.move(
            area.right() - self.width() - margin + 1,
            area.bottom() - self.height() - margin + 1,
        )

    def paintEvent(self, event: object) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        action = self._config.actions[self._action_name]
        if self._gaze_direction is not None and self._is_base_action():
            frame_rect = self._config.gaze_frames[self._gaze_direction]
            next_frame_rect = None
            blend = 0.0
        else:
            frame_rect = action.frames[self._frame_index]
            next_frame_rect, blend = self._next_tween_frame(action)
        mirrored = (
            self._action_name in {"walk", "walk_start", "walk_stop"}
            and self._direction < 0
        ) or self._action_name == "peek_right_exit"
        painter.drawPixmap(self.rect(), self._atlas.frame(frame_rect, mirrored))
        if next_frame_rect is not None and blend > 0.0:
            painter.setOpacity(blend)
            painter.drawPixmap(
                self.rect(),
                self._atlas.frame(next_frame_rect, mirrored),
            )

    def moveEvent(self, event: object) -> None:
        super().moveEvent(event)
        if hasattr(self, "_speech_bubble") and self._speech_bubble.isVisible():
            self._speech_bubble.reposition()

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_speech_bubble") and self._speech_bubble.isVisible():
            self._speech_bubble.reposition()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._cancel_pending_tuck()
            self._register_user_activity()
            self._mouse_press_global = event.globalPosition().toPoint()
            self._window_press_position = self.pos()
            self._dragging = False
            self._ignore_release_click = False
            self._dismiss_bubble_on_release = self._speech_bubble.isVisible()
            if self._dismiss_bubble_on_release:
                self._ignore_release_click = True
            elif self._sleeping:
                self._ignore_release_click = True
                self._wake_from_sleep()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not event.buttons() & Qt.MouseButton.LeftButton:
            super().mouseMoveEvent(event)
            return

        global_position = event.globalPosition().toPoint()
        delta = global_position - self._mouse_press_global
        if delta.manhattanLength() < self.DRAG_THRESHOLD:
            event.accept()
            return

        self._dismiss_bubble_on_release = False

        if self._tucked_edge is not None:
            self._restore_from_tuck(play_interaction=False, cursor=global_position)
            self._mouse_press_global = global_position
            self._window_press_position = self.pos()
            self._dragging = True
            self._begin_drag_effect()
            event.accept()
            return

        if not self._dragging:
            self._dragging = True
            self._begin_drag_effect()
        if self._walking:
            self._stop_auto_walk(return_to_idle=False, reschedule=False)
        self.move(self._clamp_position_to_screen(self._window_press_position + delta))
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return

        if self._dismiss_bubble_on_release and not self._dragging:
            self._speech_bubble.dismiss()
        elif self._tucked_edge is not None and not self._dragging:
            self._restore_from_tuck(play_interaction=True)
        elif self._dragging:
            self._settings.setValue("position", self.pos())
            edge = self._nearest_tuck_edge()
            self._post_landing_tuck_edge = edge
            self._end_drag_effect()
        elif not self._ignore_release_click:
            self._play_click_interaction()

        self._dragging = False
        self._ignore_release_click = False
        self._dismiss_bubble_on_release = False
        self._register_user_activity()
        event.accept()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._register_user_activity()
            options = self._config.scale_options_percent
            current_index = min(
                range(len(options)),
                key=lambda index: abs(options[index] - self._scale_percent),
            )
            direction = 1 if event.angleDelta().y() > 0 else -1
            next_index = min(max(current_index + direction, 0), len(options) - 1)
            self._apply_scale(options[next_index])
            event.accept()
            return
        super().wheelEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        self._register_user_activity()
        menu = QMenu(self)

        if self._tucked_edge is not None:
            reveal_action = QAction("显示完整身体", menu)
            reveal_action.triggered.connect(
                lambda: self._restore_from_tuck(play_interaction=True)
            )
            menu.addAction(reveal_action)

        interact_action = QAction("互动一下", menu)
        interact_action.triggered.connect(self._play_click_interaction)
        menu.addAction(interact_action)

        stroll_action = QAction("自动偶尔散步", menu)
        stroll_action.setCheckable(True)
        stroll_action.setChecked(self._auto_walk_enabled)
        stroll_action.toggled.connect(self._set_auto_walk_enabled)
        menu.addAction(stroll_action)

        walk_now_action = QAction("现在散步一下", menu)
        walk_now_action.setEnabled(not self._walking and self._tucked_edge is None)
        walk_now_action.triggered.connect(self._start_auto_walk)
        menu.addAction(walk_now_action)

        sleep_action = QAction("长时间不操作后自动打盹", menu)
        sleep_action.setCheckable(True)
        sleep_action.setChecked(self._sleep_enabled)
        sleep_action.toggled.connect(self._set_sleep_enabled)
        menu.addAction(sleep_action)

        sleep_now_action = QAction("现在打个盹", menu)
        sleep_now_action.setEnabled(
            not self._sleeping
            and not self._walking
            and not self._dragging
            and self._tucked_edge is None
        )
        sleep_now_action.triggered.connect(self._begin_sleep)
        menu.addAction(sleep_now_action)

        menu.addSeparator()
        gaze_action = QAction("偶尔看向鼠标", menu)
        gaze_action.setCheckable(True)
        gaze_action.setChecked(self._gaze_enabled)
        gaze_action.toggled.connect(self._set_gaze_enabled)
        menu.addAction(gaze_action)

        time_state_action = QAction("按时间切换早晨／白天／夜晚", menu)
        time_state_action.setCheckable(True)
        time_state_action.setChecked(self._time_state_enabled)
        time_state_action.toggled.connect(self._set_time_state_enabled)
        menu.addAction(time_state_action)

        speech_action = QAction("定时随机说话", menu)
        speech_action.setCheckable(True)
        speech_action.setChecked(self._speech_enabled)
        speech_action.toggled.connect(self._set_speech_enabled)
        menu.addAction(speech_action)

        speak_now_action = QAction("现在说一句", menu)
        speak_now_action.setEnabled(not self._sleeping and not self._dragging)
        speak_now_action.triggered.connect(self._speak_now)
        menu.addAction(speak_now_action)

        size_menu = menu.addMenu("桌宠大小")
        size_group = QActionGroup(size_menu)
        size_group.setExclusive(True)
        for percent in self._config.scale_options_percent:
            action = QAction(f"{percent}%", size_menu)
            action.setCheckable(True)
            action.setChecked(percent == self._scale_percent)
            action.triggered.connect(
                lambda checked=False, value=percent: self._apply_scale(value)
            )
            size_group.addAction(action)
            size_menu.addAction(action)

        menu.addSeparator()
        home_action = QAction("回到屏幕右下角", menu)
        home_action.triggered.connect(self._move_to_bottom_right)
        menu.addAction(home_action)

        desktop_layer_action = QAction("桌面层（不压住其他窗口）", menu)
        desktop_layer_action.setCheckable(True)
        desktop_layer_action.setChecked(self._desktop_layer)
        desktop_layer_action.toggled.connect(self._set_desktop_layer)
        menu.addAction(desktop_layer_action)

        menu.addSeparator()
        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_action)
        menu.exec(event.globalPos())

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._tucked_edge is None:
            self._settings.setValue("position", self.pos())
        self._settings.setValue("scale_percent", self._scale_percent)
        self._settings.setValue("auto_walk_enabled", self._auto_walk_enabled)
        self._settings.setValue("sleep_enabled", self._sleep_enabled)
        self._settings.setValue("desktop_layer", self._desktop_layer)
        self._settings.setValue("gaze_enabled", self._gaze_enabled)
        self._settings.setValue("time_state_enabled", self._time_state_enabled)
        self._settings.setValue("speech_enabled", self._speech_enabled)
        self._speech_bubble.close()
        super().closeEvent(event)

    def toggle_walking(self) -> None:
        if self._walking:
            self._finish_auto_walk()
        else:
            self._start_auto_walk()

    def _start_action(self, name: str) -> None:
        self._action_name = name
        self._frame_index = 0
        self._frame_started_at = time.monotonic()
        self._arm_animation_timer()
        self.update()

    def _arm_animation_timer(self) -> None:
        action = self._config.actions[self._action_name]
        if (
            self._action_name in self._config.animation_tween_actions
            and len(action.frames) > 1
        ):
            interval_ms = self._config.animation_render_interval_ms
        else:
            elapsed_ms = (time.monotonic() - self._frame_started_at) * 1000.0
            interval_ms = max(
                1,
                round(action.durations_ms[self._frame_index] - elapsed_ms),
            )
        self._animation_timer.start(interval_ms)

    def _play_action(self, name: str) -> None:
        self._action_queue.clear()
        self._sequence_final_action = None
        self._sequence_callback = None
        self._start_action(name)

    def _play_sequence(
        self,
        actions: tuple[str, ...],
        *,
        final_action: str | None,
        callback: Callable[[], None] | None = None,
    ) -> None:
        if not actions:
            raise ValueError("动作序列不能为空")
        self._action_queue = list(actions[1:])
        self._sequence_final_action = final_action
        self._sequence_callback = callback
        self._start_action(actions[0])

    def _advance_frame(self) -> None:
        action = self._config.actions[self._action_name]
        elapsed_ms = (time.monotonic() - self._frame_started_at) * 1000.0
        if elapsed_ms < action.durations_ms[self._frame_index]:
            if self._action_name in self._config.animation_tween_actions:
                self.update()
            self._arm_animation_timer()
            return

        next_index = self._frame_index + 1
        if next_index < len(action.frames):
            self._frame_index = next_index
            self._frame_started_at = time.monotonic()
            self._arm_animation_timer()
            self.update()
            return
        if action.loop:
            self._frame_index = 0
            self._frame_started_at = time.monotonic()
            self._arm_animation_timer()
            self.update()
            return
        if self._action_queue:
            self._start_action(self._action_queue.pop(0))
            return

        final_action = self._sequence_final_action or self._base_action_name()
        callback = self._sequence_callback
        self._action_queue.clear()
        self._sequence_callback = None
        self._start_action(final_action)
        if callback is not None:
            QTimer.singleShot(0, callback)

    def _next_tween_frame(self, action: Action) -> tuple[QRect | None, float]:
        if (
            self._action_name not in self._config.animation_tween_actions
            or len(action.frames) < 2
        ):
            return None, 0.0

        next_index = self._frame_index + 1
        if next_index >= len(action.frames):
            if not action.loop:
                return None, 0.0
            next_index = 0

        duration_ms = action.durations_ms[self._frame_index]
        elapsed_ms = (time.monotonic() - self._frame_started_at) * 1000.0
        progress = min(max(elapsed_ms / duration_ms, 0.0), 1.0)
        fraction = self._config.animation_tween_fraction
        start = 1.0 - fraction
        if progress <= start:
            return None, 0.0
        blend = min(max((progress - start) / fraction, 0.0), 1.0)
        blend = blend * blend * (3.0 - 2.0 * blend)
        return action.frames[next_index], blend

    def _play_click_interaction(self) -> None:
        if self._speech_bubble.isVisible():
            self._speech_bubble.dismiss()
            return
        if self._sleeping:
            self._wake_from_sleep()
            return
        if self._tucked_edge is not None:
            self._restore_from_tuck(play_interaction=True)
            return
        if self._angry:
            self._anger_timer.start(self._config.anger_duration_ms)
            self._say(random.choice(self._config.speech_phrases["angry"]))
            return
        if self._record_click_and_maybe_anger():
            return
        if self._interaction_active:
            return
        self._cancel_pending_tuck()
        if self._walking:
            self._stop_auto_walk(return_to_idle=False, reschedule=False)
        self._stop_idle_timers()
        self._interaction_active = True
        self._play_sequence(
            (random.choice(self._config.click_actions),),
            final_action=None,
            callback=self._finish_click_interaction,
        )

    def _finish_click_interaction(self) -> None:
        self._interaction_active = False
        self._activate_gaze(self._config.gaze_click_follow_duration_ms)
        self._after_active_action()

    def _schedule_random_idle(self) -> None:
        if self._sleeping or self._angry or self._tucked_edge is not None:
            self._idle_timer.stop()
            return
        minimum, maximum = self._config.random_idle_delay_ms
        self._idle_timer.start(random.randint(minimum, maximum))

    def _trigger_random_idle(self) -> None:
        if (
            self._walking
            or self._dragging
            or self._sleeping
            or self._angry
            or self._tucked_edge is not None
            or not self._is_base_action()
            or self._gaze_active()
        ):
            self._schedule_random_idle()
            return
        self._play_sequence(
            (self._choose_idle_motion(),),
            final_action=None,
            callback=self._after_active_action,
        )

    def _choose_idle_motion(self) -> str:
        choices = list(self._config.random_idle_actions)
        weights = [
            self._config.random_idle_weights[name]
            for name in choices
        ]
        if self._time_state_enabled:
            choices.append(
                self._config.time_motion_actions[self._visual_time_state]
            )
            weights.append(0.24)
        return random.choices(choices, weights=weights, k=1)[0]

    def _schedule_auto_walk(self) -> None:
        if (
            not self._auto_walk_enabled
            or self._sleeping
            or self._angry
            or self._tucked_edge is not None
        ):
            self._auto_walk_timer.stop()
            return
        minimum, maximum = self._config.auto_walk_delay_ms
        self._auto_walk_timer.start(random.randint(minimum, maximum))

    def _start_auto_walk(self) -> None:
        if (
            self._walking
            or self._dragging
            or self._sleeping
            or self._angry
            or self._tucked_edge is not None
            or not self._is_base_action()
        ):
            self._schedule_auto_walk()
            return

        self._idle_timer.stop()
        self._walking = True
        self._direction = random.choice((-1, 1))
        self._play_sequence(
            ("walk_start",),
            final_action="walk",
        )
        self._movement_timer.start()
        minimum, maximum = self._config.auto_walk_duration_ms
        self._walk_stop_timer.start(random.randint(minimum, maximum))

    def _finish_auto_walk(self) -> None:
        self._stop_auto_walk(return_to_idle=True, reschedule=True)

    def _stop_auto_walk(self, *, return_to_idle: bool, reschedule: bool) -> None:
        was_walking = self._walking
        self._walking = False
        self._movement_timer.stop()
        self._walk_stop_timer.stop()
        if return_to_idle and was_walking:
            self._play_sequence(
                ("walk_stop",),
                final_action=self._base_action_name(),
            )
        if reschedule and not self._sleeping and not self._angry:
            self._schedule_random_idle()
            self._schedule_auto_walk()

    def _set_auto_walk_enabled(self, enabled: bool) -> None:
        self._auto_walk_enabled = enabled
        self._settings.setValue("auto_walk_enabled", enabled)
        if enabled:
            self._schedule_auto_walk()
        else:
            self._auto_walk_timer.stop()
            if self._walking:
                self._stop_auto_walk(return_to_idle=True, reschedule=False)

    def _move_one_step(self) -> None:
        if self._action_name != "walk" or self._tucked_edge is not None:
            return

        screen = QApplication.screenAt(self.frameGeometry().center()) or self.screen()
        if screen is None:
            return
        area = screen.availableGeometry()

        next_x = self.x() + self._direction * self._config.move_step_px
        min_x = area.left()
        max_x = area.right() - self.width() + 1
        if next_x <= min_x:
            next_x = min_x
            self._direction = 1
        elif next_x >= max_x:
            next_x = max_x
            self._direction = -1

        self.move(
            next_x,
            min(max(self.y(), area.top()), area.bottom() - self.height() + 1),
        )
        self.update()

    def _after_active_action(self) -> None:
        if (
            self._sleeping
            or self._dragging
            or self._angry
            or self._tucked_edge is not None
        ):
            return
        self._schedule_random_idle()
        self._schedule_auto_walk()
        self._schedule_speech()

    def _stop_idle_timers(self) -> None:
        self._idle_timer.stop()
        self._auto_walk_timer.stop()

    def _register_user_activity(self) -> None:
        self._sleep_timer.stop()
        if not self._sleeping:
            self._schedule_sleep()

    def _schedule_sleep(self) -> None:
        if (
            not self._sleep_enabled
            or self._sleeping
            or self._angry
            or self._dragging
            or self._tucked_edge is not None
        ):
            self._sleep_timer.stop()
            return
        minimum, maximum = self._config.inactivity_sleep_delay_ms
        self._sleep_timer.start(random.randint(minimum, maximum))

    def _begin_sleep(self) -> None:
        if (
            self._sleeping
            or self._angry
            or self._walking
            or self._dragging
            or self._tucked_edge is not None
            or not self._is_base_action()
        ):
            self._schedule_sleep()
            return

        self._sleeping = True
        self._stop_idle_timers()
        self._sleep_timer.stop()
        sleep_minimum, sleep_maximum = self._config.sleep_duration_ms
        transition_ms = sum(self._config.actions["sit_down"].durations_ms) + sum(
            self._config.actions["doze_off"].durations_ms
        )
        self._auto_wake_timer.start(
            transition_ms + random.randint(sleep_minimum, sleep_maximum)
        )
        self._play_sequence(
            ("sit_down", "doze_off"),
            final_action="sleep",
        )

    def _wake_from_sleep(self) -> None:
        if not self._sleeping:
            return
        self._auto_wake_timer.stop()
        self._sleeping = False
        self._play_sequence(
            ("wake",),
            final_action=None,
            callback=self._after_wake,
        )

    def _after_wake(self) -> None:
        self._schedule_random_idle()
        self._schedule_auto_walk()
        self._schedule_sleep()
        self._schedule_speech()

    def _set_sleep_enabled(self, enabled: bool) -> None:
        self._sleep_enabled = enabled
        self._settings.setValue("sleep_enabled", enabled)
        if enabled:
            self._schedule_sleep()
        else:
            self._sleep_timer.stop()
            if self._sleeping:
                self._wake_from_sleep()

    def _begin_drag_effect(self) -> None:
        if self._drag_effect_active:
            return
        self._cancel_angry(play_calm_animation=False)
        self._gaze_direction = None
        self._reveal_animation.stop()
        self._reveal_target = QPoint()
        if self._sleeping:
            self._auto_wake_timer.stop()
            self._sleeping = False
        if self._walking:
            self._stop_auto_walk(return_to_idle=False, reschedule=False)
        self._stop_idle_timers()
        self._sleep_timer.stop()
        self._drag_effect_active = True
        self._interaction_active = False
        self._play_sequence(
            ("grab_lift",),
            final_action="held_drag",
        )

    def _end_drag_effect(self) -> None:
        self._drag_effect_active = False
        self._play_sequence(
            ("release_fall", "soft_land"),
            final_action=None,
            callback=self._after_landing,
        )

    def _after_landing(self) -> None:
        edge = self._post_landing_tuck_edge
        self._post_landing_tuck_edge = None
        if edge is not None:
            screen = QApplication.screenAt(self.frameGeometry().center()) or self.screen()
            if screen is not None:
                self._pending_tuck_edge = edge
                self._pending_tuck_area = QRect(screen.availableGeometry())
                self._tuck_timer.start(self._config.tuck_delay_ms)
        self._schedule_random_idle()
        self._schedule_auto_walk()
        self._schedule_sleep()
        self._schedule_speech()

    def _base_action_name(self) -> str:
        if not self._time_state_enabled:
            return "idle"
        return self._config.time_visual_actions[self._visual_time_state]

    def _is_base_action(self, name: str | None = None) -> bool:
        candidate = self._action_name if name is None else name
        return candidate == "idle" or candidate in self._config.time_visual_actions.values()

    @staticmethod
    def _minute_of_day(now: datetime) -> int:
        return now.hour * 60 + now.minute

    def _calculate_visual_time_state(self, now: datetime) -> str:
        minute = self._minute_of_day(now)
        if (
            minute < self._config.morning_start_minute
            or minute >= self._config.night_start_minute
        ):
            return "night"
        if minute < self._config.work_start_minute:
            return "morning"
        return "day"

    def _work_phase(self, now: datetime) -> str:
        minute = self._minute_of_day(now)
        if (
            now.weekday() not in self._config.workdays
            and self._config.morning_start_minute
            <= minute
            < self._config.night_start_minute
        ):
            return "day_off"
        if minute < self._config.morning_start_minute:
            return "early_morning"
        if minute < self._config.work_start_minute:
            return "before_work"
        if minute < self._config.lunch_start_minute:
            return "work_morning"
        if minute < self._config.lunch_end_minute:
            return "lunch"
        if minute < self._config.work_end_minute:
            return "work_afternoon"
        if minute < self._config.night_start_minute:
            return "after_work"
        return "night"

    def _update_time_state(self) -> None:
        now = datetime.now()
        new_visual_state = self._calculate_visual_time_state(now)
        new_work_phase = self._work_phase(now)
        visual_changed = new_visual_state != self._visual_time_state
        phase_changed = new_work_phase != self._last_work_phase
        self._visual_time_state = new_visual_state
        self._last_work_phase = new_work_phase

        if (
            visual_changed
            and self._time_state_enabled
            and self._is_base_action()
            and not self._walking
            and not self._sleeping
            and not self._angry
            and self._tucked_edge is None
        ):
            self._play_action(self._base_action_name())

        transition = self._config.phase_transition_phrases.get(new_work_phase)
        if (
            phase_changed
            and transition
            and self._speech_enabled
            and not self._sleeping
            and not self._dragging
            and not self._angry
        ):
            self._say(transition)

    def _set_time_state_enabled(self, enabled: bool) -> None:
        self._time_state_enabled = enabled
        self._settings.setValue("time_state_enabled", enabled)
        self._visual_time_state = self._calculate_visual_time_state(datetime.now())
        if self._is_base_action() and not self._walking:
            self._play_action(self._base_action_name())

    def _update_gaze(self) -> None:
        direction: str | None = None
        now = time.monotonic()
        eligible = (
            self._gaze_enabled
            and self._is_base_action()
            and not self._walking
            and not self._sleeping
            and not self._angry
            and not self._dragging
            and self._tucked_edge is None
        )
        if eligible and now >= self._next_gaze_at and not self._gaze_active():
            minimum, maximum = self._config.gaze_duration_ms
            self._activate_gaze(random.randint(minimum, maximum))

        if (
            eligible
            and self._gaze_active()
        ):
            cursor = QCursor.pos()
            rect = self.frameGeometry()
            outside_x = max(rect.left() - cursor.x(), 0, cursor.x() - rect.right())
            outside_y = max(rect.top() - cursor.y(), 0, cursor.y() - rect.bottom())
            radius = round(
                self._config.gaze_radius_px * self._scale_percent / 100
            )
            if math.hypot(outside_x, outside_y) <= radius:
                center = rect.center()
                dx = cursor.x() - center.x()
                dy = cursor.y() - center.y()
                if abs(dx) < 4 and abs(dy) < 4:
                    direction = "down"
                else:
                    angle = (math.degrees(math.atan2(dy, dx)) + 360.0) % 360.0
                    sectors = (
                        "right",
                        "lower_right",
                        "down",
                        "lower_left",
                        "left",
                        "upper_left",
                        "up",
                        "upper_right",
                    )
                    direction = sectors[int((angle + 22.5) // 45.0) % 8]

        if direction != self._gaze_direction:
            self._gaze_direction = direction
            self.update()

    def _gaze_active(self) -> bool:
        return self._gaze_enabled and time.monotonic() < self._gaze_active_until

    def _activate_gaze(self, duration_ms: int) -> None:
        if not self._gaze_enabled:
            return
        now = time.monotonic()
        self._gaze_active_until = max(
            self._gaze_active_until,
            now + duration_ms / 1000.0,
        )
        self._schedule_next_spontaneous_gaze(base_time=self._gaze_active_until)

    def _schedule_next_spontaneous_gaze(
        self,
        *,
        base_time: float | None = None,
    ) -> None:
        minimum, maximum = self._config.gaze_spontaneous_delay_ms
        anchor = time.monotonic() if base_time is None else base_time
        self._next_gaze_at = anchor + random.randint(minimum, maximum) / 1000.0

    def _set_gaze_enabled(self, enabled: bool) -> None:
        self._gaze_enabled = enabled
        self._settings.setValue("gaze_enabled", enabled)
        if enabled:
            self._schedule_next_spontaneous_gaze()
        else:
            self._gaze_active_until = 0.0
            self._gaze_direction = None
            self.update()

    def _record_click_and_maybe_anger(self) -> bool:
        now = time.monotonic()
        window_seconds = self._config.anger_click_window_ms / 1000.0
        while self._click_times and now - self._click_times[0] > window_seconds:
            self._click_times.popleft()
        self._click_times.append(now)
        if len(self._click_times) < self._config.anger_click_threshold:
            return False
        self._enter_angry_state()
        return True

    def _enter_angry_state(self) -> None:
        self._click_times.clear()
        self._cancel_pending_tuck()
        if self._walking:
            self._stop_auto_walk(return_to_idle=False, reschedule=False)
        self._sleep_timer.stop()
        self._stop_idle_timers()
        self._speech_timer.stop()
        self._gaze_direction = None
        self._interaction_active = False
        self._angry = True
        self._play_sequence(
            ("angry_enter",),
            final_action="angry_hold",
        )
        self._say(random.choice(self._config.speech_phrases["angry"]))
        self._anger_timer.start(self._config.anger_duration_ms)

    def _cancel_angry(self, *, play_calm_animation: bool) -> None:
        if not self._angry:
            return
        self._angry = False
        self._anger_timer.stop()
        self._click_times.clear()
        if play_calm_animation:
            self._play_sequence(
                ("angry_calm",),
                final_action=None,
                callback=self._after_active_action,
            )

    def _calm_down(self) -> None:
        if not self._angry:
            return
        self._angry = False
        self._click_times.clear()
        self._play_sequence(
            ("angry_calm",),
            final_action=None,
            callback=self._after_active_action,
        )

    def _schedule_speech(self) -> None:
        if not self._speech_enabled:
            self._speech_timer.stop()
            return
        minimum, maximum = self._config.speech_delay_ms
        self._speech_timer.start(random.randint(minimum, maximum))

    def _trigger_speech(self) -> None:
        if self._sleeping or self._dragging or self._angry:
            self._schedule_speech()
            return
        self._speak_now()

    def _speak_now(self) -> None:
        phase = "angry" if self._angry else self._work_phase(datetime.now())
        self._say(random.choice(self._config.speech_phrases[phase]))
        self._schedule_speech()

    def _say(self, text: str) -> None:
        self._speech_bubble.show_text(
            text,
            self._config.speech_bubble_duration_ms,
        )

    def _set_speech_enabled(self, enabled: bool) -> None:
        self._speech_enabled = enabled
        self._settings.setValue("speech_enabled", enabled)
        if enabled:
            self._schedule_speech()
        else:
            self._speech_timer.stop()
            self._speech_bubble.dismiss()

    def _load_bool_setting(self, key: str, default: bool) -> bool:
        saved = self._settings.value(key)
        if saved is None:
            return default
        if isinstance(saved, bool):
            return saved
        return str(saved).strip().lower() not in {"0", "false", "no", "off"}

    def _load_scale_percent(self) -> int:
        try:
            saved = int(self._settings.value("scale_percent", ""))
        except (TypeError, ValueError):
            saved = self._config.default_scale_percent
        if saved not in self._config.scale_options_percent:
            return self._config.default_scale_percent
        return saved

    def _load_auto_walk_enabled(self) -> bool:
        saved = self._settings.value("auto_walk_enabled")
        if saved is None:
            return self._config.auto_walk_default
        if isinstance(saved, bool):
            return saved
        return str(saved).strip().lower() not in {"0", "false", "no", "off"}

    def _load_sleep_enabled(self) -> bool:
        saved = self._settings.value("sleep_enabled")
        if saved is None:
            return self._config.sleep_enabled_default
        if isinstance(saved, bool):
            return saved
        return str(saved).strip().lower() not in {"0", "false", "no", "off"}

    def _load_desktop_layer(self) -> bool:
        saved = self._settings.value("desktop_layer")
        if saved is None:
            return self._config.desktop_layer_default
        if isinstance(saved, bool):
            return saved
        return str(saved).strip().lower() not in {"0", "false", "no", "off"}

    def _scaled_full_size(self) -> QSize:
        factor = self._scale_percent / 100.0
        return QSize(
            round(self._config.display_size.width() * factor),
            round(self._config.display_size.height() * factor),
        )

    def _apply_scale(self, percent: int) -> None:
        if percent == self._scale_percent:
            return

        old_center = self.frameGeometry().center()
        tucked_edge = self._tucked_edge
        screen = QApplication.screenAt(old_center) or self.screen() or QApplication.primaryScreen()
        area = screen.availableGeometry() if screen is not None else QRect()

        self._scale_percent = percent
        self._settings.setValue("scale_percent", percent)
        self.setFixedSize(self._scaled_full_size())
        if tucked_edge is not None:
            if area.isValid():
                self._position_edge_peek(tucked_edge, area, self.pos())
        else:
            target = old_center - QPoint(self.width() // 2, self.height() // 2)
            self.move(self._clamp_position_to_screen(target))
            self._settings.setValue("position", self.pos())
        self.update()

    def _nearest_tuck_edge(self) -> str | None:
        screen = QApplication.screenAt(self.frameGeometry().center()) or self.screen()
        if screen is None:
            return None
        area = screen.availableGeometry()
        distances = {
            "left": abs(self.x() - area.left()),
            "right": abs(self.frameGeometry().right() - area.right()),
        }
        distances = {
            edge: distance
            for edge, distance in distances.items()
            if edge in self._config.enabled_edges
        }
        if not distances:
            return None
        edge = min(distances, key=distances.get)
        if distances[edge] <= self._config.edge_snap_distance_px:
            self._pending_tuck_area = QRect(area)
            return edge
        return None

    def _begin_tuck(self) -> None:
        edge = self._pending_tuck_edge
        area = self._pending_tuck_area
        if edge is None or not area.isValid() or self._dragging:
            return

        if self._walking:
            self._stop_auto_walk(return_to_idle=False, reschedule=False)
        self._auto_walk_timer.stop()
        self._idle_timer.stop()
        self._sleep_timer.stop()
        self._auto_wake_timer.stop()
        self._sleeping = False
        self._tucked_edge = edge
        self._peek_motion_timer.stop()
        self._play_sequence(
            (f"peek_{edge}_enter", f"peek_{edge}"),
            final_action=f"peek_{edge}_hold",
            callback=self._schedule_peek_motion,
        )

        target = self._edge_peek_position(edge, area, self.pos())

        self._tuck_animation.stop()
        self._tuck_animation.setStartValue(self.pos())
        self._tuck_animation.setEndValue(target)
        self._tuck_animation.start()

    def _finish_tuck(self) -> None:
        edge = self._pending_tuck_edge
        area = self._pending_tuck_area
        if edge is None or not area.isValid():
            return

        self._pending_tuck_edge = None
        self.move(self._edge_peek_position(edge, area, self.pos()))
        self.update()

    def _schedule_peek_motion(self) -> None:
        if self._tucked_edge is None:
            self._peek_motion_timer.stop()
            return
        minimum, maximum = self._config.peek_motion_delay_ms
        self._peek_motion_timer.start(random.randint(minimum, maximum))

    def _play_peek_motion(self) -> None:
        edge = self._tucked_edge
        if edge is None:
            return
        if self._action_name != f"peek_{edge}_hold":
            self._schedule_peek_motion()
            return
        self._play_sequence(
            (f"peek_{edge}",),
            final_action=f"peek_{edge}_hold",
            callback=self._schedule_peek_motion,
        )

    def _edge_peek_position(self, edge: str, area: QRect, anchor: QPoint) -> QPoint:
        if edge == "left":
            x = area.left()
            y = min(max(anchor.y(), area.top()), area.bottom() - self.height() + 1)
        elif edge == "right":
            x = area.right() - self.width() + 1
            y = min(max(anchor.y(), area.top()), area.bottom() - self.height() + 1)
        else:
            raise ValueError(f"不支持的探头方向: {edge}")
        return QPoint(x, y)

    def _position_edge_peek(self, edge: str, area: QRect, anchor: QPoint) -> None:
        self.move(self._edge_peek_position(edge, area, anchor))

    def _restore_from_tuck(
        self,
        *,
        play_interaction: bool,
        cursor: QPoint | None = None,
    ) -> None:
        edge = self._tucked_edge
        if edge is None:
            return

        screen = QApplication.screenAt(self.frameGeometry().center()) or self.screen()
        area = screen.availableGeometry() if screen is not None else QRect()
        old_position = self.pos()
        old_center = self.frameGeometry().center()

        self._peek_motion_timer.stop()
        self._tucked_edge = None
        margin = 8
        if cursor is not None:
            target = cursor - QPoint(self.width() // 2, self.height() // 3)
        elif edge == "left":
            target = QPoint(area.left() + margin, old_position.y())
        elif edge == "right":
            target = QPoint(area.right() - self.width() - margin + 1, old_position.y())
        else:
            target = old_center - QPoint(self.width() // 2, self.height() // 2)

        if play_interaction:
            self._reveal_target = self._clamp_position_to_screen(target)
            self._play_sequence(
                (f"peek_{edge}_exit",),
                final_action=None,
                callback=self._after_active_action,
            )
            self._reveal_animation.stop()
            self._reveal_animation.setStartValue(old_position)
            self._reveal_animation.setEndValue(self._reveal_target)
            self._reveal_animation.start()
        else:
            self._reveal_animation.stop()
            self.move(self._clamp_position_to_screen(target))
            self._settings.setValue("position", self.pos())
            self._play_action(self._base_action_name())
            self._schedule_random_idle()
            self._schedule_auto_walk()
            self._schedule_sleep()
            self._schedule_speech()

    def _finish_reveal_animation(self) -> None:
        if not self._reveal_target.isNull():
            self.move(self._reveal_target)
            self._settings.setValue("position", self.pos())
        self._reveal_target = QPoint()

    def _cancel_pending_tuck(self) -> None:
        self._tuck_timer.stop()
        self._peek_motion_timer.stop()
        was_animating = (
            self._pending_tuck_edge is not None
            and self._tuck_animation.currentTime() > 0
        )
        self._tuck_animation.stop()
        self._pending_tuck_edge = None
        if was_animating and self._tucked_edge is None:
            self.move(self._clamp_position_to_screen(self.pos()))

    def _move_to_bottom_right(self) -> None:
        if self._tucked_edge is not None:
            self._restore_from_tuck(play_interaction=False)
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        margin = 18
        self.move(
            area.right() - self.width() - margin + 1,
            area.bottom() - self.height() - margin + 1,
        )
        self._settings.setValue("position", self.pos())

    def _apply_window_layer_flags(self) -> None:
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if self._desktop_layer:
            flags |= Qt.WindowType.WindowStaysOnBottomHint
        else:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)

    def _set_desktop_layer(self, enabled: bool) -> None:
        self._desktop_layer = enabled
        self._settings.setValue("desktop_layer", enabled)
        current_position = self.pos()
        self._apply_window_layer_flags()
        self._speech_bubble.apply_layer(enabled)
        self.show()
        self.move(current_position)

    def _clamp_position_to_screen(self, point: QPoint) -> QPoint:
        screen = QApplication.screenAt(point) or QApplication.primaryScreen()
        if screen is None:
            return point
        area = screen.availableGeometry()
        x = min(max(point.x(), area.left()), area.right() - self.width() + 1)
        y = min(max(point.y(), area.top()), area.bottom() - self.height() + 1)
        return QPoint(x, y)

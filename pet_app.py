from __future__ import annotations

import json
import random
import sys
from dataclasses import dataclass
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
    QCloseEvent,
    QContextMenuEvent,
    QMouseEvent,
    QPainter,
    QPixmap,
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
    random_idle_delay_ms: tuple[int, int]
    sleep_enabled_default: bool
    inactivity_sleep_delay_ms: tuple[int, int]
    default_scale_percent: int
    scale_options_percent: tuple[int, ...]
    edge_snap_distance_px: int
    enabled_edges: tuple[str, ...]
    tuck_delay_ms: int
    tuck_animation_ms: int
    peek_motion_delay_ms: tuple[int, int]
    reveal_animation_ms: int
    desktop_layer_default: bool

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
            "walk",
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

        scaling = raw["scaling"]
        scale_options = tuple(sorted({int(value) for value in scaling["options_percent"]}))
        if not scale_options or any(value <= 0 for value in scale_options):
            raise ValueError("尺寸选项必须是正整数")

        delay_range = tuple(int(value) for value in interaction["random_idle_delay_ms"])
        if len(delay_range) != 2 or delay_range[0] > delay_range[1]:
            raise ValueError("random_idle_delay_ms 应为 [最小值, 最大值]")

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
            random_idle_delay_ms=(delay_range[0], delay_range[1]),
            sleep_enabled_default=bool(sleep["enabled_default"]),
            inactivity_sleep_delay_ms=(sleep_delay[0], sleep_delay[1]),
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
        )


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
        self._sequence_final_action = "idle"
        self._sequence_callback: Callable[[], None] | None = None
        self._walking = False
        self._sleeping = False
        self._drag_effect_active = False
        self._ignore_release_click = False
        self._direction = 1
        self._scale_percent = self._load_scale_percent()
        self._auto_walk_enabled = self._load_auto_walk_enabled()
        self._sleep_enabled = self._load_sleep_enabled()
        self._desktop_layer = self._load_desktop_layer()

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

        self._animation_timer = QTimer(self)
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

        self._play_action("idle")
        self._schedule_random_idle()
        self._schedule_auto_walk()
        self._schedule_sleep()

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
        frame_rect = action.frames[self._frame_index]
        mirrored = (
            self._action_name == "walk" and self._direction < 0
        ) or self._action_name == "peek_right_exit"
        painter.drawPixmap(self.rect(), self._atlas.frame(frame_rect, mirrored))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._cancel_pending_tuck()
            self._register_user_activity()
            self._mouse_press_global = event.globalPosition().toPoint()
            self._window_press_position = self.pos()
            self._dragging = False
            self._ignore_release_click = False
            if self._sleeping:
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

        if self._tucked_edge is not None and not self._dragging:
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
        super().closeEvent(event)

    def toggle_walking(self) -> None:
        if self._walking:
            self._finish_auto_walk()
        else:
            self._start_auto_walk()

    def _start_action(self, name: str) -> None:
        action = self._config.actions[name]
        self._action_name = name
        self._frame_index = 0
        self._animation_timer.start(action.durations_ms[0])
        self.update()

    def _play_action(self, name: str) -> None:
        self._action_queue.clear()
        self._sequence_final_action = "idle"
        self._sequence_callback = None
        self._start_action(name)

    def _play_sequence(
        self,
        actions: tuple[str, ...],
        *,
        final_action: str,
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
        next_index = self._frame_index + 1
        if next_index >= len(action.frames):
            if action.loop:
                next_index = 0
            else:
                if self._action_queue:
                    self._start_action(self._action_queue.pop(0))
                    return
                final_action = self._sequence_final_action
                callback = self._sequence_callback
                self._action_queue.clear()
                self._sequence_callback = None
                self._start_action(final_action)
                if callback is not None:
                    QTimer.singleShot(0, callback)
                return
        self._frame_index = next_index
        self._animation_timer.start(action.durations_ms[next_index])
        self.update()

    def _play_click_interaction(self) -> None:
        if self._sleeping:
            self._wake_from_sleep()
            return
        if self._tucked_edge is not None:
            self._restore_from_tuck(play_interaction=True)
            return
        self._cancel_pending_tuck()
        if self._walking:
            self._stop_auto_walk(return_to_idle=False, reschedule=False)
        self._stop_idle_timers()
        self._play_sequence(
            (random.choice(self._config.click_actions),),
            final_action="idle",
            callback=self._after_active_action,
        )

    def _schedule_random_idle(self) -> None:
        if self._sleeping or self._tucked_edge is not None:
            self._idle_timer.stop()
            return
        minimum, maximum = self._config.random_idle_delay_ms
        self._idle_timer.start(random.randint(minimum, maximum))

    def _trigger_random_idle(self) -> None:
        if (
            self._walking
            or self._dragging
            or self._sleeping
            or self._tucked_edge is not None
            or self._action_name != "idle"
        ):
            self._schedule_random_idle()
            return
        self._play_sequence(
            (random.choice(self._config.random_idle_actions),),
            final_action="idle",
            callback=self._after_active_action,
        )

    def _schedule_auto_walk(self) -> None:
        if (
            not self._auto_walk_enabled
            or self._sleeping
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
            or self._tucked_edge is not None
            or self._action_name != "idle"
        ):
            self._schedule_auto_walk()
            return

        self._idle_timer.stop()
        self._walking = True
        self._direction = random.choice((-1, 1))
        self._play_action("walk")
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
            self._play_action("idle")
        if reschedule and not self._sleeping:
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
        if self._sleeping or self._dragging or self._tucked_edge is not None:
            return
        self._schedule_random_idle()
        self._schedule_auto_walk()

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
            or self._walking
            or self._dragging
            or self._tucked_edge is not None
            or self._action_name != "idle"
        ):
            self._schedule_sleep()
            return

        self._sleeping = True
        self._stop_idle_timers()
        self._sleep_timer.stop()
        self._play_sequence(
            ("sit_down", "doze_off"),
            final_action="sleep",
        )

    def _wake_from_sleep(self) -> None:
        if not self._sleeping:
            return
        self._sleeping = False
        self._play_sequence(
            ("wake",),
            final_action="idle",
            callback=self._after_wake,
        )

    def _after_wake(self) -> None:
        self._schedule_random_idle()
        self._schedule_auto_walk()
        self._schedule_sleep()

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
        self._reveal_animation.stop()
        self._reveal_target = QPoint()
        if self._sleeping:
            self._sleeping = False
        if self._walking:
            self._stop_auto_walk(return_to_idle=False, reschedule=False)
        self._stop_idle_timers()
        self._sleep_timer.stop()
        self._drag_effect_active = True
        self._play_sequence(
            ("grab_lift",),
            final_action="held_drag",
        )

    def _end_drag_effect(self) -> None:
        self._drag_effect_active = False
        self._play_sequence(
            ("release_fall", "soft_land"),
            final_action="idle",
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
                final_action="idle",
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
            self._play_action("idle")
            self._schedule_random_idle()
            self._schedule_auto_walk()
            self._schedule_sleep()

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

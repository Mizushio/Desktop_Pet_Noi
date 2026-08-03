from __future__ import annotations

import json
import math
import os
import struct
import subprocess
import sys
import unittest
from pathlib import Path

from PIL import Image, ImageChops

from circle_gesture import CircleGestureTracker
from optional_payload import MessageSnapshotTracker, extract_message_records
from tools.prepare_action_pack import _alpha_components, _character_core_center_x


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "assets" / "sprite_manifest.json"
PET_APP_PATH = PROJECT_ROOT / "pet_app.py"
BUILD_SCRIPT_PATH = PROJECT_ROOT / "build_exe.bat"
AUDIT_SCRIPT_PATH = PROJECT_ROOT / "tools" / "audit_animation_consistency.py"


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as file:
        signature = file.read(24)
    if signature[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"不是 PNG 文件: {path}")
    return struct.unpack(">II", signature[16:24])


class ProjectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_expanded_actions_exist(self) -> None:
        expected = {
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
            "message_notify_enter",
            "message_notify_hold",
            "message_notify_exit",
            "message_notify",
            "dizzy",
        }
        self.assertTrue(expected <= self.manifest["actions"].keys())
        self.assertNotIn("peek_top", self.manifest["actions"])

    def test_all_frames_are_inside_spritesheet(self) -> None:
        sheet_path = MANIFEST_PATH.parent / self.manifest["spritesheet"]
        sheet_width, sheet_height = png_size(sheet_path)

        for action_name, action in self.manifest["actions"].items():
            self.assertEqual(
                len(action["frames"]),
                len(action["durations_ms"]),
                f"{action_name} 的帧数和逐帧时间数量应一致",
            )
            self.assertTrue(all(value > 0 for value in action["durations_ms"]))
            for x, y, width, height in action["frames"]:
                self.assertGreater(width, 0)
                self.assertGreater(height, 0)
                self.assertGreaterEqual(x, 0)
                self.assertGreaterEqual(y, 0)
                self.assertLessEqual(x + width, sheet_width)
                self.assertLessEqual(y + height, sheet_height)

        for x, y, width, height in self.manifest["gaze"]["frames"].values():
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)
            self.assertLessEqual(x + width, sheet_width)
            self.assertLessEqual(y + height, sheet_height)

    def test_expanded_sheet_dimensions(self) -> None:
        sheet_path = MANIFEST_PATH.parent / self.manifest["spritesheet"]
        self.assertEqual((1024, 13760), png_size(sheet_path))

    def test_outfits_cover_the_same_complete_action_atlas(self) -> None:
        self.assertEqual(18, self.manifest["version"])
        outfits = self.manifest["outfits"]
        self.assertEqual(
            {"classic_maid", "dark_green"},
            set(outfits),
        )
        self.assertEqual("dark_green", self.manifest["default_outfit"])

        for outfit_id, outfit in outfits.items():
            self.assertTrue(outfit["label"].strip(), outfit_id)
            sheet_path = MANIFEST_PATH.parent / outfit["spritesheet"]
            self.assertTrue(sheet_path.is_file(), outfit_id)
            self.assertEqual((1024, 13760), png_size(sheet_path), outfit_id)

            sheet = Image.open(sheet_path).convert("RGBA")
            for action_name, action in self.manifest["actions"].items():
                for x, y, width, height in action["frames"]:
                    frame = sheet.crop((x, y, x + width, y + height))
                    self.assertIsNotNone(
                        frame.getchannel("A").getbbox(),
                        f"{outfit_id}/{action_name} 存在空白帧",
                    )
            for direction, rect in self.manifest["gaze"]["frames"].items():
                x, y, width, height = rect
                frame = sheet.crop((x, y, x + width, y + height))
                self.assertIsNotNone(
                    frame.getchannel("A").getbbox(),
                    f"{outfit_id}/gaze/{direction} 存在空白帧",
                )

    def test_dark_green_outfit_passes_full_visual_audit(self) -> None:
        environment = os.environ.copy()
        environment["PET_SPRITESHEET"] = "character_spritesheet_dark_green.png"
        result = subprocess.run(
            [sys.executable, str(AUDIT_SCRIPT_PATH)],
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_dark_green_cute_and_wave_active_frames_keep_neutral_scale(self) -> None:
        sheet_path = MANIFEST_PATH.parent / "character_spritesheet_dark_green.png"
        sheet = Image.open(sheet_path).convert("RGBA")
        actions = self.manifest["actions"]

        def subject_height(rect: list[int]) -> int:
            x, y, width, height = rect
            alpha = sheet.crop((x, y, x + width, y + height)).getchannel("A")
            left, top, right, bottom = self._dominant_alpha_bounds(alpha)
            self.assertGreater(right, left)
            return bottom - top

        def has_only_subject(rect: list[int]) -> bool:
            x, y, width, height = rect
            alpha = sheet.crop((x, y, x + width, y + height)).getchannel("A")
            component_sizes = sorted(
                (len(component) for component in _alpha_components(alpha)),
                reverse=True,
            )
            if len(component_sizes) < 2:
                return True
            return component_sizes[1] <= max(32, round(component_sizes[0] * 0.005))

        idle_height = subject_height(actions["idle"]["frames"][0])
        self.assertGreaterEqual(idle_height, 258)
        self.assertLessEqual(idle_height, 264)

        # Exclude the neutral entry/exit frames.  Earlier tests only compared
        # the tallest frame, so those neutral frames concealed the undersized
        # hands-on-cheeks and wave drawings.
        cute_active = actions["click"]["frames"][1:-1]
        wave_active = actions["wave"]["frames"][1:-1]
        for action_name, active_frames in (
            ("click", cute_active),
            ("wave", wave_active),
        ):
            heights = [subject_height(rect) for rect in active_frames]
            self.assertGreaterEqual(
                min(heights),
                idle_height - 7,
                f"dark_green/{action_name} 仍有明显缩小帧: {heights}",
            )
            self.assertLessEqual(
                max(heights),
                idle_height + 4,
                f"dark_green/{action_name} 出现明显放大帧: {heights}",
            )
        self.assertTrue(
            all(has_only_subject(rect) for rect in wave_active),
            "dark_green/wave 存在与角色分离的跨格残片",
        )

    def test_both_outfits_keep_wave_head_complete_and_vertically_stable(self) -> None:
        actions = self.manifest["actions"]
        for outfit_id, outfit in self.manifest["outfits"].items():
            sheet = Image.open(
                MANIFEST_PATH.parent / outfit["spritesheet"]
            ).convert("RGBA")
            tops: list[int] = []
            heights: list[int] = []
            for frame_index, (x, y, width, height) in enumerate(
                actions["wave"]["frames"][1:-1],
                start=1,
            ):
                alpha = sheet.crop(
                    (x, y, x + width, y + height)
                ).getchannel("A")
                components = _alpha_components(alpha)
                self.assertTrue(components, f"{outfit_id}/wave/{frame_index}")
                subject = max(components, key=len)
                xs = [point[0] for point in subject]
                ys = [point[1] for point in subject]
                top = min(ys)
                bottom = max(ys) + 1
                top_xs = [px for px, py in subject if py == top]
                top_run_width = max(top_xs) - min(top_xs) + 1
                flat_top_limit = max(
                    20,
                    round((max(xs) + 1 - min(xs)) * 0.15),
                )
                self.assertLessEqual(
                    top_run_width,
                    flat_top_limit,
                    f"{outfit_id}/wave/{frame_index} 头顶疑似被源格裁切",
                )
                self.assertLessEqual(
                    len(top_xs),
                    flat_top_limit,
                    f"{outfit_id}/wave/{frame_index} 头顶存在截断直线",
                )
                tops.append(top)
                heights.append(bottom - top)

            self.assertLessEqual(
                max(tops) - min(tops),
                2,
                f"{outfit_id}/wave 仍有垂直平移: {tops}",
            )
            self.assertLessEqual(
                max(heights) - min(heights),
                2,
                f"{outfit_id}/wave 仍有大小波动: {heights}",
            )

    def test_outfit_switching_is_available_and_packaged(self) -> None:
        source = PET_APP_PATH.read_text(encoding="utf-8")
        self.assertIn('menu.addMenu("换装")', source)
        self.assertIn("def _load_outfit_id(self) -> str:", source)
        self.assertIn("def _set_outfit(self, outfit_id: str) -> None:", source)
        self.assertIn('self._settings.setValue("outfit_id", outfit_id)', source)
        build_script = BUILD_SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertIn("character_spritesheet_dark_green.png", build_script)

    def test_running_cycle_has_eight_distinct_consistent_frames(self) -> None:
        action = self.manifest["actions"]["walk"]
        self.assertEqual(8, len(action["frames"]))

        sheet_path = MANIFEST_PATH.parent / self.manifest["spritesheet"]
        sheet = Image.open(sheet_path).convert("RGBA")
        alpha_sizes: list[tuple[int, int]] = []
        frame_bytes: set[bytes] = set()
        for x, y, width, height in action["frames"]:
            frame = sheet.crop((x, y, x + width, y + height))
            bounds = frame.getchannel("A").getbbox()
            self.assertIsNotNone(bounds)
            assert bounds is not None
            alpha_sizes.append((bounds[2] - bounds[0], bounds[3] - bounds[1]))
            frame_bytes.add(frame.tobytes())

        self.assertEqual(8, len(frame_bytes))
        heights = [height for _, height in alpha_sizes]
        widths = [width for width, _ in alpha_sizes]
        self.assertLessEqual(max(heights) - min(heights), 8)
        self.assertLessEqual(max(widths) - min(widths), 8)

    def test_core_character_scale_is_stable(self) -> None:
        sheet_path = MANIFEST_PATH.parent / self.manifest["spritesheet"]
        sheet = Image.open(sheet_path).convert("RGBA")

        def alpha_heights(action_name: str) -> list[int]:
            heights: list[int] = []
            for x, y, width, height in self.manifest["actions"][action_name]["frames"]:
                frame = sheet.crop((x, y, x + width, y + height))
                bounds = frame.getchannel("A").getbbox()
                self.assertIsNotNone(bounds)
                assert bounds is not None
                heights.append(bounds[3] - bounds[1])
            return heights

        self.assertLessEqual(max(alpha_heights("idle")) - min(alpha_heights("idle")), 3)
        self.assertLessEqual(max(alpha_heights("click")) - min(alpha_heights("click")), 12)

        # Compare each pack at its tallest natural pose. Sitting and bowing may
        # legitimately reduce silhouette height, but switching packs must not
        # make the same character suddenly grow or shrink.
        reference_height = max(alpha_heights("idle"))
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
            "sit_sway",
            "curtsey",
            "cheek_puff",
            "message_notify_enter",
            "message_notify_exit",
            "message_notify",
        )
        self.assertGreaterEqual(reference_height, 258)
        self.assertLessEqual(reference_height, 262)
        for action_name in comparable_actions:
            self.assertLessEqual(
                abs(max(alpha_heights(action_name)) - reference_height),
                5,
                action_name,
            )

    def test_sleep_subject_anchor_does_not_jump(self) -> None:
        sheet_path = MANIFEST_PATH.parent / self.manifest["spritesheet"]
        sheet = Image.open(sheet_path).convert("RGBA")
        centers: list[float] = []
        bottoms: list[int] = []

        for action_name in ("sit_down", "doze_off", "sleep", "wake"):
            for x, y, width, height in self.manifest["actions"][action_name]["frames"]:
                alpha = sheet.crop((x, y, x + width, y + height)).getchannel("A")
                left, _top, right, bottom = self._dominant_alpha_bounds(alpha)
                centers.append((left + right) / 2)
                bottoms.append(bottom)

        self.assertLessEqual(max(centers) - min(centers), 1.0)
        self.assertLessEqual(max(bottoms) - min(bottoms), 0)

        sleep_tops: list[int] = []
        for x, y, width, height in self.manifest["actions"]["sleep"]["frames"]:
            alpha = sheet.crop((x, y, x + width, y + height)).getchannel("A")
            bounds = alpha.getbbox()
            self.assertIsNotNone(bounds)
            assert bounds is not None
            sleep_tops.append(bounds[1])
        self.assertLessEqual(max(sleep_tops) - min(sleep_tops), 15)

    @staticmethod
    def _meaningful_alpha_bottom(alpha: Image.Image) -> int:
        width, height = alpha.size
        pixels = alpha.load()
        minimum_row_pixels = max(4, round(width * 0.01))
        for y in range(height - 1, -1, -1):
            occupied = sum(1 for x in range(width) if pixels[x, y] >= 32)
            if occupied >= minimum_row_pixels:
                return y + 1
        raise AssertionError("帧中没有有效角色底部")

    @staticmethod
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
            raise AssertionError("帧中没有有效角色像素")
        trim = max(1, round(total * 0.03))

        def lower(counts: list[int]) -> int:
            accumulated = 0
            for index, count in enumerate(counts):
                accumulated += count
                if accumulated >= trim:
                    return index
            return 0

        def upper(counts: list[int]) -> int:
            accumulated = 0
            for index in range(len(counts) - 1, -1, -1):
                accumulated += counts[index]
                if accumulated >= trim:
                    return index + 1
            return len(counts)

        return lower(x_counts), lower(y_counts), upper(x_counts), upper(y_counts)

    @staticmethod
    def _dominant_alpha_bounds(alpha: Image.Image) -> tuple[int, int, int, int]:
        width, height = alpha.size
        pixels = alpha.load()
        visited = bytearray(width * height)
        components: list[list[tuple[int, int]]] = []
        for start_y in range(height):
            for start_x in range(width):
                offset = start_y * width + start_x
                if visited[offset] or pixels[start_x, start_y] < 32:
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
                                and pixels[next_x, next_y] >= 32
                            ):
                                visited[next_offset] = 1
                                stack.append((next_x, next_y))
                components.append(component)
        if not components:
            raise AssertionError("帧中没有有效角色主体")
        subject = max(components, key=len)
        xs = [point[0] for point in subject]
        ys = [point[1] for point in subject]
        return min(xs), min(ys), max(xs) + 1, max(ys) + 1

    def test_interactions_have_real_middle_frames(self) -> None:
        actions = self.manifest["actions"]
        self.assertGreaterEqual(len(actions["click"]["frames"]), 10)
        self.assertGreaterEqual(len(actions["wave"]["frames"]), 8)
        self.assertGreaterEqual(len(actions["heart"]["frames"]), 8)
        self.assertGreater(sum(actions["click"]["durations_ms"]), 1800)
        self.assertGreater(sum(actions["wave"]["durations_ms"]), 3000)
        self.assertGreater(sum(actions["heart"]["durations_ms"]), 3500)

    def test_wave_frames_have_no_cross_cell_vertical_jump(self) -> None:
        sheet_path = MANIFEST_PATH.parent / self.manifest["spritesheet"]
        sheet = Image.open(sheet_path).convert("RGBA")
        heights: list[int] = []
        bottoms: list[int] = []
        for x, y, width, height in self.manifest["actions"]["wave"]["frames"]:
            bounds = sheet.crop(
                (x, y, x + width, y + height)
            ).getchannel("A").getbbox()
            self.assertIsNotNone(bounds)
            assert bounds is not None
            heights.append(bounds[3] - bounds[1])
            bottoms.append(bounds[3])
        self.assertLessEqual(max(heights), 280)
        self.assertLessEqual(max(heights) - min(heights), 16)
        self.assertLessEqual(max(bottoms) - min(bottoms), 1)

    def test_interaction_actions_are_valid(self) -> None:
        known = set(self.manifest["actions"])
        interaction = self.manifest["interaction"]
        self.assertTrue(set(interaction["click_actions"]) <= known)
        self.assertTrue(set(interaction["random_idle_actions"]) <= known)
        self.assertEqual(
            set(interaction["random_idle_actions"]),
            set(interaction["random_idle_weights"]),
        )
        self.assertTrue(
            all(value > 0 for value in interaction["random_idle_weights"].values())
        )

    def test_idle_is_quiet_and_moves_about_every_five_seconds(self) -> None:
        actions = self.manifest["actions"]
        self.assertEqual(1, len(actions["idle"]["frames"]))
        self.assertEqual(1, len(actions["time_morning"]["frames"]))
        self.assertEqual(1, len(actions["time_day"]["frames"]))
        self.assertEqual(1, len(actions["time_night"]["frames"]))

        delay_min, delay_max = self.manifest["interaction"][
            "random_idle_delay_ms"
        ]
        self.assertGreaterEqual(delay_min, 4000)
        self.assertLessEqual(delay_max, 6500)
        self.assertLess(delay_min, delay_max)
        self.assertGreaterEqual(len(actions["idle_motion"]["frames"]), 7)

        motion_actions = self.manifest["time_state"]["motion_actions"]
        self.assertEqual({"morning", "day", "night"}, set(motion_actions))
        for action_name in motion_actions.values():
            self.assertIn(action_name, actions)
            self.assertFalse(actions[action_name]["loop"])
            self.assertGreaterEqual(len(actions[action_name]["frames"]), 7)

    def test_smooth_render_and_stable_click_configuration(self) -> None:
        animation = self.manifest["animation"]
        self.assertGreaterEqual(animation["render_fps"], 24)
        self.assertLessEqual(animation["render_fps"], 60)
        self.assertGreater(animation["tween_fraction"], 0)
        self.assertTrue(
            {"click", "wave", "idle_motion"}
            <= set(animation["tween_actions"])
        )
        # Cross-fading two noticeably tilted whole-body frames creates a
        # double-image ghost. These actions use their real source frames only.
        self.assertNotIn("sit_sway", animation["tween_actions"])
        self.assertNotIn("cheek_puff", animation["tween_actions"])

        click_actions = self.manifest["interaction"]["click_actions"]
        self.assertTrue(click_actions)
        for action_name in click_actions:
            self.assertGreaterEqual(
                len(self.manifest["actions"][action_name]["frames"]),
                8,
            )

    def test_sigh_and_small_idle_actions_have_time_to_read(self) -> None:
        actions = self.manifest["actions"]
        self.assertGreaterEqual(sum(actions["idle_motion"]["durations_ms"]), 6000)
        self.assertGreaterEqual(max(actions["idle_motion"]["durations_ms"]), 1800)
        self.assertGreaterEqual(actions["idle_motion"]["durations_ms"][1], 1000)
        self.assertGreaterEqual(actions["idle_motion"]["durations_ms"][5], 900)
        self.assertGreaterEqual(sum(actions["click"]["durations_ms"]), 3500)
        self.assertGreaterEqual(sum(actions["cute_idle"]["durations_ms"]), 3500)
        self.assertGreaterEqual(sum(actions["wave"]["durations_ms"]), 4500)
        self.assertGreaterEqual(sum(actions["shy"]["durations_ms"]), 4000)
        self.assertGreaterEqual(sum(actions["sleepy"]["durations_ms"]), 4500)
        for action_name in self.manifest["time_state"]["motion_actions"].values():
            self.assertGreaterEqual(
                sum(actions[action_name]["durations_ms"]),
                3800,
                action_name,
            )

    def test_click_action_subject_anchor_is_stable(self) -> None:
        sheet_path = MANIFEST_PATH.parent / self.manifest["spritesheet"]
        sheet = Image.open(sheet_path).convert("RGBA")
        centers: list[float] = []
        bottoms: list[int] = []

        for action_name in self.manifest["interaction"]["click_actions"]:
            for x, y, width, height in self.manifest["actions"][action_name]["frames"]:
                alpha = sheet.crop((x, y, x + width, y + height)).getchannel("A")
                bounds = self._dominant_alpha_bounds(alpha)
                left, _top, right, _bottom = bounds
                centers.append((left + right) / 2)
                bottoms.append(bounds[3])

        self.assertLessEqual(max(centers) - min(centers), 1.0)
        self.assertLessEqual(max(bottoms) - min(bottoms), 0)

    def test_surprise_sigh_and_wave_visual_alignment(self) -> None:
        sheet_path = MANIFEST_PATH.parent / self.manifest["spritesheet"]
        sheet = Image.open(sheet_path).convert("RGBA")
        actions = self.manifest["actions"]

        x, y, width, height = actions["idle"]["frames"][0]
        idle_bounds = sheet.crop(
            (x, y, x + width, y + height)
        ).getchannel("A").getbbox()
        self.assertIsNotNone(idle_bounds)
        assert idle_bounds is not None
        idle_center = (idle_bounds[0] + idle_bounds[2]) / 2
        idle_height = idle_bounds[3] - idle_bounds[1]

        for frame_index in (1, 3):
            x, y, width, height = actions["idle_motion"]["frames"][frame_index]
            bounds = sheet.crop(
                (x, y, x + width, y + height)
            ).getchannel("A").getbbox()
            self.assertIsNotNone(bounds)
            assert bounds is not None
            center = (bounds[0] + bounds[2]) / 2
            self.assertLessEqual(abs(center - idle_center), 3.0)

        wave_heights: list[int] = []
        for x, y, width, height in actions["wave"]["frames"][1:-1]:
            bounds = sheet.crop(
                (x, y, x + width, y + height)
            ).getchannel("A").getbbox()
            self.assertIsNotNone(bounds)
            assert bounds is not None
            wave_heights.append(bounds[3] - bounds[1])
        self.assertGreaterEqual(min(wave_heights), idle_height - 6)
        self.assertLessEqual(max(wave_heights), idle_height + 2)

    def test_upper_gaze_frame_mapping_is_not_reversed(self) -> None:
        gaze_frames = self.manifest["gaze"]["frames"]
        self.assertEqual([768, 8000, 256, 320], gaze_frames["upper_left"])
        self.assertEqual([256, 8000, 256, 320], gaze_frames["upper_right"])

    def test_click_guard_and_bubble_dismiss_are_implemented(self) -> None:
        source = PET_APP_PATH.read_text(encoding="utf-8")
        self.assertIn("def dismiss(self) -> None:", source)
        self.assertIn("if self._speech_bubble.isVisible():", source)
        self.assertIn("if self._interaction_active:", source)
        self.assertIn("self._dismiss_bubble_on_release", source)

    def test_gaze_time_anger_and_speech_configuration(self) -> None:
        gaze = self.manifest["gaze"]
        self.assertTrue(gaze["enabled_default"])
        self.assertGreaterEqual(gaze["radius_px"], 1000)
        self.assertEqual(2, len(gaze["spontaneous_delay_ms"]))
        self.assertEqual(2, len(gaze["duration_ms"]))
        self.assertGreater(gaze["click_follow_duration_ms"], 0)
        circle = gaze["circle_gesture"]
        self.assertEqual(2.0, circle["turns"])
        self.assertGreater(circle["min_radius_px"], 0)
        self.assertGreater(
            circle["max_sample_gap_ms"],
            gaze["poll_interval_ms"],
        )
        self.assertLess(circle["max_step_degrees"], 180)
        self.assertGreater(circle["dizzy_cooldown_ms"], 0)
        self.assertEqual(
            {
                "left",
                "upper_left",
                "up",
                "upper_right",
                "right",
                "lower_right",
                "down",
                "lower_left",
            },
            set(gaze["frames"]),
        )

        time_state = self.manifest["time_state"]
        self.assertEqual("08:30", time_state["work_start"])
        self.assertEqual("11:40", time_state["lunch_start"])
        self.assertEqual("12:30", time_state["lunch_end"])
        self.assertEqual("17:20", time_state["work_end"])
        self.assertEqual(
            {"morning", "day", "night"},
            set(time_state["visual_actions"]),
        )
        self.assertTrue(
            set(time_state["visual_actions"].values())
            <= set(self.manifest["actions"])
        )
        self.assertEqual(
            {"idle"},
            set(time_state["visual_actions"].values()),
        )

        anger = self.manifest["anger"]
        self.assertGreaterEqual(anger["click_threshold"], 2)
        self.assertGreater(anger["click_window_ms"], 0)
        self.assertGreater(anger["duration_ms"], 0)
        self.assertFalse(self.manifest["actions"]["angry_enter"]["loop"])
        self.assertTrue(self.manifest["actions"]["angry_hold"]["loop"])
        self.assertFalse(self.manifest["actions"]["angry_calm"]["loop"])

        speech = self.manifest["speech"]
        self.assertTrue(speech["enabled_default"])
        self.assertEqual(2, len(speech["delay_ms"]))
        self.assertLess(speech["delay_ms"][0], speech["delay_ms"][1])
        for phase in (
            "early_morning",
            "before_work",
            "work_morning",
            "lunch",
            "work_afternoon",
            "after_work",
            "night",
            "day_off",
            "angry",
        ):
            self.assertTrue(speech["phrases"][phase])

    def test_circle_tracker_accepts_both_directions_and_rejects_wobble(self) -> None:
        def completes_circle(direction: int) -> bool:
            tracker = CircleGestureTracker(required_turns=2.0)
            triggered = False
            for index in range(74):
                angle = math.radians(direction * index * 10)
                triggered = tracker.sample(
                    160 * math.cos(angle),
                    160 * math.sin(angle),
                    now=index * 0.1,
                    min_radius_px=70,
                )
                if triggered:
                    break
            return triggered

        self.assertTrue(completes_circle(1))
        self.assertTrue(completes_circle(-1))

        tracker = CircleGestureTracker(required_turns=2.0)
        triggered = False
        for index in range(120):
            angle = math.radians(25 if index % 2 else -25)
            triggered = tracker.sample(
                160 * math.cos(angle),
                160 * math.sin(angle),
                now=index * 0.1,
                min_radius_px=70,
            )
            self.assertFalse(triggered)
        self.assertLess(tracker.progress, 0.2)

    def test_dizzy_action_and_assets_are_stable_for_both_outfits(self) -> None:
        action = self.manifest["actions"]["dizzy"]
        self.assertFalse(action["loop"])
        self.assertEqual(10, len(action["frames"]))
        self.assertGreaterEqual(sum(action["durations_ms"]), 4000)
        self.assertNotIn("dizzy", self.manifest["animation"]["tween_actions"])

        for outfit in self.manifest["outfits"].values():
            sheet = Image.open(
                MANIFEST_PATH.parent / outfit["spritesheet"]
            ).convert("RGBA")
            subject_heights: list[int] = []
            subject_bottoms: list[int] = []
            core_centers: list[float] = []
            top_margins: list[int] = []
            for x, y, width, height in action["frames"][1:-1]:
                alpha = sheet.crop(
                    (x, y, x + width, y + height)
                ).getchannel("A")
                left, top, right, bottom = self._dominant_alpha_bounds(alpha)
                del left, right
                subject_heights.append(bottom - top)
                subject_bottoms.append(bottom)
                core_centers.append(_character_core_center_x(alpha))
                alpha_bounds = alpha.getbbox()
                self.assertIsNotNone(alpha_bounds)
                assert alpha_bounds is not None
                top_margins.append(alpha_bounds[1])
            # A connected star-ring can extend the dominant alpha component
            # by a few pixels without changing the character's body scale.
            self.assertLessEqual(max(subject_heights) - min(subject_heights), 5)
            self.assertEqual(0, max(subject_bottoms) - min(subject_bottoms))
            self.assertLessEqual(max(core_centers) - min(core_centers), 1.5)
            self.assertGreaterEqual(min(top_margins), 20)

        source = PET_APP_PATH.read_text(encoding="utf-8")
        self.assertIn("def play_dizzy_reaction(self) -> bool:", source)
        self.assertIn('"预览晕头转向动作"', source)

    def test_new_cute_actions_are_slow_and_stably_anchored(self) -> None:
        sheet_path = MANIFEST_PATH.parent / self.manifest["spritesheet"]
        sheet = Image.open(sheet_path).convert("RGBA")
        for action_name in ("heart", "sit_sway", "curtsey", "cheek_puff"):
            action = self.manifest["actions"][action_name]
            self.assertFalse(action["loop"])
            self.assertGreaterEqual(len(action["frames"]), 8)
            self.assertGreater(sum(action["durations_ms"]), 3000)
            centers: list[float] = []
            bottoms: list[int] = []
            for x, y, width, height in action["frames"]:
                bounds = self._dominant_alpha_bounds(
                    sheet.crop(
                        (x, y, x + width, y + height)
                    ).getchannel("A")
                )
                centers.append((bounds[0] + bounds[2]) / 2)
                bottoms.append(bounds[3])
            self.assertLessEqual(max(centers) - min(centers), 1.0, action_name)
            self.assertLessEqual(max(bottoms) - min(bottoms), 0, action_name)

    def test_message_notification_is_ready_for_future_calls(self) -> None:
        actions = self.manifest["actions"]
        self.assertFalse(actions["message_notify_enter"]["loop"])
        self.assertTrue(actions["message_notify_hold"]["loop"])
        self.assertFalse(actions["message_notify_exit"]["loop"])
        self.assertFalse(actions["message_notify"]["loop"])
        self.assertEqual(18, len(actions["message_notify"]["frames"]))
        self.assertGreaterEqual(
            sum(actions["message_notify"]["durations_ms"]),
            7500,
        )
        self.assertNotIn(
            "message_notify",
            self.manifest["animation"]["tween_actions"],
        )

        sheet = Image.open(
            MANIFEST_PATH.parent / self.manifest["spritesheet"]
        ).convert("RGBA")
        core_centers: list[float] = []
        bottoms: list[int] = []
        heights: list[int] = []
        for action_name in (
            "message_notify_enter",
            "message_notify_hold",
            "message_notify_exit",
        ):
            for x, y, width, height in actions[action_name]["frames"]:
                alpha = sheet.crop(
                    (x, y, x + width, y + height)
                ).getchannel("A")
                bounds = self._dominant_alpha_bounds(alpha)
                core_centers.append(_character_core_center_x(alpha))
                bottoms.append(bounds[3])
                heights.append(bounds[3] - bounds[1])
        self.assertLessEqual(max(core_centers) - min(core_centers), 1.5)
        self.assertLessEqual(max(bottoms) - min(bottoms), 0)
        self.assertLessEqual(max(heights) - min(heights), 5)

        source = PET_APP_PATH.read_text(encoding="utf-8")
        self.assertIn("def play_message_notification(self) -> bool:", source)
        self.assertIn('"预览消息提示动作"', source)

    def test_chat_api_messages_are_normalized_and_deduplicated(self) -> None:
        initial_payload = {
            "ok": True,
            "data": [
                {
                    "id": 10,
                    "send_user": "A",
                    "msg": "旧消息",
                    "send_time": "2026-07-29 12:00:00",
                }
            ],
        }
        next_payload = {
            "ok": True,
            "data": [
                *initial_payload["data"],
                {
                    "id": 11,
                    "sender": {"name": "B"},
                    "content": "新消息",
                    "created_at": "2026-07-29 12:01:00",
                },
            ],
        }
        tracker = MessageSnapshotTracker()
        self.assertEqual([], tracker.ingest(extract_message_records(initial_payload)))
        new_records = tracker.ingest(extract_message_records(next_payload))
        self.assertEqual(1, len(new_records))
        self.assertEqual("B", new_records[0].sender)
        self.assertEqual("新消息", new_records[0].content)
        self.assertEqual([], tracker.ingest(extract_message_records(next_payload)))

    def test_duplicate_text_messages_are_counted_as_separate_occurrences(self) -> None:
        tracker = MessageSnapshotTracker()
        message = {"sender": "A", "message": "相同正文"}
        self.assertEqual([], tracker.ingest(extract_message_records([message])))
        new_records = tracker.ingest(
            extract_message_records([message, message])
        )
        self.assertEqual(1, len(new_records))

    def test_private_optional_config_is_ignored_and_not_embedded_in_exe(self) -> None:
        gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("*.private.json", gitignore.splitlines())
        self.assertFalse((PROJECT_ROOT / "chat_config.example.json").exists())

        build_script = BUILD_SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertIn(
            'copy /Y "desktop_pet.private.json" "dist\\desktop_pet.private.json"',
            build_script,
        )
        self.assertNotIn(
            '--add-data "desktop_pet.private.json',
            build_script,
        )

    def test_removed_game_feature_has_no_runtime_or_release_residue(self) -> None:
        source = PET_APP_PATH.read_text(encoding="utf-8")
        build_script = BUILD_SCRIPT_PATH.read_text(encoding="utf-8")
        package_script = (
            PROJECT_ROOT / "tools" / "package_release.py"
        ).read_text(encoding="utf-8")
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertFalse((PROJECT_ROOT / "plugins").exists())
        self.assertFalse((PROJECT_ROOT / "plugin_manager.py").exists())
        self.assertFalse((PROJECT_ROOT / "THIRD_PARTY_NOTICES.md").exists())
        for forbidden in (
            "adarkroom_native",
            "DarkRoomHost",
            "NativeDarkRoomGame",
            "GAME_PLUGIN_ID",
            "_game_host",
            "game_notifications_enabled",
        ):
            self.assertNotIn(forbidden, source)
            self.assertNotIn(forbidden, package_script)
        self.assertNotIn("plugins\\adarkroom_native", build_script)
        self.assertIn("完整移除黑暗房间游戏功能", readme)

    def test_optional_monitor_is_config_presence_driven_and_hidden_when_absent(
        self,
    ) -> None:
        source = PET_APP_PATH.read_text(encoding="utf-8")
        self.assertIn("ChatMonitor(self._chat_config, self)", source)
        self.assertIn(
            "self._chat_monitor.new_messages.connect(self._on_chat_messages)",
            source,
        )
        self.assertIn("self._message_popup.show_messages(", source)
        self.assertIn("if self.play_message_notification():", source)
        self.assertIn("if private_config_path.is_file():", source)
        self.assertIn("if self._chat_monitor is not None:", source)
        self.assertNotIn('"网页新消息提醒"', source)
        self.assertNotIn("chat_monitor_enabled", source)

        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        for hidden_term in (
            "chat_config",
            "desktop_pet.private",
            "WebSocket",
            "网页新消息",
            "聊天网页",
            "API 轮询",
        ):
            self.assertNotIn(hidden_term, readme)

    def test_new_character_assets_keep_a_stable_baseline(self) -> None:
        sheet_path = MANIFEST_PATH.parent / self.manifest["spritesheet"]
        sheet = Image.open(sheet_path).convert("RGBA")
        action_names = (
            "time_morning",
            "time_day",
            "time_night",
            "angry_enter",
            "angry_hold",
            "angry_calm",
        )
        for action_name in action_names:
            bottoms: list[int] = []
            heights: list[int] = []
            for x, y, width, height in self.manifest["actions"][action_name]["frames"]:
                bounds = sheet.crop(
                    (x, y, x + width, y + height)
                ).getchannel("A").getbbox()
                self.assertIsNotNone(bounds)
                assert bounds is not None
                bottoms.append(bounds[3])
                heights.append(bounds[3] - bounds[1])
            self.assertLessEqual(max(bottoms) - min(bottoms), 1, action_name)
            self.assertLessEqual(max(heights) - min(heights), 9, action_name)

        gaze_heights: list[int] = []
        gaze_bottoms: list[int] = []
        for x, y, width, height in self.manifest["gaze"]["frames"].values():
            bounds = sheet.crop(
                (x, y, x + width, y + height)
            ).getchannel("A").getbbox()
            self.assertIsNotNone(bounds)
            assert bounds is not None
            gaze_heights.append(bounds[3] - bounds[1])
            gaze_bottoms.append(bounds[3])
        self.assertLessEqual(max(gaze_bottoms) - min(gaze_bottoms), 1)
        self.assertLessEqual(max(gaze_heights) - min(gaze_heights), 9)

    def test_sleep_drag_and_edge_action_configuration(self) -> None:
        actions = self.manifest["actions"]
        self.assertFalse(actions["sit_down"]["loop"])
        self.assertFalse(actions["doze_off"]["loop"])
        self.assertTrue(actions["sleep"]["loop"])
        self.assertFalse(actions["wake"]["loop"])
        self.assertFalse(actions["peek_left"]["loop"])
        self.assertFalse(actions["peek_right"]["loop"])
        self.assertTrue(actions["peek_left_hold"]["loop"])
        self.assertTrue(actions["peek_right_hold"]["loop"])
        self.assertEqual(1, len(actions["peek_left_hold"]["frames"]))
        self.assertEqual(1, len(actions["peek_right_hold"]["frames"]))
        self.assertEqual(9, len(actions["peek_left_exit"]["frames"]))
        self.assertEqual(9, len(actions["peek_right_exit"]["frames"]))
        self.assertFalse(actions["grab_lift"]["loop"])
        self.assertTrue(actions["held_drag"]["loop"])
        self.assertFalse(actions["release_fall"]["loop"])
        self.assertFalse(actions["soft_land"]["loop"])

        sleep = self.manifest["sleep"]
        self.assertTrue(sleep["enabled_default"])
        self.assertEqual(2, len(sleep["inactivity_delay_ms"]))
        self.assertLess(sleep["inactivity_delay_ms"][0], sleep["inactivity_delay_ms"][1])
        self.assertEqual(2, len(sleep["duration_ms"]))
        self.assertGreater(sleep["duration_ms"][0], 0)
        self.assertLess(sleep["duration_ms"][0], sleep["duration_ms"][1])
        source = PET_APP_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "self._auto_wake_timer.timeout.connect(self._wake_from_sleep)",
            source,
        )
        self.assertIn("transition_ms + random.randint", source)

    def test_common_actions_enter_and_leave_through_neutral_idle(self) -> None:
        idle_frame = self.manifest["actions"]["idle"]["frames"][0]
        actions = self.manifest["actions"]
        for action_name in (
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
            "dizzy",
            "time_morning_motion",
            "time_day_motion",
            "time_night_motion",
        ):
            self.assertEqual(idle_frame, actions[action_name]["frames"][0], action_name)
            self.assertEqual(idle_frame, actions[action_name]["frames"][-1], action_name)
        self.assertEqual(idle_frame, actions["walk_start"]["frames"][0])
        self.assertEqual(idle_frame, actions["walk_stop"]["frames"][-1])
        self.assertEqual(idle_frame, actions["wake"]["frames"][-1])
        self.assertEqual(idle_frame, actions["soft_land"]["frames"][-1])
        self.assertEqual(idle_frame, actions["angry_enter"]["frames"][0])
        self.assertEqual(idle_frame, actions["angry_calm"]["frames"][-1])

    def test_left_and_right_peek_artwork_are_exact_mirrors(self) -> None:
        sheet_path = MANIFEST_PATH.parent / self.manifest["spritesheet"]
        sheet = Image.open(sheet_path).convert("RGBA")
        for left_action, right_action in (
            ("peek_left_enter", "peek_right_enter"),
            ("peek_left", "peek_right"),
        ):
            left_frames = self.manifest["actions"][left_action]["frames"]
            right_frames = self.manifest["actions"][right_action]["frames"]
            self.assertEqual(len(left_frames), len(right_frames))
            for left_rect, right_rect in zip(left_frames, right_frames):
                lx, ly, lw, lh = left_rect
                rx, ry, rw, rh = right_rect
                left = sheet.crop((lx, ly, lx + lw, ly + lh)).transpose(
                    Image.Transpose.FLIP_LEFT_RIGHT
                )
                right = sheet.crop((rx, ry, rx + rw, ry + rh))
                self.assertIsNone(
                    ImageChops.difference(left, right).getbbox(),
                    f"{left_action} 与 {right_action} 不完全镜像",
                )

    def test_drop_and_landing_return_to_full_character_scale(self) -> None:
        sheet_path = MANIFEST_PATH.parent / self.manifest["spritesheet"]
        sheet = Image.open(sheet_path).convert("RGBA")
        actions = self.manifest["actions"]

        def subject_height(rect: list[int]) -> int:
            x, y, width, height = rect
            alpha = sheet.crop((x, y, x + width, y + height)).getchannel("A")
            left, top, right, bottom = self._dominant_alpha_bounds(alpha)
            del left, right
            return bottom - top

        idle_height = subject_height(actions["idle"]["frames"][0])
        landing_pose_height = subject_height(actions["soft_land"]["frames"][-2])
        self.assertLessEqual(abs(landing_pose_height - idle_height), 5)

        release_last = subject_height(actions["release_fall"]["frames"][-1])
        landing_first = subject_height(actions["soft_land"]["frames"][0])
        # The released hand can touch the headband and merge into the same
        # alpha component. Compare the visible character region below the hand
        # rather than treating the hand as part of the pet's height.
        release_visible_height = min(release_last, 320 - 80)
        self.assertLessEqual(abs(release_visible_height - landing_first), 20)

        source = PET_APP_PATH.read_text(encoding="utf-8")
        self.assertIn('("walk_start",)', source)
        self.assertIn('("walk_stop",)', source)
        self.assertIn('{"walk", "walk_start", "walk_stop"}', source)

    def test_scaling_walking_layer_and_edge_peek_configuration(self) -> None:
        scaling = self.manifest["scaling"]
        self.assertIn(scaling["default_percent"], scaling["options_percent"])
        self.assertEqual(sorted(set(scaling["options_percent"])), scaling["options_percent"])

        movement = self.manifest["movement"]
        self.assertEqual(2, len(movement["auto_walk_delay_ms"]))
        self.assertEqual(2, len(movement["auto_walk_duration_ms"]))
        self.assertLess(
            movement["auto_walk_delay_ms"][0],
            movement["auto_walk_delay_ms"][1],
        )

        edge_peek = self.manifest["edge_peek"]
        self.assertGreaterEqual(edge_peek["snap_distance_px"], 0)
        self.assertEqual(["left", "right"], edge_peek["enabled_edges"])
        self.assertEqual(2, len(edge_peek["motion_delay_ms"]))
        self.assertLess(edge_peek["motion_delay_ms"][0], edge_peek["motion_delay_ms"][1])
        self.assertGreater(edge_peek["reveal_animation_ms"], 500)
        self.assertTrue(self.manifest["window_layer"]["desktop_layer_default"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import struct
import unittest
from pathlib import Path

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "assets" / "sprite_manifest.json"


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

    def test_expanded_sheet_dimensions(self) -> None:
        sheet_path = MANIFEST_PATH.parent / self.manifest["spritesheet"]
        self.assertEqual((1024, 8000), png_size(sheet_path))

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

    def test_sleep_subject_anchor_does_not_jump(self) -> None:
        sheet_path = MANIFEST_PATH.parent / self.manifest["spritesheet"]
        sheet = Image.open(sheet_path).convert("RGBA")
        centers: list[float] = []
        bottoms: list[int] = []

        for action_name in ("sit_down", "doze_off", "sleep", "wake"):
            for x, y, width, height in self.manifest["actions"][action_name]["frames"]:
                alpha = sheet.crop((x, y, x + width, y + height)).getchannel("A")
                left, _top, right, _bottom = self._robust_alpha_bounds(alpha)
                centers.append((left + right) / 2)
                bottoms.append(self._meaningful_alpha_bottom(alpha))

        self.assertLessEqual(max(centers) - min(centers), 3.0)
        self.assertLessEqual(max(bottoms) - min(bottoms), 2)

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

    def test_interactions_have_real_middle_frames(self) -> None:
        actions = self.manifest["actions"]
        self.assertEqual(8, len(actions["click"]["frames"]))
        self.assertEqual(8, len(actions["wave"]["frames"]))
        self.assertGreater(sum(actions["click"]["durations_ms"]), 1800)
        self.assertGreater(sum(actions["wave"]["durations_ms"]), 1800)

    def test_interaction_actions_are_valid(self) -> None:
        known = set(self.manifest["actions"])
        interaction = self.manifest["interaction"]
        self.assertTrue(set(interaction["click_actions"]) <= known)
        self.assertTrue(set(interaction["random_idle_actions"]) <= known)

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
        self.assertEqual(8, len(actions["peek_left_exit"]["frames"]))
        self.assertEqual(8, len(actions["peek_right_exit"]["frames"]))
        self.assertFalse(actions["grab_lift"]["loop"])
        self.assertTrue(actions["held_drag"]["loop"])
        self.assertFalse(actions["release_fall"]["loop"])
        self.assertFalse(actions["soft_land"]["loop"])

        sleep = self.manifest["sleep"]
        self.assertTrue(sleep["enabled_default"])
        self.assertEqual(2, len(sleep["inactivity_delay_ms"]))
        self.assertLess(sleep["inactivity_delay_ms"][0], sleep["inactivity_delay_ms"][1])

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

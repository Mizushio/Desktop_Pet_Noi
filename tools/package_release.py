from __future__ import annotations

import argparse
import hashlib
import tempfile
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT.parent / "WindowsDesktopPet_v1.0.zip"

ROOT_FILES = (
    ".gitignore",
    "README.md",
    "build_exe.bat",
    "circle_gesture.py",
    "main.py",
    "optional_payload.py",
    "optional_runtime.py",
    "pet_app.py",
    "requirements-build.txt",
    "requirements-tools.txt",
    "requirements.txt",
    "run.bat",
)
TOOL_FILES = (
    "tools/audit_animation_consistency.py",
    "tools/package_release.py",
    "tools/prepare_action_pack.py",
)
TEST_FILES = ("tests/test_project.py",)
RUNTIME_ASSETS = (
    "assets/character_spritesheet.png",
    "assets/character_spritesheet_dark_green.png",
    "assets/pet.ico",
    "assets/sprite_manifest.json",
)


def release_files() -> list[Path]:
    relative_paths = {
        *(Path(name) for name in ROOT_FILES),
        *(Path(name) for name in TOOL_FILES),
        *(Path(name) for name in TEST_FILES),
        *(Path(name) for name in RUNTIME_ASSETS),
    }
    private_config = Path("desktop_pet.private.json")
    if (PROJECT_ROOT / private_config).is_file():
        relative_paths.add(private_config)

    files = sorted(relative_paths)
    missing = [path for path in files if not (PROJECT_ROOT / path).is_file()]
    if missing:
        raise FileNotFoundError(
            "发布白名单包含不存在的文件: "
            + ", ".join(path.as_posix() for path in missing)
        )
    return files


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_archive(output_path: Path, files: list[Path]) -> None:
    expected_names = {path.as_posix() for path in files}
    with zipfile.ZipFile(output_path, "r") as archive:
        corrupt = archive.testzip()
        if corrupt is not None:
            raise RuntimeError(f"ZIP CRC 检查失败: {corrupt}")
        actual_names = {info.filename for info in archive.infolist()}
        if actual_names != expected_names:
            missing = sorted(expected_names - actual_names)
            extra = sorted(actual_names - expected_names)
            raise RuntimeError(
                f"ZIP 文件清单不一致；缺少={missing}，多出={extra}"
            )

        with tempfile.TemporaryDirectory(prefix="desktop_pet_release_") as temp_dir:
            extracted_root = Path(temp_dir)
            archive.extractall(extracted_root)
            for relative_path in files:
                source_path = PROJECT_ROOT / relative_path
                extracted_path = extracted_root / relative_path
                if file_hash(source_path) != file_hash(extracted_path):
                    raise RuntimeError(f"独立解压字节校验失败: {relative_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="创建仅含运行、测试和精简素材所需文件的桌宠发布包"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"输出 ZIP 路径（默认: {DEFAULT_OUTPUT}）",
    )
    args = parser.parse_args()
    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    files = release_files()
    with zipfile.ZipFile(
        output_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        allowZip64=True,
    ) as archive:
        for relative_path in files:
            archive.write(
                PROJECT_ROOT / relative_path,
                arcname=relative_path.as_posix(),
            )

    verify_archive(output_path, files)
    total_source_bytes = sum((PROJECT_ROOT / path).stat().st_size for path in files)
    print(
        f"已生成并验证: {output_path}\n"
        f"文件数: {len(files)}，源文件总计: {total_source_bytes} bytes，"
        f"ZIP: {output_path.stat().st_size} bytes"
    )


if __name__ == "__main__":
    main()

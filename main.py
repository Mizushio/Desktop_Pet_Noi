from __future__ import annotations

import multiprocessing
import sys

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QApplication

from pet_app import DesktopPet


def main() -> int:
    multiprocessing.freeze_support()

    QCoreApplication.setOrganizationName("Mizushio")
    QCoreApplication.setApplicationName("DesktopPet")
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    pet = DesktopPet()
    pet.show()
    pet.place_at_saved_or_default_position()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

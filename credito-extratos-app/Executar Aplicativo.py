from __future__ import annotations

import subprocess
from pathlib import Path


def main() -> None:
    project_dir = Path(__file__).resolve().parent
    script_path = project_dir / "run_local.ps1"

    subprocess.Popen(
        [
            "powershell.exe",
            "-NoExit",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
        ],
        cwd=project_dir,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )


if __name__ == "__main__":
    main()

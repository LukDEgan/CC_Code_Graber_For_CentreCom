from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

# PyInstaller execs .spec files rather than importing them, so __file__ isn't
# defined here -- use the SPECPATH it injects into the exec namespace instead.
REPO_ROOT = Path(SPECPATH).resolve().parent

# sv_ttk ships .tcl theme files + sprite PNGs as package data with no
# PyInstaller hook of its own -- collect explicitly. Playwright's driver
# folder does NOT need an entry here: it registers its own PyInstaller hook
# (collect_data_files("playwright")) via a pyinstaller40 entry point,
# auto-discovered at build time as long as playwright is installed in the
# same build venv as pyinstaller.
datas = collect_data_files("sv_ttk")

a = Analysis(
    [str(REPO_ROOT / "main.py")],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CentreComTicketGenerator",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="CentreComTicketGenerator",
)

"""First-use setup, using only the Python standard library until the venv is ready."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import venv
import zipfile

ROOT = Path(__file__).resolve().parent
TYPST_VERSION = "0.15.1"
# SHA-256 digests published on the official typst/typst v0.15.1 release.
TYPST_ASSETS = {
    ("Windows", "x86_64"): ("x86_64-pc-windows-msvc.zip", "19ce3551153c2fe7ee9fa2f95208310c8f4d3209fedb699e0333faf8913f6736"),
    ("Windows", "aarch64"): ("aarch64-pc-windows-msvc.zip", "4ab28e1b71ec3184d38d580ab797f499b6770d952b6b19167be5cea5c2662e14"),
    ("Darwin", "x86_64"): ("x86_64-apple-darwin.tar.xz", "7f9fdd9584866245de9a79e0add8f9236fae6f40a8a45e2c4771ccc14db4e0fa"),
    ("Darwin", "aarch64"): ("aarch64-apple-darwin.tar.xz", "48f62ed034aa3a7978309579ac6ca00045e2ef0da73114e8af27cfd8e74dc05a"),
    ("Linux", "x86_64"): ("x86_64-unknown-linux-musl.tar.xz", "a6d077d0a95eed5a2eba715b2dae06be954f624ccbf85758a03f389ded33118c"),
    ("Linux", "aarch64"): ("aarch64-unknown-linux-musl.tar.xz", "5aa8d74a3d906e60ea12a66ac2f37f8eef1b14cbad7182a745e393a10c23dcee"),
}
FLAGS = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
CHECK = "import ipykernel, jupyter_client, nbformat, matplotlib, pandas, PIL; from packaging.requirements import Requirement; from importlib.metadata import version; import sys; assert all(version(r.name) in r.specifier for r in (Requirement(line.strip()) for line in open(sys.argv[1]) if line.strip() and not line.lstrip().startswith('#')))"


def emit(**event):
    print(json.dumps(event, ensure_ascii=True), flush=True)


def cache_home():
    override = os.environ.get("CLAUDE_NOTEBOOK_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library/Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return base / "cc-notebook"


def environment_key(requirements):
    # Plugin cache moves and UI-only releases must not trigger package downloads.
    identity = ["setup-1", str(Path(sys.executable).resolve()), sys.version,
                platform.system(), platform.machine(), requirements]
    return hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:24]


def env_python(directory):
    return directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


@contextmanager
def install_lock(home, timeout=600):
    """OS locks are released even if setup crashes or the terminal closes."""
    with (home / "setup.lock").open("a+b") as lock:
        if os.name == "nt":
            import msvcrt
            lock.write(b"0")
            lock.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                lock.seek(0)
                if os.name == "nt":
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (OSError, BlockingIOError):
                if time.monotonic() >= deadline:
                    raise RuntimeError("Another setup is still running. Wait for it, then use /lab setup.")
                time.sleep(0.25)
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def healthy(python, log=None):
    try:
        result = subprocess.run([str(python), "-I", "-c", CHECK, str(ROOT / "requirements.txt")],
                                capture_output=True, timeout=90, **FLAGS)
        if log and result.returncode:
            with log.open('ab') as output:
                output.write(b'\nDependency verification:\n' + result.stdout + result.stderr)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired) as error:
        if log:
            with log.open('a', encoding='utf-8') as output:
                output.write('\nDependency verification: ' + str(error) + '\n')
        return False


def managed_python(home, log, repair=False):
    environments = home / "environments"
    environments.mkdir(exist_ok=True)
    key = environment_key((ROOT / "requirements.txt").read_text(encoding="utf-8"))
    marker = environments / (key + ".json")
    if not repair:
        try:
            directory = environments / json.loads(marker.read_text())["directory"]
            # Never follow an edited marker to a foreign or project environment.
            if directory.resolve().parent == environments.resolve() and healthy(env_python(directory)):
                emit(progress="Using the existing notebook environment.")
                return env_python(directory)
        except (OSError, ValueError, KeyError, TypeError):
            pass
    emit(progress="Creating an isolated Python environment…")
    directory = Path(tempfile.mkdtemp(prefix=key + "-", dir=environments))
    # A venv cannot be renamed after creation (its launchers contain absolute paths).
    # Replacements get a new directory; running kernels keep their original environment.
    try:
        try:
            venv.EnvBuilder(with_pip=True).create(directory)
        except Exception as error:
            raise RuntimeError("Python could not create a virtual environment. On Debian/Ubuntu install python3-venv, then retry /lab setup. " + str(error)) from error
        python = env_python(directory)
        emit(progress="Downloading Python packages from PyPI. This can take a few minutes…")
        with log.open("ab") as output:
            result = subprocess.run([str(python), "-I", "-m", "pip", "--isolated", "install",
                                     "--disable-pip-version-check", "--no-input", "--only-binary=:all:",
                                     "--index-url", "https://pypi.org/simple", "--timeout", "30", "--retries", "2",
                                     "-r", str(ROOT / "requirements.txt")], stdout=output, stderr=output,
                                    timeout=600, **FLAGS)
        if result.returncode or not healthy(python, log):
            raise RuntimeError("Python package installation or verification failed. Check your connection and setup log, then retry /lab setup.")
        temp = marker.with_suffix(".tmp")
        temp.write_text(json.dumps({"directory": directory.name}), encoding="utf-8")
        os.replace(temp, marker)
        return python
    except Exception:
        # Only remove this invocation's newly created, unused environment.
        if directory.resolve().parent == environments.resolve() and not directory.is_symlink():
            shutil.rmtree(directory, ignore_errors=True)
        raise


def typst_asset(system=None, machine=None):
    system = system or platform.system()
    machine = (machine or platform.machine()).lower()
    machine = {"amd64": "x86_64", "arm64": "aarch64"}.get(machine, machine)
    if (system, machine) not in TYPST_ASSETS:
        raise RuntimeError("No bundled Typst binary for this OS/architecture. Install Typst manually for advanced LaTeX.")
    return TYPST_ASSETS[system, machine]


def typst_works(path):
    try:
        result = subprocess.run([str(path), "--version"], capture_output=True, timeout=10, **FLAGS)
        return result.returncode == 0 and result.stdout.startswith(b"typst ")
    except (OSError, subprocess.TimeoutExpired):
        return False


def unpack_binary(archive, destination, expected):
    """Extract only the expected regular executable, never archive paths or links."""
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as bundle:
            entry = bundle.getinfo(expected)
            if entry.is_dir() or entry.file_size > 100_000_000 or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Invalid Typst executable in archive.")
            data = bundle.read(entry)
    else:
        with tarfile.open(archive, "r:xz") as bundle:
            entry = bundle.getmember(expected)
            if not entry.isfile() or entry.size > 100_000_000:
                raise ValueError("Invalid Typst executable in archive.")
            data = bundle.extractfile(entry).read()
    destination.write_bytes(data)
    destination.chmod(0o700)


def typst_binary(home):
    asset, _ = typst_asset()
    name = "typst-" + asset
    folder = home / "tools" / ("typst-" + TYPST_VERSION) / name.split(".")[0]
    return folder / ("typst.exe" if platform.system() == "Windows" else "typst")


def find_typst(home):
    """Read-only discovery shared by notebook setup and transcript rendering."""
    configured = os.environ.get("CLAUDE_NOTEBOOK_TYPST") or shutil.which("typst")
    if configured and typst_works(configured):
        return str(configured)
    binary = typst_binary(home)
    return str(binary) if binary.is_file() and typst_works(binary) else None


def install_typst(home):
    found = find_typst(home)
    if found:
        return found
    asset, checksum = typst_asset()
    name = "typst-" + asset
    binary = typst_binary(home)
    folder = binary.parent
    emit(progress="Downloading Typst for LaTeX and SVG previews…")
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="download-", dir=folder) as temp:
        archive = Path(temp) / name
        request = urllib.request.Request(f"https://github.com/typst/typst/releases/download/v{TYPST_VERSION}/{name}",
                                         headers={"User-Agent": "cc-notebook-setup"})
        digest, total = hashlib.sha256(), 0
        with urllib.request.urlopen(request, timeout=45) as response, archive.open("wb") as output:
            deadline = time.monotonic() + 120
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > 100_000_000 or time.monotonic() > deadline:
                    raise RuntimeError("Typst download exceeded its size or time limit.")
                digest.update(chunk)
                output.write(chunk)
        if digest.hexdigest() != checksum:
            raise RuntimeError("Typst checksum did not match the pinned official release. Download discarded.")
        candidate = Path(temp) / binary.name
        stem = name.removesuffix(".zip").removesuffix(".tar.xz")
        unpack_binary(archive, candidate, stem + "/" + binary.name)
        if not typst_works(candidate):
            raise RuntimeError("The downloaded Typst binary cannot run on this machine.")
        os.replace(candidate, binary)
    return str(binary)


def prepare_latex(typst, log):
    emit(progress="Preparing MiTeX and checking LaTeX rendering…")
    with tempfile.TemporaryDirectory(prefix="cc-notebook-equation-") as temp:
        root = Path(temp)
        (root / "test.typ").write_text('#import "@preview/mitex:0.2.7": mitex\n#set page(width:auto,height:auto)\n#mitex("x^2")', encoding="utf-8")
        with log.open("ab") as output:
            result = subprocess.run([str(typst), "compile", "--root", str(root), str(root / "test.typ"), str(root / "test.png")],
                                    stdout=output, stderr=output, timeout=90, **FLAGS)
        if result.returncode or not (root / "test.png").is_file():
            raise RuntimeError("MiTeX could not be prepared. Retry /lab setup when the network is available.")


def setup(home, log, repair=False):
    with install_lock(home):
        python = managed_python(home, log, repair)
        typst, warning, latex = None, None, False
        try:
            typst = install_typst(home)
            prepare_latex(typst, log)
            latex = True
        except Exception as error:
            warning = f"Advanced LaTeX setup incomplete: {error} Basic math and Python still work. Retry /lab setup."
        return {"python": str(python), "typst": typst, "latex": latex, "warning": warning,
                "home": str(home), "log": str(log)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repair", action="store_true", help="Build a replacement environment without modifying existing kernels")
    parser.add_argument("--find-typst", action="store_true", help="Report the existing Typst executable without installing or changing anything")
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        emit(ok=False, error="Python 3.10 or newer is required. Install Python, reopen your terminal, then retry /lab setup.")
        return 1
    home = cache_home()
    if args.find_typst:
        try:
            emit(typst=find_typst(home))
            return 0
        except Exception:
            emit(typst=None)
            return 1
    log = None
    try:
        home.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, path = tempfile.mkstemp(prefix="setup-", suffix=".log", dir=home)
        os.close(fd)
        log = Path(path)
        emit(progress="Checking notebook dependencies…", log=str(log))
        result = setup(home, log, args.repair)
        emit(ok=True, result=result)
        return 0
    except Exception as error:
        emit(ok=False, error=f"{error}\nSetup log: {log or home}\nRetry with /lab setup.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

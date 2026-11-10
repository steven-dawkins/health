#!/usr/bin/env python3
"""Zip every gitignored data source into one archive, preserving paths.

Usage: python3 backup_data.py [output.zip]   (default: datasources.zip)
Restore: unzip datasources.zip -d <repo root>

The file list comes from git (`ls-files --ignored`), so it follows .gitignore.
__pycache__ and the output archive itself are skipped.
"""
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def ignored_files():
    out = subprocess.run(
        ["git", "ls-files", "--others", "--ignored", "--exclude-standard", "-z"],
        cwd=ROOT, check=True, capture_output=True).stdout
    return sorted(p for p in out.decode().split("\0")
                  if p and "__pycache__" not in Path(p).parts)


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "datasources.zip").resolve()
    files = [f for f in ignored_files() if (ROOT / f).resolve() != out]
    total = sum((ROOT / f).stat().st_size for f in files)
    print(f"{len(files)} files, {total / 1e6:.0f} MB -> {out}")
    done = 0
    with zipfile.ZipFile(out, "w", allowZip64=True) as z:
        for f in files:
            src = ROOT / f
            # Already-compressed zips: store rather than waste CPU re-deflating.
            method = zipfile.ZIP_STORED if f.endswith(".zip") else zipfile.ZIP_DEFLATED
            z.write(src, f, compress_type=method)
            done += src.stat().st_size
            print(f"\r{done / total:6.1%}", end="", flush=True)
    print(f"\nWrote {out} ({out.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()

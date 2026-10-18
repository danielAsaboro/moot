"""Download the pinned benchmark revision and Canon's repo (for the ORACLE arm) if they are not already here."""
from __future__ import annotations

import shutil
import subprocess
import urllib.request

from moot.bench_erag import DATA, DATASET, REVISION, ROOT
from moot.bench_erag.oracle import INVENTORY

FILES = {"questions.parquet": "data/questions/test.parquet", "documents.parquet": "data/documents/test.parquet"}


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    for name, path in FILES.items():
        dest = DATA / name
        if not dest.exists():
            url = f"https://huggingface.co/datasets/{DATASET}/resolve/{REVISION}/{path}"
            print("downloading", url)
            with urllib.request.urlopen(url) as r, open(dest.with_suffix(".part"), "wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
            dest.with_suffix(".part").rename(dest)
    if not INVENTORY.exists():
        subprocess.run(["git", "clone", "-q", "https://github.com/Enoch208/canon", str(ROOT.parent / "canon-teardown")], check=True)
    print("data in", DATA)


if __name__ == "__main__":
    main()

"""Idempotently create runtime directories without replacing any files."""

from pathlib import Path


def bootstrap(root: Path) -> list[str]:
    """Create missing directories; fail clearly if a file occupies a directory path."""
    report = []
    for relative in ("data/reference", "data/cache", "data/user_uploads", "outputs"):
        path = root / relative
        existed = path.is_dir()
        path.mkdir(parents=True, exist_ok=True)
        report.append(f"{'OK' if existed else 'CREATED'} {path}")
    return report


if __name__ == "__main__":
    print("\n".join(bootstrap(Path(__file__).resolve().parents[1])))

# pipelines/preprocess.py
"""
Advanced preprocessing pipeline with multi-stage cleaning and quality checks
"""
import os, argparse, hashlib
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
from typing import Tuple, Dict, Optional
import json

from ._logging import setup_logger
from .utils_text import normalize_fa, redact_pii

log = setup_logger("preprocess")


class DocumentQualityChecker:
    """Quality assessment for documents"""

    MIN_LENGTH = 50  # minimum characters
    MAX_LENGTH = 1_000_000  # maximum characters
    MIN_WORD_COUNT = 10

    @staticmethod
    def check_quality(text: str) -> Tuple[bool, str, Dict]:
        """
        Returns: (is_valid, reason, metrics)
        """
        metrics = {
            "length": len(text),
            "word_count": len(text.split()),
            "line_count": len(text.splitlines()),
            "has_persian": any("\u0600" <= c <= "\u06ff" for c in text[:1000]),
        }

        if metrics["length"] < DocumentQualityChecker.MIN_LENGTH:
            return False, "too_short", metrics

        if metrics["length"] > DocumentQualityChecker.MAX_LENGTH:
            return False, "too_long", metrics

        if metrics["word_count"] < DocumentQualityChecker.MIN_WORD_COUNT:
            return False, "insufficient_words", metrics

        if not metrics["has_persian"]:
            return False, "no_persian_text", metrics

        return True, "valid", metrics


def _proc_file(fp: Path) -> Tuple[Path, Optional[str], Dict]:
    """
    Process a single file with quality checks
    Returns: (filepath, processed_text, metadata)
    """
    try:
        with open(fp, "r", encoding="utf-8", errors="ignore") as f:
            raw = f.read()

        # Quality check
        is_valid, reason, metrics = DocumentQualityChecker.check_quality(raw)

        metadata = {
            "source": str(fp),
            "original_size": len(raw),
            "quality_check": reason,
            **metrics,
        }

        if not is_valid:
            log.warning(f"Skipping {fp.name}: {reason}")
            return fp, None, metadata

        # Process
        t = normalize_fa(raw)
        t = redact_pii(t)

        # Generate hash for deduplication
        metadata["content_hash"] = hashlib.md5(t.encode()).hexdigest()
        metadata["processed_size"] = len(t)

        return fp, t, metadata

    except Exception as e:
        log.error(f"Error processing {fp}: {e}")
        return fp, None, {"error": str(e)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", required=True)
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--metadata_out", default=None, help="Save processing metadata")
    ap.add_argument("--deduplicate", action="store_true", help="Remove duplicate documents")
    ap.add_argument("--wandb", action="store_true", help="Enable W&B logging")
    args = ap.parse_args()

    # W&B init
    if args.wandb:
        import wandb

        wandb.init(project=os.getenv("WANDB_PROJECT", "mahoun"), name="preprocess", reinit=True)

    src, dst = Path(args.src), Path(args.dst)
    dst.mkdir(parents=True, exist_ok=True)

    files = [
        p for p in src.rglob("*") if p.is_file() and p.suffix.lower() in {".txt", ".json", ".jsonl"}
    ]
    log.info(f"Found {len(files)} files.")

    if args.wandb:
        wandb.log({"total_files": len(files), "workers": args.workers})

    # Process with progress tracking
    processed = 0
    skipped = 0
    failed = 0
    seen_hashes = set()
    duplicates = 0
    all_metadata = []

    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(_proc_file, fp): fp for fp in files}

        for future in tqdm(as_completed(futures), total=len(files), desc="preprocess"):
            fp, txt, metadata = future.result()
            all_metadata.append(metadata)

            if txt is None:
                if "error" in metadata:
                    failed += 1
                else:
                    skipped += 1
                continue

            # Deduplication
            if args.deduplicate:
                content_hash = metadata.get("content_hash")
                if content_hash in seen_hashes:
                    duplicates += 1
                    log.debug(f"Duplicate: {fp.name}")
                    continue
                seen_hashes.add(content_hash)

            # Save
            rel = fp.relative_to(src)
            out = dst / rel.with_suffix(".txt")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(txt, encoding="utf-8")
            processed += 1

    # Save metadata
    if args.metadata_out:
        meta_path = Path(args.metadata_out)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(all_metadata, f, ensure_ascii=False, indent=2)
        log.info(f"Metadata saved to {meta_path}")

    # Summary
    log.info(
        f"Preprocess complete: {processed} processed, {skipped} skipped, {failed} failed, {duplicates} duplicates"
    )

    if args.wandb:
        wandb.log(
            {
                "processed_files": processed,
                "skipped_files": skipped,
                "failed_files": failed,
                "duplicate_files": duplicates,
                "success_rate": processed / len(files) * 100 if files else 0,
                "status": "completed",
            }
        )

        # Quality distribution
        quality_dist = {}
        for m in all_metadata:
            reason = m.get("quality_check", "unknown")
            quality_dist[reason] = quality_dist.get(reason, 0) + 1

        wandb.log({"quality_distribution": quality_dist})
        wandb.finish()


if __name__ == "__main__":
    main()

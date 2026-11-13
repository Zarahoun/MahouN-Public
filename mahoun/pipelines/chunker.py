# pipelines/chunker.py
import os, argparse, json
from pathlib import Path
from ._logging import setup_logger
from .utils_text import sent_tokenize_simple

log = setup_logger("chunker")


def chunk_text(text: str, target=600, overlap=80) -> list[str]:
    """Classic simple chunking (backward compatibility)"""
    sents = sent_tokenize_simple(text)
    chunks, buf = [], []
    count = 0
    for s in sents:
        buf.append(s)
        count += len(s.split())
        if count >= target:
            chunks.append(" ".join(buf))
            buf = (
                sents[max(0, len(sents) - 1 - overlap) : 0] if False else []
            )  # simple reset
            count = 0
    if buf:
        chunks.append(" ".join(buf))
    return chunks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean_dir", required=True)
    ap.add_argument("--jsonl_out", required=True)
    ap.add_argument("--category", default="civil")
    ap.add_argument(
        "--semantic", action="store_true", help="Use semantic chunker (GNN)"
    )
    ap.add_argument("--wandb", action="store_true", help="Enable W&B logging")
    args = ap.parse_args()

    # W&B init
    if args.wandb:
        import wandb

        wandb.init(
            project=os.getenv("WANDB_PROJECT", "mahoun"), name="chunker", reinit=True
        )
        wandb.config.update({"mode": "semantic" if args.semantic else "classic"})

    out = Path(args.jsonl_out)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Initialize semantic chunker if requested
    semantic_chunker = None
    if args.semantic:
        try:
            from mahoun.graph.gnn.semantic_chunker import SemanticChunker
            from mahoun.pipelines._config import load_gnn_config

            log.info("Initializing Semantic Chunker...")
            gnn_cfg = load_gnn_config()

            if gnn_cfg and gnn_cfg.semantic_chunker:
                cfg = gnn_cfg.semantic_chunker
                semantic_chunker = SemanticChunker(
                    embed_model=cfg.get("embed_model", "BAAI/bge-m3"),
                    ner_model=cfg.get(
                        "ner_model", "HooshvareLab/bert-base-parsbert-uncased"
                    ),
                    device=cfg.get("device", "cuda"),
                    batch_size=cfg.get("batch_size", 32),
                )
                log.info("Semantic Chunker initialized successfully")
            else:
                log.warning("GNN config not found, falling back to classic chunker")
                args.semantic = False
        except Exception as e:
            log.error(f"Failed to initialize Semantic Chunker: {e}")
            log.warning("Falling back to classic chunker")
            args.semantic = False

    total_chunks = 0
    total_files = 0
    total_coherence = 0.0
    total_entities = 0

    with open(out, "w", encoding="utf-8") as w:
        for fp in Path(args.clean_dir).rglob("*.txt"):
            text = fp.read_text(encoding="utf-8")
            total_files += 1

            if args.semantic and semantic_chunker:
                # Use semantic chunker
                gnn_cfg = load_gnn_config()
                cfg = gnn_cfg.semantic_chunker if gnn_cfg else {}

                chunk_objs = semantic_chunker.chunk_text(
                    text=text,
                    min_size=cfg.get("min_chunk_size", 300),
                    max_size=cfg.get("max_chunk_size", 800),
                    target_size=cfg.get("target_chunk_size", 600),
                    overlap=cfg.get("overlap_size", 80),
                    similarity_threshold=cfg.get("similarity_threshold", 0.7),
                    coherence_threshold=cfg.get("coherence_threshold", 0.7),
                    preserve_entities=cfg.get("preserve_entities", True),
                    doc_id=fp.stem,
                    metadata={"category": args.category, "source": str(fp)},
                )

                for chunk in chunk_objs:
                    rec = {
                        "id": chunk.id,
                        "source": str(fp),
                        "text": chunk.text,
                        "meta": {
                            "category": args.category,
                            "coherence_score": chunk.coherence_score,
                            "entity_count": chunk.entity_count,
                            "semantic_density": chunk.semantic_density,
                        },
                        "entities": chunk.entities,
                    }
                    w.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    total_chunks += 1
                    total_coherence += chunk.coherence_score
                    total_entities += chunk.entity_count
            else:
                # Use classic chunker
                chunks = chunk_text(text)
                for i, ch in enumerate(chunks):
                    rec = {
                        "id": f"{fp.stem}-{i}",
                        "source": str(fp),
                        "text": ch,
                        "meta": {"category": args.category},
                    }
                    w.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    total_chunks += 1

    log.info(f"Chunking done: {total_chunks} chunks from {total_files} files.")

    if args.wandb:
        metrics = {
            "total_files": total_files,
            "total_chunks": total_chunks,
            "avg_chunks_per_file": total_chunks / total_files if total_files > 0 else 0,
            "category": args.category,
            "status": "completed",
        }

        if args.semantic and total_chunks > 0:
            metrics.update(
                {
                    "avg_coherence": total_coherence / total_chunks,
                    "total_entities": total_entities,
                    "avg_entities_per_chunk": total_entities / total_chunks,
                }
            )

        wandb.log(metrics)
        wandb.finish()


if __name__ == "__main__":
    main()

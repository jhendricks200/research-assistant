"""Optional: re-embed every chunk with BAAI/bge-base-en-v1.5 into a separate collection,
so the bge_* variants in run_eval.py can be compared with the default embedder.

Resumable: skips ids already embedded. Needs requirements-eval.txt.
"""
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import chromadb  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

import config  # noqa: E402
from run_eval import BGE_COLLECTION, _device  # noqa: E402

client = chromadb.PersistentClient(path=config.CHROMA_PATH)
src = client.get_collection(config.COLLECTION_NAME)
dst = client.get_or_create_collection(BGE_COLLECTION, metadata={"hnsw:space": "cosine"})
model = SentenceTransformer("BAAI/bge-base-en-v1.5", device=_device())
model.max_seq_length = 512

total = src.count()
done = set(dst.get(include=[])["ids"]) if dst.count() else set()
print(f"source {total}, already embedded {len(done)}", flush=True)
t0, n, page = time.time(), 0, 1000
for off in range(0, total, page):
    got = src.get(limit=page, offset=off, include=["documents", "metadatas"])
    keep = [i for i, cid in enumerate(got["ids"]) if cid not in done]
    if not keep:
        continue
    docs = [got["documents"][i] for i in keep]
    dst.add(ids=[got["ids"][i] for i in keep], documents=docs,
            metadatas=[got["metadatas"][i] for i in keep],
            embeddings=model.encode(docs, batch_size=32, normalize_embeddings=True).tolist())
    n += len(keep)
    print(f"{min(off + page, total)}/{total} embedded {n} in {time.time() - t0:.0f}s", flush=True)
    if shutil.disk_usage(ROOT).free < 15e9:
        sys.exit("stopping: less than 15 GB free disk")
print(f"done: {dst.count()} chunks in {BGE_COLLECTION}", flush=True)

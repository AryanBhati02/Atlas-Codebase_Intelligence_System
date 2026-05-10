"""
build_vocab.py
--------------
Standalone script that builds the token vocabulary from CodeSearchNet Python
training split and saves it to training/data/vocab.json.

Run this ONCE before starting train_gatv2.py.

Usage:
    python training/build_vocab.py
    python training/build_vocab.py --data_dir training/data/codesearchnet_python \\
                                    --vocab_path training/data/vocab.json \\
                                    --max_vocab 10000
    python training/build_vocab.py --download      # also downloads the dataset
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Iterable, Mapping, cast


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("build_vocab")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build token vocabulary from CodeSearchNet Python train split."
    )
    parser.add_argument(
        "--data_dir",
        default="training/data/codesearchnet_python",
        help="Directory where the HuggingFace dataset is stored (or will be downloaded).",
    )
    parser.add_argument(
        "--vocab_path",
        default="training/data/vocab.json",
        help="Output path for vocab.json.",
    )
    parser.add_argument(
        "--max_vocab",
        type=int,
        default=10_000,
        help="Maximum vocabulary size (including <PAD> and <UNK>).",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download CodeSearchNet Python dataset if not already present.",
    )
    return parser.parse_args()


def download_and_save(data_dir: str) -> None:
    """Download CodeSearchNet Python train split and save to disk."""
    try:
        from datasets import load_dataset  
    except ImportError:
        logger.error(
            "The `datasets` library is not installed. "
            "Run: pip install datasets"
        )
        sys.exit(1)

    logger.info("Downloading CodeSearchNet Python dataset …")
    ds = load_dataset(
        "code_search_net",
        "python",
    )
    os.makedirs(data_dir, exist_ok=True)
    ds["train"].save_to_disk(data_dir)
    logger.info(f"Dataset saved to {data_dir}")


def main() -> None:
    args = parse_args()

    
    backend_root = Path(__file__).resolve().parents[1]
    data_dir   = str(backend_root / args.data_dir)
    vocab_path = str(backend_root / args.vocab_path)

    
    if args.download or not Path(data_dir).exists():
        download_and_save(data_dir)

    
    try:
        from datasets import load_from_disk  
    except ImportError:
        logger.error(
            "The `datasets` library is not installed. "
            "Run: pip install datasets"
        )
        sys.exit(1)

    logger.info(f"Loading dataset from {data_dir} …")
    try:
        dataset = load_from_disk(data_dir)
    except Exception as exc:
        logger.error(
            f"Could not load dataset from {data_dir}. "
            f"Use --download to fetch it first. Error: {exc}"
        )
        sys.exit(1)

    logger.info(f"Dataset loaded: {len(dataset)} examples.")

    
    code_samples = []
    for example in cast(Iterable[Mapping[str, object]], dataset):
        raw_code = example.get("whole_func_string", "")
        code = raw_code if isinstance(raw_code, str) else ""
        if code.strip():
            code_samples.append(code)

    logger.info(f"Collected {len(code_samples)} non-empty code samples.")

    
    from core.model.dataset import Vocabulary  

    vocab = Vocabulary.build_from_codes(
        code_samples,
        max_vocab_size=args.max_vocab,
    )

    
    vocab.save(vocab_path)
    logger.info(
        f"Vocabulary saved to {vocab_path}: {vocab.size} tokens "
        f"(max requested: {args.max_vocab})."
    )
    import sys as _sys
    
    msg = f"\nVocabulary: {vocab.size} tokens  ->  {vocab_path}\n"
    _sys.stdout.buffer.write(msg.encode("utf-8"))
    _sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()

"""
train_gatv2.py
--------------
GATv2 contrastive training with:
  - Mixed precision (torch.cuda.amp / torch.amp — version-aware)
  - Gradient checkpointing on the GATv2 layers (saves VRAM on RTX 3050 6 GB)
  - InfoNCE symmetric in-batch negative loss
  - AdamW + CosineAnnealing LR schedule
  - Automatic CUDA OOM detection with helpful guidance
  - Checkpoint saving every 20 epochs + best model

Default batch_size = 16  (NOT 64 — InfoNCE builds [B×B] matrix;
at 64 this plus model weights will OOM on 6 GB VRAM).

Usage:
    # Minimal (uses all defaults)
    python training/train_gatv2.py

    # Custom
    python training/train_gatv2.py \\
        --epochs 100 --batch_size 16 --lr 1e-4 \\
        --data_dir training/data/codesearchnet_python \\
        --vocab_path training/data/vocab.json \\
        --checkpoint_dir training/checkpoints

    # Resume from checkpoint
    python training/train_gatv2.py --resume training/checkpoints/epoch_40.pt

    # Ablation — static edges only (no fusion weights)
    python training/train_gatv2.py --static_only
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("train_gatv2")

def _get_amp_tools(device_type: str = "cuda"):
    """
    Return (autocast_cls, GradScaler) using the correct API for the installed
    PyTorch version.

    PyTorch < 2.0  : torch.cuda.amp.autocast, torch.cuda.amp.GradScaler
    PyTorch >= 2.0 : torch.amp.autocast(device_type=...), torch.amp.GradScaler(device)
    """
    major, minor, *_ = (int(x) for x in torch.__version__.split(".")[:2])

    if major >= 2:
        from torch.amp import GradScaler  

        autocast = torch.amp.autocast  
        scaler   = GradScaler(device_type)
        logger.info(f"Using torch.amp (PyTorch {torch.__version__})")
    else:
        from torch.cuda.amp import GradScaler, autocast as _autocast  

        
        class _CompatAutocast:
            def __init__(self):
                pass
            def __call__(self, device_type="cuda", **kwargs):
                return _autocast(**kwargs)

        autocast = _CompatAutocast()
        scaler   = GradScaler()
        logger.info(f"Using torch.cuda.amp (PyTorch {torch.__version__})")

    return autocast, scaler

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train GATv2 function encoder with InfoNCE contrastive loss."
    )
    parser.add_argument("--epochs",           type=int,   default=100)
    parser.add_argument(
        "--batch_size", type=int, default=16,
        help="Batch size. Default 16 for RTX 3050 6 GB. Increase carefully.",
    )
    parser.add_argument("--lr",               type=float, default=1e-4)
    parser.add_argument("--temperature",      type=float, default=0.07)
    parser.add_argument(
        "--checkpoint_dir", default="training/checkpoints",
        help="Directory to save checkpoints.",
    )
    parser.add_argument(
        "--data_dir", default="training/data/codesearchnet_python",
        help="HuggingFace dataset directory (output of save_to_disk).",
    )
    parser.add_argument(
        "--vocab_path", default="training/data/vocab.json",
        help="Path to vocab.json produced by build_vocab.py.",
    )
    parser.add_argument(
        "--static_only", action="store_true",
        help="Ablation flag: ignore fusion weights, use 1.0 for all edges.",
    )
    parser.add_argument(
        "--resume",
        default=None,
        help="Path to a checkpoint .pt file to resume training from.",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--max_pairs",
        type=int,
        default=200_000,
        help="Cap on training pairs (default 200 000). Set to e.g. 2000 for a fast smoke-test.",
    )
    return parser.parse_args()

def main() -> None:
    args = parse_args()

    
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    
    backend_root   = Path(__file__).resolve().parents[1]
    data_dir       = str(backend_root / args.data_dir)
    vocab_path     = str(backend_root / args.vocab_path)
    checkpoint_dir = str(backend_root / args.checkpoint_dir)
    os.makedirs(checkpoint_dir, exist_ok=True)

    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"Training on {device}")
    if device.type == "cuda":
        logger.info(
            f"GPU: {torch.cuda.get_device_name(0)} | "
            f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB"
        )

    
    autocast, scaler = _get_amp_tools(device.type)

    
    from core.model.dataset import FunctionPairDataset, collate_pairs  

    logger.info("Loading dataset …")
    try:
        dataset = FunctionPairDataset(
            data_dir=data_dir,
            vocab_path=vocab_path,
            max_seq_len=64,
            seed=args.seed,
            max_pairs=args.max_pairs,
        )
    except RuntimeError as exc:
        logger.error(str(exc))
        sys.exit(1)

    dataloader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=True,
        collate_fn=collate_pairs,
        num_workers=0,            
        pin_memory=(device.type == "cuda"),
        drop_last=True,           
    )
    logger.info(
        f"DataLoader: {len(dataset)} pairs → "
        f"{len(dataloader)} batches/epoch (batch_size={args.batch_size})"
    )
    if args.static_only:
        logger.info(
            "Static-only ablation enabled: edge_attr will be forced to 1.0. "
            "With the current CodeSearchNet token graphs this matches the default "
            "training data, because fusion weights are only available for real repo graphs."
        )

    from core.model.dataset import Vocabulary  
    from core.model.function_encoder import FunctionEncoder, infonce_loss  

    vocab = Vocabulary.from_file(vocab_path)
    model = FunctionEncoder(
        vocab_size=vocab.size,
        embed_dim=128,
        hidden_dim=64,
        out_dim=128,
        heads=4,
        dropout=0.2,
    ).to(device)

    logger.info(
        f"FunctionEncoder: "
        f"{sum(p.numel() for p in model.parameters()):,} parameters"
    )

    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=args.lr,
        weight_decay=1e-5,
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer,
        T_max=args.epochs,
        eta_min=1e-6,
    )

    start_epoch = 1
    best_loss   = float("inf")
    epoch_losses: list[dict] = []

    if args.resume:
        resume_path = str(backend_root / args.resume) if not os.path.isabs(args.resume) else args.resume
        if os.path.isfile(resume_path):
            logger.info(f"Resuming from checkpoint: {resume_path}")
            ckpt = torch.load(resume_path, map_location=device)
            model.load_state_dict(ckpt["model_state_dict"])
            optimizer.load_state_dict(ckpt["optimizer_state_dict"])
            start_epoch = ckpt.get("epoch", 0) + 1
            best_loss   = ckpt.get("loss", float("inf"))
            logger.info(f"Resumed at epoch {start_epoch}, best loss so far: {best_loss:.4f}")
        else:
            logger.warning(f"Checkpoint not found: {resume_path}; starting fresh.")

    
    train_start = time.time()

    for epoch in range(start_epoch, args.epochs + 1):
        model.train()
        epoch_loss = 0.0
        num_batches = 0

        for batch_idx, (batch_a, batch_b) in enumerate(dataloader):
            
            batch_a = batch_a.to(device)
            batch_b = batch_b.to(device)

            
            if args.static_only:
                batch_a.edge_attr = torch.ones_like(batch_a.edge_attr)
                batch_b.edge_attr = torch.ones_like(batch_b.edge_attr)

            optimizer.zero_grad(set_to_none=True)

            try:
                with autocast(device_type=device.type):
                    z_a = model(
                        batch_a.x,
                        batch_a.edge_index,
                        batch_a.edge_attr,
                        batch_a.batch,
                    )
                    z_b = model(
                        batch_b.x,
                        batch_b.edge_index,
                        batch_b.edge_attr,
                        batch_b.batch,
                    )
                    loss = infonce_loss(z_a, z_b, temperature=args.temperature)

                scaler.scale(loss).backward()
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                scaler.step(optimizer)
                scaler.update()

            except torch.cuda.OutOfMemoryError:
                torch.cuda.empty_cache()
                logger.error(
                    "\n"
                    "====================================================\n"
                    "  CUDA OUT OF MEMORY!\n"
                    "  Current batch_size = %d\n"
                    "  Suggestions:\n"
                    "    1. Reduce --batch_size to %d or lower\n"
                    "    2. Reduce --max_seq_len (edit FunctionPairDataset)\n"
                    "    3. Set model.use_checkpointing = True (already on)\n"
                    "====================================================\n",
                    args.batch_size,
                    max(4, args.batch_size // 2),
                )
                sys.exit(1)

            epoch_loss  += loss.item()
            num_batches += 1

        scheduler.step()
        avg_loss = epoch_loss / max(num_batches, 1)
        epoch_losses.append({"epoch": epoch, "loss": avg_loss})

        
        if device.type == "cuda":
            vram_gb = torch.cuda.memory_allocated() / 1e9
            vram_str = f" | VRAM: {vram_gb:.2f} GB"
        else:
            vram_str = ""

        logger.info(
            f"Epoch {epoch:4d}/{args.epochs} | "
            f"Loss: {avg_loss:.4f} | "
            f"LR: {scheduler.get_last_lr()[0]:.6f}"
            f"{vram_str}"
        )

        
        if epoch % 20 == 0:
            ckpt_path = os.path.join(checkpoint_dir, f"epoch_{epoch:04d}.pt")
            torch.save(
                {
                    "epoch": epoch,
                    "model_state_dict": model.state_dict(),
                    "optimizer_state_dict": optimizer.state_dict(),
                    "loss": avg_loss,
                    "vocab_size": vocab.size,
                },
                ckpt_path,
            )
            logger.info(f"Checkpoint saved: {ckpt_path}")

        
        if avg_loss < best_loss:
            best_loss = avg_loss
            best_path = os.path.join(checkpoint_dir, "best_model.pt")
            torch.save(
                {
                    "epoch": epoch,
                    "model_state_dict": model.state_dict(),
                    "optimizer_state_dict": optimizer.state_dict(),
                    "loss": best_loss,
                    "vocab_size": vocab.size,
                },
                best_path,
            )
    
    total_time = time.time() - train_start
    if device.type == "cuda":
        final_vram = torch.cuda.max_memory_allocated() / 1e9
    else:
        final_vram = 0.0

    logger.info(
        f"\n{'='*60}\n"
        f"Training complete!\n"
        f"  Total time  : {total_time / 60:.1f} min\n"
        f"  Best loss   : {best_loss:.4f}\n"
        f"  Peak VRAM   : {final_vram:.2f} GB\n"
        f"  Best model  : {os.path.join(checkpoint_dir, 'best_model.pt')}\n"
        f"{'='*60}"
    )

    
    log_path = os.path.join(checkpoint_dir, "training_log.json")
    with open(log_path, "w") as f:
        json.dump(
            {
                "config": vars(args),
                "best_loss": best_loss,
                "total_time_seconds": total_time,
                "peak_vram_gb": final_vram,
                "epoch_losses": epoch_losses,
            },
            f,
            indent=2,
        )
    logger.info(f"Training log saved to {log_path}")


if __name__ == "__main__":
    main()

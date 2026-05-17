"""
function_encoder.py
-------------------
GATv2-based function encoder (Brody et al. 2022).

GATv2Conv uses *dynamic attention* — attention weights depend on BOTH the
query and key nodes — unlike standard GATConv whose attention is static.
This matters for code: the same callee behaves differently depending on
its caller's context.

Architecture:
  token_embed  → gat1 (concat, 4 heads) → gat2 (single head) → global_mean_pool
               → proj → LayerNorm → L2 normalize

Mixed precision:  works with torch.cuda.amp.autocast out-of-the-box.
Grad checkpointing: gat1+gat2 wrapped with checkpoint() when training to
                    reduce VRAM peak usage on RTX 3050 6 GB.
"""

from __future__ import annotations

from typing import cast

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import GATv2Conv, global_mean_pool
from torch.utils.checkpoint import checkpoint


class FunctionEncoder(nn.Module):
    """
    Encode a function (represented as a small token graph) into a fixed-size
    L2-normalised embedding.

    Parameters
    ----------
    vocab_size  : number of unique tokens in the vocabulary (including padding at 0)
    embed_dim   : token embedding dimension  (default 128)
    hidden_dim  : GATv2 layer-1 per-head dimension (default 64)
    out_dim     : final embedding dimension  (default 128)
    heads       : number of attention heads in gat1 (default 4)
    dropout     : dropout probability for gat1 (default 0.2)
    """

    def __init__(
        self,
        vocab_size: int = 10_000,
        embed_dim: int = 128,
        hidden_dim: int = 64,
        out_dim: int = 128,
        heads: int = 4,
        dropout: float = 0.2,
    ) -> None:
        super().__init__()

        
        self.token_embed = nn.Embedding(vocab_size, embed_dim, padding_idx=0)

        
        self.gat1 = GATv2Conv(
            in_channels=embed_dim,
            out_channels=hidden_dim,
            heads=heads,
            dropout=dropout,
            concat=True,
            edge_dim=1,          
        )

        
        self.gat2 = GATv2Conv(
            in_channels=hidden_dim * heads,   
            out_channels=out_dim,
            heads=1,
            dropout=dropout / 2,
            concat=False,
            edge_dim=1,
        )

        
        self.proj = nn.Linear(out_dim, out_dim)
        self.norm = nn.LayerNorm(out_dim)

        
        self.use_checkpointing: bool = True

    def forward(
        self,
        x: torch.Tensor,           
        edge_index: torch.Tensor,  
        edge_attr: torch.Tensor,   
        batch: torch.Tensor,       
    ) -> torch.Tensor:
        """
        Returns L2-normalised embeddings of shape [B, out_dim].

        Each function in the batch is a token graph whose nodes are the
        individual token positions; edges connect nearby tokens (sliding
        window) with optional fusion-weight annotations.
        """
        
        h = self.token_embed(x)    

        if self.use_checkpointing and self.training:
            
            h = cast(
                torch.Tensor,
                checkpoint(
                    self._gat_forward,
                    h, edge_index, edge_attr,
                    use_reentrant=False,
                ),
            )
        else:
            h = self._gat_forward(h, edge_index, edge_attr)

        
        h = global_mean_pool(h, batch)

        
        h = self.proj(h)
        h = self.norm(h)
        return F.normalize(h, dim=-1)   

    def _gat_forward(
        self,
        h: torch.Tensor,
        edge_index: torch.Tensor,
        edge_attr: torch.Tensor,
    ) -> torch.Tensor:
        """Two-layer GATv2Conv stack."""
        h = F.elu(self.gat1(h, edge_index, edge_attr=edge_attr))   
        h = F.dropout(h, p=0.1, training=self.training)
        h = self.gat2(h, edge_index, edge_attr=edge_attr)           
        return h

def infonce_loss(
    z_a: torch.Tensor,
    z_b: torch.Tensor,
    temperature: float = 0.07,
) -> torch.Tensor:
    """
    Symmetric InfoNCE contrastive loss.

    Given a batch of B positive pairs (z_a[i], z_b[i]), the loss pulls
    matching pairs together and pushes all other in-batch pairs apart.

    Parameters
    ----------
    z_a         : [B, D]  L2-normalised embeddings (view A)
    z_b         : [B, D]  L2-normalised embeddings (view B)
    temperature : logit scaling factor (default 0.07)

    Returns
    -------
    Scalar loss tensor.
    """
    
    logits = torch.mm(z_a, z_b.T) / temperature

    
    labels = torch.arange(len(z_a), device=z_a.device)

    
    loss = (
        F.cross_entropy(logits,   labels)
        + F.cross_entropy(logits.T, labels)
    ) / 2.0
    return loss

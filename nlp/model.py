from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from torch import nn
from torch.nn import functional as F

try:
    from torchvision.models import MobileNet_V3_Small_Weights, mobilenet_v3_small
except Exception:  # pragma: no cover - older torchvision fallback
    from torchvision.models import mobilenet_v3_small  # type: ignore

    MobileNet_V3_Small_Weights = None  # type: ignore

from .labels import NUM_CLASSES, WASTE_TOKENS, default_caption_for
from .tokenizer import CaptionTokenizer, build_tokenizer


@dataclass(slots=True)
class CaptionModelConfig:
    vocab_size: int
    num_classes: int = NUM_CLASSES
    d_model: int = 192
    num_heads: int = 6
    num_layers: int = 3
    ff_dim: int = 384
    dropout: float = 0.1
    max_text_len: int = 48
    image_grid_size: int = 4
    pretrained: bool = True


def _build_backbone(pretrained: bool) -> nn.Module:
    if pretrained and MobileNet_V3_Small_Weights is not None:
        try:
            return mobilenet_v3_small(weights=MobileNet_V3_Small_Weights.DEFAULT).features
        except Exception:
            pass

    try:
        return mobilenet_v3_small(weights=None).features
    except TypeError:  # pragma: no cover - older torchvision API
        return mobilenet_v3_small(pretrained=False).features


class FlashMultiHeadAttention(nn.Module):
    def __init__(self, d_model: int, num_heads: int, dropout: float = 0.1):
        super().__init__()
        if d_model % num_heads != 0:
            raise ValueError("d_model must be divisible by num_heads")
        self.d_model = d_model
        self.num_heads = num_heads
        self.head_dim = d_model // num_heads
        self.dropout = dropout

        self.q_proj = nn.Linear(d_model, d_model)
        self.k_proj = nn.Linear(d_model, d_model)
        self.v_proj = nn.Linear(d_model, d_model)
        self.out_proj = nn.Linear(d_model, d_model)

    def forward(
        self,
        query: torch.Tensor,
        key: torch.Tensor | None = None,
        value: torch.Tensor | None = None,
        *,
        is_causal: bool = False,
    ) -> torch.Tensor:
        if key is None:
            key = query
        if value is None:
            value = key

        batch_size, query_len, _ = query.shape
        key_len = key.shape[1]

        q = self.q_proj(query).view(batch_size, query_len, self.num_heads, self.head_dim).transpose(1, 2)
        k = self.k_proj(key).view(batch_size, key_len, self.num_heads, self.head_dim).transpose(1, 2)
        v = self.v_proj(value).view(batch_size, key_len, self.num_heads, self.head_dim).transpose(1, 2)

        attn = F.scaled_dot_product_attention(
            q,
            k,
            v,
            dropout_p=self.dropout if self.training else 0.0,
            is_causal=is_causal,
        )
        attn = attn.transpose(1, 2).contiguous().view(batch_size, query_len, self.d_model)
        return self.out_proj(attn)


class FlashDecoderLayer(nn.Module):
    def __init__(self, d_model: int, num_heads: int, ff_dim: int, dropout: float):
        super().__init__()
        self.self_attn = FlashMultiHeadAttention(d_model, num_heads, dropout=dropout)
        self.cross_attn = FlashMultiHeadAttention(d_model, num_heads, dropout=dropout)
        self.norm1 = nn.LayerNorm(d_model)
        self.norm2 = nn.LayerNorm(d_model)
        self.norm3 = nn.LayerNorm(d_model)
        self.ff = nn.Sequential(
            nn.Linear(d_model, ff_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(ff_dim, d_model),
        )
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor, memory: torch.Tensor) -> torch.Tensor:
        x = x + self.dropout(self.self_attn(self.norm1(x), is_causal=True))
        x = x + self.dropout(self.cross_attn(self.norm2(x), memory))
        x = x + self.dropout(self.ff(self.norm3(x)))
        return x


class WasteCaptionTransformer(nn.Module):
    def __init__(self, config: CaptionModelConfig):
        super().__init__()
        self.config = config
        self.vocab_size = config.vocab_size
        self.num_classes = config.num_classes
        self.d_model = config.d_model
        self.num_heads = config.num_heads
        self.num_layers = config.num_layers
        self.ff_dim = config.ff_dim
        self.dropout = config.dropout
        self.max_text_len = config.max_text_len
        self.image_grid_size = config.image_grid_size

        self.backbone = _build_backbone(config.pretrained)
        self.feature_dim = 576
        self.global_pool = nn.AdaptiveAvgPool2d(1)
        self.image_pool = nn.AdaptiveAvgPool2d((self.image_grid_size, self.image_grid_size))

        self.classifier = nn.Linear(self.feature_dim, self.num_classes)
        self.image_projector = nn.Linear(self.feature_dim, self.d_model)
        self.image_context = nn.Linear(self.feature_dim, self.d_model)
        self.image_positional = nn.Parameter(
            torch.zeros(1, self.image_grid_size * self.image_grid_size + 1, self.d_model)
        )

        self.token_embedding = nn.Embedding(self.vocab_size, self.d_model, padding_idx=0)
        self.text_positional = nn.Parameter(torch.zeros(1, self.max_text_len, self.d_model))
        self.input_dropout = nn.Dropout(self.dropout)
        self.decoder_layers = nn.ModuleList(
            [FlashDecoderLayer(self.d_model, self.num_heads, self.ff_dim, self.dropout) for _ in range(self.num_layers)]
        )
        self.final_norm = nn.LayerNorm(self.d_model)
        self.lm_head = nn.Linear(self.d_model, self.vocab_size)
        self.lm_head.weight = self.token_embedding.weight

        self._reset_parameters()

    def _reset_parameters(self) -> None:
        nn.init.trunc_normal_(self.image_positional, std=0.02)
        nn.init.trunc_normal_(self.text_positional, std=0.02)
        nn.init.trunc_normal_(self.token_embedding.weight, std=0.02)
        nn.init.trunc_normal_(self.classifier.weight, std=0.02)
        nn.init.zeros_(self.classifier.bias)
        nn.init.trunc_normal_(self.image_projector.weight, std=0.02)
        nn.init.zeros_(self.image_projector.bias)
        nn.init.trunc_normal_(self.image_context.weight, std=0.02)
        nn.init.zeros_(self.image_context.bias)
        nn.init.zeros_(self.lm_head.bias)

    def get_config(self) -> dict[str, Any]:
        return {
            "vocab_size": self.vocab_size,
            "num_classes": self.num_classes,
            "d_model": self.d_model,
            "num_heads": self.num_heads,
            "num_layers": self.num_layers,
            "ff_dim": self.ff_dim,
            "dropout": self.dropout,
            "max_text_len": self.max_text_len,
            "image_grid_size": self.image_grid_size,
            "pretrained": False,
        }

    def encode_images(self, images: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        feature_map = self.backbone(images)
        pooled = self.global_pool(feature_map).flatten(1)
        class_logits = self.classifier(pooled)

        spatial = self.image_pool(feature_map).flatten(2).transpose(1, 2)
        spatial = self.image_projector(spatial)
        context = self.image_context(pooled).unsqueeze(1)
        memory = torch.cat([context, spatial], dim=1)
        memory = memory + self.image_positional[:, : memory.size(1)]
        memory = self.input_dropout(memory)
        return class_logits, memory

    def decode(self, captions: torch.Tensor, memory: torch.Tensor) -> torch.Tensor:
        if captions.dim() != 2:
            raise ValueError("captions must be a 2D tensor")
        if captions.size(1) > self.max_text_len:
            captions = captions[:, : self.max_text_len]

        positions = self.text_positional[:, : captions.size(1)]
        hidden = self.token_embedding(captions) + positions
        hidden = self.input_dropout(hidden)
        for layer in self.decoder_layers:
            hidden = layer(hidden, memory)
        hidden = self.final_norm(hidden)
        return self.lm_head(hidden)

    def forward(self, images: torch.Tensor, captions: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        class_logits, memory = self.encode_images(images)
        caption_logits = self.decode(captions, memory)
        return class_logits, caption_logits

    def generate(
        self,
        images: torch.Tensor,
        tokenizer: CaptionTokenizer,
        max_len: int = 32,
        temperature: float = 0.0,
    ) -> tuple[str, list[str]]:
        was_training = self.training
        self.eval()
        try:
            if images.dim() == 3:
                images = images.unsqueeze(0)
            max_len = max(2, min(max_len, self.max_text_len))
            device = images.device

            with torch.inference_mode():
                class_logits, memory = self.encode_images(images)
                predicted_class = int(class_logits.argmax(dim=-1)[0].item())
                token_ids = torch.tensor([[tokenizer.bos_id]], device=device, dtype=torch.long)

                for _ in range(max_len - 1):
                    caption_logits = self.decode(token_ids, memory)
                    next_logits = caption_logits[:, -1, :]
                    if temperature and temperature > 0:
                        probs = torch.softmax(next_logits / temperature, dim=-1)
                        next_id = torch.multinomial(probs, num_samples=1)
                    else:
                        next_id = next_logits.argmax(dim=-1, keepdim=True)
                    token_ids = torch.cat([token_ids, next_id], dim=1)
                    if int(next_id.item()) == tokenizer.eos_id:
                        break

                decoded_tokens = tokenizer.decode_ids(token_ids[0].tolist())
                decoded_text = tokenizer.decode(token_ids[0].tolist())
                if len(decoded_tokens) <= 3 or "waste" not in decoded_text.lower():
                    fallback = default_caption_for(WASTE_TOKENS[predicted_class])
                    fallback_ids = tokenizer.encode(fallback)
                    decoded_tokens = tokenizer.decode_ids(fallback_ids)
                    decoded_text = tokenizer.decode(fallback_ids)
                return decoded_text, decoded_tokens
        finally:
            self.train(was_training)


def build_model(
    vocab_size: int,
    num_classes: int = NUM_CLASSES,
    d_model: int = 192,
    num_heads: int = 6,
    num_layers: int = 3,
    ff_dim: int = 384,
    dropout: float = 0.1,
    max_text_len: int = 48,
    image_grid_size: int = 4,
    pretrained: bool = True,
) -> WasteCaptionTransformer:
    return WasteCaptionTransformer(
        CaptionModelConfig(
            vocab_size=vocab_size,
            num_classes=num_classes,
            d_model=d_model,
            num_heads=num_heads,
            num_layers=num_layers,
            ff_dim=ff_dim,
            dropout=dropout,
            max_text_len=max_text_len,
            image_grid_size=image_grid_size,
            pretrained=pretrained,
        )
    )


def _normalize_state_dict(state_dict: dict[str, torch.Tensor]) -> dict[str, torch.Tensor]:
    if not state_dict:
        return state_dict
    if all(key.startswith("module.") for key in state_dict):
        return {key.removeprefix("module."): value for key, value in state_dict.items()}
    return state_dict


def load_caption_model(
    checkpoint_path: str | Path,
    map_location: str | torch.device = "cpu",
) -> tuple[WasteCaptionTransformer, CaptionTokenizer, dict[str, Any]]:
    checkpoint = torch.load(checkpoint_path, map_location=map_location)
    if not isinstance(checkpoint, dict):
        raise TypeError("Checkpoint must be a dictionary")

    tokenizer_data = checkpoint.get("tokenizer") or {}
    tokenizer = CaptionTokenizer(list(tokenizer_data.get("vocab", build_tokenizer().vocab)))

    config = dict(checkpoint.get("config", {}))
    config.setdefault("vocab_size", tokenizer.vocab_size)
    config.setdefault("num_classes", NUM_CLASSES)
    model = build_model(**config)

    state_dict = checkpoint.get("model_state", checkpoint.get("state_dict", checkpoint))
    if not isinstance(state_dict, dict):
        raise TypeError("Checkpoint does not contain a model state dict")
    model.load_state_dict(_normalize_state_dict(state_dict))
    model.eval()
    return model, tokenizer, checkpoint


WasteStudent = WasteCaptionTransformer

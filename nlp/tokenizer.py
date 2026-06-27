from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import torch

TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?|[.!?,;:]")

SPECIAL_TOKENS = ["<pad>", "<bos>", "<eos>", "<unk>"]


def tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.lower())


def detokenize(tokens: Sequence[str]) -> str:
    text = " ".join(tokens)
    text = re.sub(r"\s+([.!?,;:])", r"\1", text)
    text = re.sub(r"\s+'", "'", text)
    text = text.strip()
    if text:
        text = text[0].upper() + text[1:]
    return text


@dataclass
class CaptionTokenizer:
    vocab: list[str]

    def __post_init__(self) -> None:
        self.token_to_id = {token: idx for idx, token in enumerate(self.vocab)}
        self.id_to_token = list(self.vocab)
        self.pad_id = self.token_to_id["<pad>"]
        self.bos_id = self.token_to_id["<bos>"]
        self.eos_id = self.token_to_id["<eos>"]
        self.unk_id = self.token_to_id["<unk>"]

    @property
    def vocab_size(self) -> int:
        return len(self.vocab)

    @classmethod
    def build(cls, texts: Iterable[str]) -> "CaptionTokenizer":
        seen = set(SPECIAL_TOKENS)
        vocab = list(SPECIAL_TOKENS)
        for text in texts:
            for token in tokenize(text):
                if token not in seen:
                    seen.add(token)
                    vocab.append(token)
        return cls(vocab)

    @classmethod
    def from_file(cls, path: str | Path) -> "CaptionTokenizer":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(list(data["vocab"]))

    def to_dict(self) -> dict[str, list[str]]:
        return {"vocab": self.vocab}

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    def encode(self, text: str, add_special_tokens: bool = True) -> list[int]:
        ids = [self.token_to_id.get(token, self.unk_id) for token in tokenize(text)]
        if add_special_tokens:
            return [self.bos_id, *ids, self.eos_id]
        return ids

    def decode_ids(self, ids: Sequence[int], skip_special_tokens: bool = True) -> list[str]:
        tokens: list[str] = []
        for idx in ids:
            token = self.id_to_token[int(idx)]
            if skip_special_tokens and token in SPECIAL_TOKENS:
                continue
            if token == "<eos>":
                break
            tokens.append(token)
        return tokens

    def decode(self, ids: Sequence[int], skip_special_tokens: bool = True) -> str:
        return detokenize(self.decode_ids(ids, skip_special_tokens=skip_special_tokens))

    def pad_batch(self, sequences: Sequence[Sequence[int]], pad_to: int | None = None) -> torch.Tensor:
        if not sequences:
            return torch.empty(0, dtype=torch.long)
        max_len = pad_to or max(len(seq) for seq in sequences)
        batch = torch.full((len(sequences), max_len), self.pad_id, dtype=torch.long)
        for row, seq in enumerate(sequences):
            row_ids = torch.tensor(list(seq)[:max_len], dtype=torch.long)
            batch[row, : row_ids.numel()] = row_ids
        return batch


def build_tokenizer() -> CaptionTokenizer:
    from .labels import build_caption_catalog

    return CaptionTokenizer.build(build_caption_catalog())


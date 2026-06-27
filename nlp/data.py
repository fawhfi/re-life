from __future__ import annotations

import random
from functools import partial
from pathlib import Path
from typing import Iterable

from PIL import Image
import torch
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from torchvision import transforms

from .labels import CAPTION_TEMPLATES, CLASS_TO_IDX, NUM_CLASSES, WASTE_TOKENS
from .tokenizer import CaptionTokenizer, build_tokenizer as _build_tokenizer

IMG_SIZE = 224
MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")


def build_tokenizer() -> CaptionTokenizer:
    return _build_tokenizer()


def _build_transform(split: str) -> transforms.Compose:
    if split == "train":
        return transforms.Compose(
            [
                transforms.RandomResizedCrop(IMG_SIZE, scale=(0.75, 1.0)),
                transforms.RandomHorizontalFlip(p=0.5),
                transforms.ToTensor(),
                transforms.Normalize(MEAN, STD),
            ]
        )

    return transforms.Compose(
        [
            transforms.Resize((IMG_SIZE, IMG_SIZE)),
            transforms.ToTensor(),
            transforms.Normalize(MEAN, STD),
        ]
    )


def _iter_image_paths(folder: Path) -> Iterable[Path]:
    for extension in IMAGE_EXTENSIONS:
        yield from sorted(folder.glob(f"*{extension}"))


class WasteCaptionDataset(Dataset):
    def __init__(
        self,
        data_root: str | Path,
        split: str,
        tokenizer: CaptionTokenizer,
        max_caption_len: int = 32,
        seed: int = 7,
    ):
        self.root = Path(data_root) / split
        self.split = split
        self.class_to_idx = dict(CLASS_TO_IDX)
        self.transform = _build_transform(split)
        self.tokenizer = tokenizer
        self.max_caption_len = max_caption_len
        self.rng = random.Random(seed)
        self.samples: list[tuple[Path, int]] = []

        for class_name in WASTE_TOKENS:
            class_dir = self.root / class_name
            if not class_dir.exists():
                continue
            for path in _iter_image_paths(class_dir):
                self.samples.append((path, CLASS_TO_IDX[class_name]))

        if not self.samples:
            raise RuntimeError(f"No images found under {self.root}")

    def __len__(self) -> int:
        return len(self.samples)

    def _caption_for(self, class_idx: int, index: int) -> str:
        waste_type = WASTE_TOKENS[class_idx]
        templates = CAPTION_TEMPLATES[waste_type]
        if self.split == "train":
            return templates[(index + self.rng.randint(0, len(templates) - 1)) % len(templates)]
        return templates[0]

    def __getitem__(self, index: int):
        path, target = self.samples[index]
        with Image.open(path) as image:
            image_tensor = self.transform(image.convert("RGB"))
        caption = self._caption_for(target, index)
        caption_ids = self.tokenizer.encode(caption)
        if len(caption_ids) > self.max_caption_len:
            caption_ids = caption_ids[: self.max_caption_len - 1] + [self.tokenizer.eos_id]
        return image_tensor, target, caption_ids

    def class_weights(self) -> torch.Tensor:
        counts = torch.zeros(NUM_CLASSES, dtype=torch.float32)
        for _, label in self.samples:
            counts[label] += 1
        weights = counts.sum() / counts.clamp(min=1.0)
        return weights / weights.mean()

    def sample_weights(self) -> torch.Tensor:
        weights = self.class_weights()
        sample_weights = torch.tensor([weights[label].item() for _, label in self.samples], dtype=torch.float32)
        return sample_weights


def collate_caption_batch(batch, pad_id: int):
    images, labels, captions = zip(*batch)
    images = torch.stack(images)
    labels = torch.tensor(labels, dtype=torch.long)
    max_len = max(len(caption) for caption in captions)
    padded = torch.full((len(captions), max_len), pad_id, dtype=torch.long)
    for row, caption in enumerate(captions):
        values = torch.tensor(caption, dtype=torch.long)
        padded[row, : values.numel()] = values
    return images, labels, padded


def build_caption_datasets(
    data_root: str | Path,
    tokenizer: CaptionTokenizer | None = None,
    max_caption_len: int = 32,
):
    tokenizer = tokenizer or build_tokenizer()
    root = Path(data_root)
    return (
        WasteCaptionDataset(root, "train", tokenizer, max_caption_len=max_caption_len),
        WasteCaptionDataset(root, "val", tokenizer, max_caption_len=max_caption_len),
        WasteCaptionDataset(root, "test", tokenizer, max_caption_len=max_caption_len),
    )


def build_caption_dataloaders(
    data_root: str | Path,
    tokenizer: CaptionTokenizer | None = None,
    batch_size: int = 32,
    num_workers: int = 0,
    max_caption_len: int = 32,
):
    tokenizer = tokenizer or build_tokenizer()
    train_dataset, val_dataset, test_dataset = build_caption_datasets(
        data_root,
        tokenizer=tokenizer,
        max_caption_len=max_caption_len,
    )

    sampler = WeightedRandomSampler(
        weights=train_dataset.sample_weights(),
        num_samples=len(train_dataset),
        replacement=True,
    )

    collate_fn = partial(collate_caption_batch, pad_id=tokenizer.pad_id)
    loader_kwargs = {
        "batch_size": batch_size,
        "num_workers": num_workers,
        "collate_fn": collate_fn,
    }
    return (
        DataLoader(train_dataset, sampler=sampler, shuffle=False, **loader_kwargs),
        DataLoader(val_dataset, shuffle=False, **loader_kwargs),
        DataLoader(test_dataset, shuffle=False, **loader_kwargs),
        tokenizer,
    )


# Backwards-compatible aliases
WasteDataset = WasteCaptionDataset
build_datasets = build_caption_datasets
build_dataloaders = build_caption_dataloaders

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import torch
from PIL import Image
from torchvision import transforms

from .data import IMG_SIZE, MEAN, STD
from .labels import TOKEN_ALIASES, WASTE_TOKENS, default_caption_for
from .model import load_caption_model

DEFAULT_MODEL_PATH = Path(__file__).resolve().parent / "artifacts" / "transformer.pt"


@lru_cache(maxsize=2)
def _load_bundle(model_path: str):
    return load_caption_model(model_path)


def _prepare_image(image_input: str | Path | bytes | bytearray) -> torch.Tensor:
    transform = transforms.Compose(
        [
            transforms.Resize((IMG_SIZE, IMG_SIZE)),
            transforms.ToTensor(),
            transforms.Normalize(MEAN, STD),
        ]
    )
    if isinstance(image_input, (bytes, bytearray)):
        from io import BytesIO

        source = BytesIO(image_input)
    else:
        source = image_input
    with Image.open(source) as image:
        return transform(image.convert("RGB")).unsqueeze(0)


def _greedy_decode(model, memory, tokenizer, predicted_class: int, max_len: int = 16) -> tuple[str, list[str]]:
    max_len = max(2, min(max_len, model.max_text_len))
    token_ids = torch.tensor([[tokenizer.bos_id]], device=memory.device, dtype=torch.long)

    with torch.inference_mode():
        for _ in range(max_len - 1):
            caption_logits = model.decode(token_ids, memory)
            next_logits = caption_logits[:, -1, :]
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


def predict_image(image_path: str | Path | bytes | bytearray, model_path: str | Path = DEFAULT_MODEL_PATH):
    model_file = Path(model_path)
    if not model_file.exists():
        raise FileNotFoundError(f"Model file not found: {model_file}")

    model, tokenizer, _ = _load_bundle(str(model_file.resolve()))
    image_tensor = _prepare_image(image_path)

    with torch.inference_mode():
        class_logits, memory = model.encode_images(image_tensor)
        probabilities = torch.softmax(class_logits, dim=-1)[0]
        index = int(probabilities.argmax().item())
        text, tokens = _greedy_decode(model, memory, tokenizer, index)

    token = WASTE_TOKENS[index]
    return {
        "classifier_source": "nlp",
        "waste_type": token,
        "waste_label": TOKEN_ALIASES[token],
        "text": text,
        "tokens": tokens,
        "confidence": float(probabilities[index].item()),
    }

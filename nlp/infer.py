from __future__ import annotations

from functools import lru_cache
from io import BytesIO
import os
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

from .constants import IMG_SIZE, MEAN, STD
from .knowledge import grounded_response_for, response_satisfies_prompt
from .labels import TOKEN_ALIASES, WASTE_TOKENS, default_caption_for
from .tokenizer import CaptionTokenizer, build_tokenizer

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
DEFAULT_MODEL_PATH = ARTIFACTS_DIR / "model_fp16.onnx"
DEFAULT_TOKENIZER_PATH = ARTIFACTS_DIR / "tokenizer.json"

_MEAN = np.asarray(MEAN, dtype=np.float32).reshape(1, 1, 3)
_STD = np.asarray(STD, dtype=np.float32).reshape(1, 1, 3)


@lru_cache(maxsize=1)
def _get_tokenizer():
    if DEFAULT_TOKENIZER_PATH.exists():
        return CaptionTokenizer.from_file(DEFAULT_TOKENIZER_PATH)
    return build_tokenizer()


def _session_options() -> ort.SessionOptions:
    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    cpu_count = os.cpu_count() or 1
    default_threads = max(1, min(4, cpu_count))
    options.intra_op_num_threads = int(os.getenv("REL_ORT_INTRA_OP_THREADS", default_threads))
    options.inter_op_num_threads = int(os.getenv("REL_ORT_INTER_OP_THREADS", 1))
    return options


@lru_cache(maxsize=4)
def _load_session(model_path: str):
    session = ort.InferenceSession(
        model_path,
        sess_options=_session_options(),
        providers=["CPUExecutionProvider"],
    )
    inputs = session.get_inputs()
    outputs = session.get_outputs()
    if not inputs or not outputs:
        raise RuntimeError(f"Invalid ONNX model: {model_path}")
    return session, inputs[0].name, outputs[0].name


def _resolve_model_path(model_path: str | Path) -> Path:
    env_override = os.getenv("REL_ONNX_MODEL")
    if env_override:
        candidate = Path(env_override)
        if candidate.exists():
            return candidate

    candidate = Path(model_path)
    if candidate.exists():
        return candidate

    fallbacks = [
        ARTIFACTS_DIR / "model_fp16.onnx",
        Path(__file__).resolve().parents[2] / "nlp" / "artifacts" / "model_fp16.onnx",
    ]
    for fallback in fallbacks:
        if fallback.exists():
            return fallback

    searched = ", ".join(str(path) for path in [candidate, *fallbacks])
    raise FileNotFoundError(f"Model file not found. Searched: {searched}")


def _prepare_image(image_input: str | Path | bytes | bytearray) -> np.ndarray:
    if isinstance(image_input, (bytes, bytearray)):
        source = BytesIO(image_input)
    else:
        source = image_input

    with Image.open(source) as image:
        resized = image.convert("RGB").resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR)
        array = np.asarray(resized, dtype=np.float32) / 255.0

    array = (array - _MEAN) / _STD
    array = np.transpose(array, (2, 0, 1))[None, ...]
    return np.ascontiguousarray(array, dtype=np.float32)


def _softmax(logits: np.ndarray) -> np.ndarray:
    logits = logits.astype(np.float32, copy=False)
    shifted = logits - logits.max(axis=-1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=-1, keepdims=True)


def predict_image(
    image_path: str | Path | bytes | bytearray,
    model_path: str | Path = DEFAULT_MODEL_PATH,
    prompt: str | None = None,
):
    model_file = _resolve_model_path(model_path)
    session, input_name, output_name = _load_session(str(model_file.resolve()))
    image_tensor = _prepare_image(image_path)

    logits = session.run([output_name], {input_name: image_tensor})[0]
    probabilities = _softmax(logits)[0]
    index = int(probabilities.argmax())
    token = WASTE_TOKENS[index]

    tokenizer = _get_tokenizer()
    prompt_text = (prompt or "").strip()
    caption = grounded_response_for(token, prompt_text) if prompt_text else default_caption_for(token)
    caption_ids = tokenizer.encode(caption)
    text = caption if prompt_text else tokenizer.decode(caption_ids)
    if prompt_text and not response_satisfies_prompt(text, prompt_text):
        text = grounded_response_for(token, prompt_text)

    return {
        "classifier_source": "nlp",
        "model_source": "transformer",
        "runtime_source": "onnxruntime",
        "artifact": model_file.name,
        "waste_type": token,
        "waste_label": TOKEN_ALIASES[token],
        "text": text,
        "tokens": tokenizer.decode_ids(caption_ids),
        "confidence": float(probabilities[index]),
    }

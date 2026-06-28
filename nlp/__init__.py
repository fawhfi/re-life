from .constants import IMG_SIZE, MEAN, STD
from .labels import CLASS_TO_IDX, NUM_CLASSES, TOKEN_ALIASES, WASTE_TOKENS, default_caption_for
from .tokenizer import CaptionTokenizer, build_tokenizer

__all__ = [
    "CLASS_TO_IDX",
    "CaptionTokenizer",
    "IMG_SIZE",
    "MEAN",
    "NUM_CLASSES",
    "STD",
    "TOKEN_ALIASES",
    "WASTE_TOKENS",
    "build_tokenizer",
    "default_caption_for",
    "predict_image",
]


def __getattr__(name: str):
    if name == "predict_image":
        from .infer import predict_image

        return predict_image
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

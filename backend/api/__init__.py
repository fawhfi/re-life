"""API 初始化"""
from .auth import router as auth_router
from .data import router as data_router
from .scan import router as scan_router

__all__ = ["auth_router", "data_router", "scan_router"]

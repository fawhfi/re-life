"""Re-Life FastAPI 后端 - 主入口文件"""
from fastapi import FastAPI, File, UploadFile, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pathlib import Path
import sys

# 添加项目根目录到 Python 路径
root_dir = Path(__file__).parent
sys.path.insert(0, str(root_dir))

from api.scan import router as scan_router
from api.auth import router as auth_router
from api.data import router as data_router
from core.middleware import setup_middleware

app = FastAPI(
    title="Re-Life API",
    description="Sustainable waste management API with AI analysis",
    version="2.0.0"
)

# 设置中间件
setup_middleware(app)

# 注册路由
app.include_router(scan_router, prefix="/api", tags=["Scan"])
app.include_router(auth_router, prefix="/api", tags=["Auth"])
app.include_router(data_router, prefix="/api", tags=["Data"])

# 健康检查
@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "version": "2.0.0"}

# 根路径
@app.get("/")
async def root():
    return {"message": "Re-Life API", "version": "2.0.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)

"""Web 服务入口。启动 FastAPI + uvicorn。"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("web.app:app", host="0.0.0.0", port=8000, reload=True)

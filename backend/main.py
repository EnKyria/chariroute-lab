from fastapi import FastAPI, HTTPException
from mangum import Mangum
from pydantic import BaseModel, Field

app = FastAPI()


# リクエストの型
class RouteRequest(BaseModel):
    origin: str = Field(min_length=1)
    destination: str = Field(min_length=1)


# ルート候補1件の型
class RouteCandidate(BaseModel):
    type: str
    duration_minutes: int


# レスポンス全体の型
class RouteResponse(BaseModel):
    routes: list[RouteCandidate]


# ヘルスチェック
@app.get("/health")
def health():
    return {"status": "ok"}


# ルート検索
@app.post(
    "/api/routes/search",
    response_model=RouteResponse
)
def search_routes(request: RouteRequest):

    if request.origin == request.destination:
        raise HTTPException(
            status_code=400,
            detail="出発地と目的地が同じです"
        )

    return {
        "routes": [
            {
                "type": "bike_share",
                "duration_minutes": 18
            },
            {
                "type": "walk",
                "duration_minutes": 32
            }
        ]
    }

handler = Mangum(app)
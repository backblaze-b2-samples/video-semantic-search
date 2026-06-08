import logging

from fastapi import APIRouter, HTTPException

from app.service.search import search
from app.types import SearchRequest, SearchResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/search", response_model=SearchResponse)
async def search_endpoint(req: SearchRequest):
    try:
        return search(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_db
from utils.response import success, error, paginate

router = APIRouter()


@router.get("")
async def login_for_admin():
    """Admin login placeholder — extend with real auth"""
    return {"message": "admin route group ready"}

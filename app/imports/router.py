from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_session
from app.imports.service import MAX_BYTES, import_products

router = APIRouter(prefix="/api/imports", tags=["imports"])


@router.post("/products")
async def upload(
    session: Annotated[AsyncSession, Depends(get_session, scope="function")],
    file: Annotated[UploadFile, File()],
    allow_partial: Annotated[bool, Form()] = False,
) -> dict[str, int]:
    return await import_products(
        session, await file.read(MAX_BYTES + 1), allow_partial=allow_partial
    )

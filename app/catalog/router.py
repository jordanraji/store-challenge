from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import service
from app.catalog.schemas import ProductInput, ProductOutput, ProductPage, ProductUpdate
from app.core.dependencies import get_session

router = APIRouter(prefix="/api/products", tags=["products"])
SessionDependency = Annotated[AsyncSession, Depends(get_session, scope="function")]


@router.post("", response_model=ProductOutput, status_code=201)
async def create(data: ProductInput, session: SessionDependency) -> Any:
    return await service.create_product(session, data)


@router.get("", response_model=ProductPage)
async def search(
    session: SessionDependency,
    q: str = Query(default="", max_length=200),
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Any:
    return await service.search_products(session, q.strip(), page, page_size)


@router.get("/{product_id}", response_model=ProductOutput)
async def get(product_id: int, session: SessionDependency) -> Any:
    return await service.get_product(session, product_id)


@router.put("/{product_id}", response_model=ProductOutput)
async def update(product_id: int, data: ProductUpdate, session: SessionDependency) -> Any:
    return await service.update_product(session, product_id, data)


@router.delete("/{product_id}", status_code=204)
async def delete(
    product_id: int, session: SessionDependency, version: int = Query(gt=0)
) -> Response:
    await service.delete_product(session, product_id, version)
    return Response(status_code=204)

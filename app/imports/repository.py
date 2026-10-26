from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.imports.models import ImportBatch


class ImportBatchRepository:
    async def create(self, session: AsyncSession, batch: ImportBatch) -> ImportBatch:
        session.add(batch)
        await session.flush()
        return batch

    async def get_for_update(
        self, session: AsyncSession, batch_id: UUID, owner_id: str
    ) -> ImportBatch | None:
        return await session.scalar(
            select(ImportBatch)
            .where(ImportBatch.id == batch_id, ImportBatch.owner_id == owner_id)
            .with_for_update()
        )

    async def complete(self, session: AsyncSession, batch: ImportBatch, imported: int) -> None:
        batch.status = "completed"
        batch.imported = imported
        await session.flush()

    async def cancel(self, session: AsyncSession, batch: ImportBatch) -> None:
        batch.status = "cancelled"
        batch.products = []
        await session.flush()

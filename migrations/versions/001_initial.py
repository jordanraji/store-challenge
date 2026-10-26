import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("sku", sa.String(64), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("stock", sa.Integer(), nullable=False),
        sa.Column("weight_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("price >= 0", name="ck_product_price"),
        sa.CheckConstraint("stock >= 0", name="ck_product_stock"),
        sa.CheckConstraint("weight_kg >= 0", name="ck_product_weight"),
        sa.CheckConstraint("version > 0", name="ck_product_version"),
    )
    op.execute("ALTER TABLE products ADD COLUMN search_document tsvector")
    op.execute("ALTER TABLE products ADD COLUMN search_name text")
    op.execute("""
        CREATE FUNCTION update_product_search() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            NEW.search_name := unaccent(lower(NEW.name));
            NEW.search_document := to_tsvector('simple', unaccent(concat_ws(' ', NEW.name, NEW.sku, NEW.description, NEW.category)));
            RETURN NEW;
        END;
        $$
    """)
    op.execute(
        "CREATE TRIGGER product_search BEFORE INSERT OR UPDATE ON products FOR EACH ROW EXECUTE FUNCTION update_product_search()"
    )
    op.execute("CREATE INDEX ix_product_search ON products USING gin(search_document)")
    op.execute("CREATE INDEX ix_product_name_trgm ON products USING gin(search_name gin_trgm_ops)")
    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("client_id", sa.String(64), nullable=False),
        sa.Column("total", sa.Numeric(20, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("total >= 0", name="ck_order_total"),
    )
    op.create_table(
        "order_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Uuid(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_line_quantity"),
        sa.CheckConstraint("unit_price >= 0", name="ck_line_price"),
        sa.UniqueConstraint("order_id", "product_id"),
    )
    op.create_index("ix_order_lines_order_id", "order_lines", ["order_id"])
    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.String(64), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response", postgresql.JSONB(), nullable=True),
        sa.UniqueConstraint("client_id", "key", name="uq_idempotency_client_key"),
    )


def downgrade() -> None:
    op.drop_table("idempotency_records")
    op.drop_table("order_lines")
    op.drop_table("orders")
    op.drop_table("products")
    op.execute("DROP FUNCTION update_product_search()")

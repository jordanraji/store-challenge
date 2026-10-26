# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Buyers browsing and purchasing products are the primary audience. Inventory administrators manage products and CSV imports in a separate area. These two workflows are confirmed by the user and the challenge.

## Product Purpose

An e-commerce challenge implemented as a working store: discover products, review availability, create a cart and complete a simulated purchase. Administrators create, edit, deactivate and import products. CSV uploads with row errors require an explicit choice to import valid rows or cancel without changing inventory.

## Operating Context

The store is the home page; administration is separate. The interface is in English. The application runs locally on port 5000 through Docker Compose. All implementation and implementation documentation live under code/; AGENTS.md and ADRs.md remain at the repository root.

## Capabilities and Constraints

FastAPI, Jinja2, HTMX, locally served Bootstrap 5.3.8 and custom CSS for the established visual identity. PostgreSQL provides text search and trigram matching, optimistic product versions, atomic stock deduction and persistent order idempotency. USD is the backend's documented initial currency. Payments are simulated. There is no real delivery promise or payment provider. Administration is currently a local demonstration without authentication; do not imply otherwise.

## Brand Commitments

The project name is Store. The user requested a carefully designed interface using Impeccable, avoiding the appearance of a generic AI template. No logo, palette, font or imagery was supplied.

## Evidence on Hand

The original CSV and PDF are at the repository root. Product data includes name, SKU, description, category, price, stock and weight. The model has no product image field. No customer claims, sales metrics, reviews, delivery guarantees or promotional pricing are available and none should be invented. The live database may be empty; empty states must work without seeded products.

## Product Principles

- Keep the buying task clear, from search to confirmation.
- Use the same business rules for HTML and JSON.
- Show price, stock and failures plainly; preserve the cart when purchase fails.
- Prevent duplicate purchases through server-backed idempotency.
- Keep management tasks separate from shopping.

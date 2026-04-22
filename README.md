# NittanyAuction

Flask + SQLite. Python 3.5+.

## Setup

```bash
pip install flask
python load_data.py   # creates nittanyauction.db from CSV dataset
python app.py          # http://127.0.0.1:5000
```

`load_data.py` reads from `../NittanyAuctionDataset_v1/` and populates all tables. Drops and recreates the DB each run.

## Structure

```
app.py          → Flask app, registers blueprints
db.py           → get_db(), query_db(), connection lifecycle
schema.sql      → DDL for all 16 tables
load_data.py    → CSV → SQLite loader

routes/
  auth.py       → login, register, logout, profile
  listings.py   → browse, search, listing detail, bid, Q&A
  bidder.py     → watchlist, shopping cart, auction history, ratings, seller application
  seller.py     → dashboard, list product, answer questions, category requests
  helpdesk.py   → request queue, category mgmt, analytics

templates/      → Jinja2, organized by blueprint. base.html is the shared layout.
```

## Schema

Follows the provided relational schema. Composite PK on `Auction_Listings(Seller_Email, Listing_ID)`. Listing_ID is per-seller, not global. `Bids` references this composite FK.

Auctions end by bid count (`Max_bids`), not time. Status: `1` active, `0` inactive, `2` sold.

Two Phase 1 tables (`Questions` for product Q&A, `Watchlist` for saved search alerts) plus `Shopping_Cart` (saved listings, composite FK to `Auction_Listings`) for the Phase 2 cart feature. No CSV data for these, populated through the app.

## Auth

Session-based. Roles (`bidder`, `seller`, `helpdesk`) are resolved from DB at login and stored in `session['roles']`. Each blueprint enforces its own access via `before_request`.

Passwords are plaintext per the provided dataset. Not production.

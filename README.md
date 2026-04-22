# NittanyAuction

Web prototype of the NittanyAuction campus auction platform
for Lion State University.

**Contributors:**
[JaeMin Birdsall](https://github.com/JaeMinBird) ·
[Frank Zhou](https://github.com/fzhou1010) ·
[Elvis Chin](https://github.com/ChinElvis) ·
[Alexander Vedernikov](https://github.com/AlexanderVedernikov)

## Setup

```bash
pip install -r requirements.txt
python load_data.py   # builds nittanyauction.db from NittanyAuctionDataset_v1/*.csv
python app.py         # http://127.0.0.1:5000
```

`load_data.py` drops any existing DB, re-runs `schema.sql`, then loads every CSV in
`NittanyAuctionDataset_v1/`. It SHA256-hashes every `Users.password` on insert, so
the DB never contains plaintext credentials, even the seed rows. Re-run it any time
to reset to a clean state.

Login: any seeded `Users.email` + its plaintext password from the dataset will work.
The mailbox `helpdeskteam@lsu.edu` is the pseudo "unassigned" address where new
help requests land; real staff accounts come from `Helpdesk.csv`.

## Directory layout

```
app.py            Flask entry, blueprint registration, nav-notification context
db.py             get_db / query_db, request_desc helpers, HELPDESK_TEAM_EMAIL
schema.sql        DDL for every table + views + indexes
load_data.py      CSV → SQLite loader (hashes passwords, honors FK order)
notifications.py  notify() helper used across routes

routes/
  auth.py         login, registration, profile, ChangeID / BecomeSeller requests
  listings.py     browse, category hierarchy, search, bidding, payment
  bidder.py       cart, auction history, rating, seller upgrade application
  seller.py       dashboard, list/edit/remove, Q&A, category request, promotion
  helpdesk.py     queue, request handling, categories, analytics
  notifications.py shared notification inbox

templates/        Jinja templates, one folder per blueprint; base.html is the shell
static/           Assets (LSU logo)
NittanyAuctionDataset_v1/  Raw CSVs
```

## Feature → Code map

| Feature | Main file(s) |
|---|---|
| User Login | `routes/auth.py` (`login`), `templates/auth/login.html` |
| Category Hierarchy | `routes/listings.py` (`browse`, `get_all_subcategories`) |
| Auction Listing Management | `routes/seller.py` (`list_product*`, `edit_listing`, `remove_listing`), `templates/seller/dashboard.html` |
| Auction Bidding | `routes/listings.py` (`place_bid`, `check_auction_complete`, `pay`) |
| User Registration | `routes/auth.py` (`register`, `register_form`) |
| User Profile Update | `routes/auth.py` (`profile`, `changeID`), `templates/auth/profile.html` |
| Product Search | `routes/listings.py` (`browse`, search branch) |
| Rating | `routes/bidder.py` (`rate_seller`, `auction_history`), `Rating` table + `Seller_Avg_Rating` view |
| HelpDesk Support | `routes/helpdesk.py` (`queue`, `claim_request`, `handle_request`, `_handle_add_category`), `routes/seller.py` (`request_category`) |
| Auction Promotion | `routes/seller.py` (`promote_listing`), `routes/listings.py` (browse query) |
| Shopping Cart | `routes/bidder.py` (`shopping_cart`, `cart_add`, `cart_remove`), `Shopping_Cart` table |

## Schema overview (`schema.sql`)

Every table from the provided relational schema is present. `Auction_Listings` uses
the composite PK `(Seller_Email, Listing_ID)` so Listing_ID is per-seller; `Bids`
and `Transactions` reference that composite FK. The design is kept in **3NF**:
multi-valued attributes live in their own tables (`Credit_Cards`, `Shopping_Cart`),
and the `zipcode → city, state` dependency is captured by `Zipcode_Info` so
`Address` doesn't repeat it. Foreign keys are turned on at every connection
(`db.py` `get_db`).

Team-added tables: `Questions` (product Q&A), `Shopping_Cart` (persisted cart),
and `Notifications` (in-app alerts). Two columns
were added to `Auction_Listings` to record removal audit info (`remaining_bids`,
`reason_of_removal`) and three to track promotion state (`is_promoted`,
`promotion_fee`, `promotion_time`). `Categories` is self-referential with
`ON UPDATE CASCADE` so a helpdesk-driven rename propagates to children and
listings, and `ON DELETE` is restrictive so history can't be wiped by accident.

### Views and why they exist

- **`Seller_Avg_Rating`**: `AVG(Rating), COUNT(*)` grouped by seller. Every place
  that shows a seller's rating (seller dashboard, listing detail, browse card,
  shopping cart) reads from this view instead of re-aggregating, so the average
  stays consistent across the site and no caller can forget to compute it.
- **`Listing_Bid_Stats`**: `COUNT(*), MAX(Bid_Price)` grouped by listing. The
  seller dashboard and cart both need "how many bids so far / what's the top bid"
  for every listing on the page; the view lets them do that with a single
  `LEFT JOIN` instead of the N+1 correlated-subquery pattern we started with.

### Indexes

Five indexes cover the hot paths the routes actually hit: the notification-bell
lookup on every page, the `Bids (Seller_Email, Listing_ID)` join that powers both
views, `(Status, Category)` for browse filtering, `Rating(Seller_Email)` for the
avg view, and `Shopping_Cart(Bidder_Email)` for the cart page.

## Auth model

Session-based. On login we resolve `session['roles']` by probing `Bidders`,
`Sellers`, and `Helpdesk`; a single user may hold more than one role (e.g. a
student seller is also a bidder). Each blueprint's `before_request` gate enforces
its own access, so a bidder can't reach `/seller/*` or `/helpdesk/*` by URL
guessing. Passwords are SHA256-hashed at registration, at every login compare, and
in the CSV loader; password inputs are masked everywhere they appear.

## Key rules, where they live

- No self-bidding, +$1 minimum increment, turn-taking, and `Max_bids` termination
  -> `listings.place_bid`.
- Reserve-price gate on auction close -> `listings.check_auction_complete`.
- Sold / inactive listings are hidden -> every browse and search query filters on
  `Status = 1`.
- Edit lock once a listing has bids, and removal-audit capture
  -> `seller.edit_listing` and `seller.remove_listing`.
- Rating eligibility (paid transaction) and deduplication (partial unique index)
  -> `bidder.rate_seller` plus `idx_rating_unique_per_listing`.
- Credit-card privacy -> every `Credit_Cards` read in the app filters on
  `Owner_email = session['email']`.
- Reserve price is never rendered to bidders -> no template under
  `templates/listings/` references `Reserve_Price`.
- HelpDesk requests default to `helpdeskteam@lsu.edu` via
  `db.HELPDESK_TEAM_EMAIL`; staff claim a request, which reassigns it to their
  own email before they can act on it.

## Tech notes

Flask + Python 3 + SQLite. Search is plain parameterized SQL in `listings.browse`
(no third-party search library). The category tree is queried per request in
`listings.browse` and `seller.list_product`; nothing is hardcoded.

## Regenerating the DB

```bash
rm nittanyauction.db       # or: del nittanyauction.db  on Windows
python load_data.py
python app.py
```

`load_data.py` recreates the file every run, so there's no stale-state failure
mode. The team-added tables (`Questions`, `Shopping_Cart`, `Notifications`) start
empty and get populated through normal use of the app.

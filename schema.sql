-- we don't need pragma foreign keys 

CREATE TABLE IF NOT EXISTS Users ( -- all create should check whether table exists
    email TEXT PRIMARY KEY,
    password TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS Helpdesk (
    email TEXT PRIMARY KEY,
    position TEXT NOT NULL,
    FOREIGN KEY (email) REFERENCES Users(email)
);

CREATE TABLE IF NOT EXISTS Requests (
    request_id INTEGER,
    sender_email TEXT NOT NULL,
    helpdesk_staff_email TEXT NOT NULL,
    request_type TEXT NOT NULL,
    request_desc TEXT,
    request_status INTEGER DEFAULT 0, -- we want the initial status of requests to be 0, meaning no request
    response_comment TEXT, -- helpdesk staff's note at approve/deny time (reason, approval remark, etc.)
    response_at TIMESTAMP, -- when the request was resolved (approved or denied)
    PRIMARY KEY (request_id),
    FOREIGN KEY (sender_email) REFERENCES Users(email),
    FOREIGN KEY (helpdesk_staff_email) REFERENCES Helpdesk(email)
);

CREATE TABLE IF NOT EXISTS Zipcode_Info (
    zipcode TEXT PRIMARY KEY,
    city TEXT NOT NULL,
    state TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS Address (
    address_id TEXT,
    zipcode TEXT NOT NULL,
    street_num TEXT,
    street_name TEXT,
    PRIMARY KEY (address_id),
    FOREIGN KEY (zipcode) REFERENCES Zipcode_Info(zipcode)
);

CREATE TABLE IF NOT EXISTS Bidders (
    email TEXT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    age INTEGER,
    home_address_id TEXT,
    major TEXT,
    phone TEXT,
    PRIMARY KEY (email),
    FOREIGN KEY (email) REFERENCES Users(email),
    FOREIGN KEY (home_address_id) REFERENCES Address(address_id)
);

CREATE TABLE IF NOT EXISTS Credit_Cards (
    credit_card_num TEXT PRIMARY KEY,
    card_type TEXT NOT NULL,
    expire_month INTEGER NOT NULL,
    expire_year INTEGER NOT NULL,
    security_code TEXT NOT NULL,
    Owner_email TEXT NOT NULL,
    FOREIGN KEY (Owner_email) REFERENCES Users(email)
);

CREATE TABLE IF NOT EXISTS Sellers (
    email TEXT,
    bank_routing_number TEXT,
    bank_account_number TEXT,
    balance REAL DEFAULT 0 CHECK(balance >= 0),
    PRIMARY KEY (email),
    FOREIGN KEY (email) REFERENCES Users(email)
);

CREATE TABLE IF NOT EXISTS Local_Vendors (
    email TEXT,
    business_name TEXT NOT NULL,
    business_address_id TEXT,
    customer_service_phone_number TEXT,
    PRIMARY KEY (email),
    FOREIGN KEY (email) REFERENCES Sellers(email),
    FOREIGN KEY (business_address_id) REFERENCES Address(address_id)
);

CREATE TABLE IF NOT EXISTS Categories (
    category_name TEXT,
    parent_category TEXT,
    PRIMARY KEY (category_name),
    -- ON UPDATE CASCADE: helpdesk-driven category rename propagates to children.
    -- ON DELETE defaults to NO ACTION so deleting a parent with children fails loudly instead of orphaning them.
    FOREIGN KEY (parent_category) REFERENCES Categories(category_name) ON UPDATE CASCADE
);
-- add condition - DONE
CREATE TABLE IF NOT EXISTS Auction_Listings (
    Seller_Email TEXT NOT NULL,
    Listing_ID INTEGER NOT NULL,
    Category TEXT NOT NULL,
    Auction_Title TEXT,
    Product_Name TEXT,
    Product_Description TEXT,
    Condition TEXT,
    Quantity INTEGER DEFAULT 1,
    Reserve_Price REAL NOT NULL,
    Max_bids INTEGER NOT NULL,
    remaining_bids INTEGER, --the number of bids on the product during the time of removal, if removed
    reason_of_removal TEXT, -- added a reason of removal from the auction listing
    is_promoted INTEGER DEFAULT 0, -- binary for whether the product is under promotion or not, default 0 for no
    promotion_fee REAL,
    promotion_time TIME,
    -- Status enum: 1=active, 0=inactive (seller-removed), 2=sold,
    -- 3=failed (auction closed with reserve price not met).
    Status INTEGER DEFAULT 1 CHECK(Status IN (0,1,2,3)),
    PRIMARY KEY (Seller_Email, Listing_ID),
    FOREIGN KEY (Seller_Email) REFERENCES Sellers(email),
    -- ON UPDATE CASCADE keeps listings consistent with helpdesk-driven category renames.
    -- ON DELETE RESTRICT prevents category deletion from silently wiping auction history (BR-9).
    FOREIGN KEY (Category) REFERENCES Categories(category_name) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS Bids (
    Bid_ID INTEGER PRIMARY KEY AUTOINCREMENT,
    Seller_Email TEXT NOT NULL,
    Listing_ID INTEGER NOT NULL,
    Bidder_Email TEXT NOT NULL,
    Bid_Price REAL NOT NULL CHECK(Bid_Price > 0),
    FOREIGN KEY (Seller_Email, Listing_ID) REFERENCES Auction_Listings(Seller_Email, Listing_ID),
    FOREIGN KEY (Bidder_Email) REFERENCES Bidders(email)
);

CREATE TABLE IF NOT EXISTS Transactions (
    Transaction_ID INTEGER,
    Seller_Email TEXT NOT NULL,
    Listing_ID INTEGER NOT NULL,
    Bidder_Email TEXT NOT NULL,
    Date TEXT,
    Payment REAL,
    PRIMARY KEY (Transaction_ID),
    FOREIGN KEY (Seller_Email, Listing_ID) REFERENCES Auction_Listings(Seller_Email, Listing_ID),
    FOREIGN KEY (Bidder_Email) REFERENCES Bidders(email)
);

CREATE TABLE IF NOT EXISTS Rating (
    Bidder_Email TEXT NOT NULL,
    Seller_Email TEXT NOT NULL,
    Listing_ID INTEGER, -- nullable so legacy seed rows (no per-listing anchor) still load
    Date TEXT NOT NULL,
    Rating INTEGER NOT NULL CHECK(Rating >= 1 AND Rating <= 5),
    Rating_Desc TEXT,
    PRIMARY KEY (Bidder_Email, Seller_Email, Date),
    FOREIGN KEY (Bidder_Email) REFERENCES Bidders(email),
    FOREIGN KEY (Seller_Email) REFERENCES Sellers(email),
    FOREIGN KEY (Seller_Email, Listing_ID) REFERENCES Auction_Listings(Seller_Email, Listing_ID)
);

-- BR-15: at most one rating per (bidder, seller, completed auction).
-- Partial index so seed rows with NULL Listing_ID are exempt.
CREATE UNIQUE INDEX IF NOT EXISTS idx_rating_unique_per_listing
    ON Rating(Bidder_Email, Seller_Email, Listing_ID)
    WHERE Listing_ID IS NOT NULL;

-- Team Phase 1 new feature: Product Q&A
CREATE TABLE IF NOT EXISTS Questions (
    question_id INTEGER PRIMARY KEY AUTOINCREMENT,
    Seller_Email TEXT NOT NULL,
    Listing_ID INTEGER NOT NULL,
    Bidder_Email TEXT NOT NULL,
    question_text TEXT NOT NULL,
    answer_text TEXT,
    answered INTEGER DEFAULT 0, -- whether the question has been answered or not
    question_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    answer_time TIMESTAMP,
    FOREIGN KEY (Seller_Email, Listing_ID) REFERENCES Auction_Listings(Seller_Email, Listing_ID),
    FOREIGN KEY (Bidder_Email) REFERENCES Bidders(email)
);

-- Notifications: per-user events emitted by the system (auction ended, outbid, etc.)
CREATE TABLE IF NOT EXISTS Notifications (
    notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient_email TEXT NOT NULL,
    notif_type TEXT NOT NULL,
    message TEXT NOT NULL,
    seller_email TEXT,
    listing_id INTEGER,
    is_read INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (recipient_email) REFERENCES Users(email) ON DELETE CASCADE,
    FOREIGN KEY (seller_email, listing_id) REFERENCES Auction_Listings(Seller_Email, Listing_ID)
);

-- Shopping Cart: bidders save listings for quick access and direct bidding
CREATE TABLE IF NOT EXISTS Shopping_Cart (
    Bidder_Email TEXT NOT NULL,
    Seller_Email TEXT NOT NULL,
    Listing_ID INTEGER NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (Bidder_Email, Seller_Email, Listing_ID),
    FOREIGN KEY (Bidder_Email) REFERENCES Bidders(email) ON DELETE CASCADE,
    FOREIGN KEY (Seller_Email, Listing_ID) REFERENCES Auction_Listings(Seller_Email, Listing_ID) ON DELETE CASCADE
);

-- Per-seller rating aggregate. Used anywhere avg rating / rating count is displayed
-- (seller dashboard, listing detail, future browse cards) so the aggregate lives in
-- one place and all callers stay consistent.
CREATE VIEW IF NOT EXISTS Seller_Avg_Rating AS
SELECT Seller_Email,
       AVG(Rating) AS Avg_Rating,
       COUNT(*) AS Rating_Count
FROM Rating
GROUP BY Seller_Email;

-- Per-listing bid aggregate (current highest bid + total bid count).
-- Replaces the correlated MAX/COUNT subqueries that recurred across the dashboard,
-- cart, and browse paths, and collapses the seller-dashboard N+1 into a LEFT JOIN.
CREATE VIEW IF NOT EXISTS Listing_Bid_Stats AS
SELECT Seller_Email,
       Listing_ID,
       COUNT(*) AS Bid_Count,
       MAX(Bid_Price) AS Current_Bid
FROM Bids
GROUP BY Seller_Email, Listing_ID;

-- Indexes on hot query paths identified in audit:
-- Notifications is queried by (recipient, is_read) on every page load via the
-- app-level context processor; the other four back the frequent filter/join
-- patterns in browse, seller dashboard, cart, and Seller_Avg_Rating.
CREATE INDEX IF NOT EXISTS idx_notifications_recipient_unread ON Notifications(recipient_email, is_read);
CREATE INDEX IF NOT EXISTS idx_bids_listing ON Bids(Seller_Email, Listing_ID);
CREATE INDEX IF NOT EXISTS idx_listings_status_category ON Auction_Listings(Status, Category);
CREATE INDEX IF NOT EXISTS idx_rating_seller ON Rating(Seller_Email);
CREATE INDEX IF NOT EXISTS idx_cart_bidder ON Shopping_Cart(Bidder_Email);
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
    FOREIGN KEY (Owner_email) REFERENCES Bidders(email)
);

CREATE TABLE IF NOT EXISTS Sellers (
    email TEXT,
    bank_routing_number TEXT,
    bank_account_number TEXT,
    balance REAL DEFAULT 0,
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
    PRIMARY KEY (category_name)
);

CREATE TABLE IF NOT EXISTS Auction_Listings (
    Seller_Email TEXT NOT NULL,
    Listing_ID INTEGER NOT NULL,
    Category TEXT NOT NULL,
    Auction_Title TEXT,
    Product_Name TEXT,
    Product_Description TEXT,
    Quantity INTEGER DEFAULT 1,
    Reserve_Price REAL,
    Max_bids INTEGER,
    remaining_bids INTEGER, --the number of bids on the product during the time of removal, if removed
    reason_of_removal TEXT, -- added a reason of removal from the auction listing
    is_promoted INTEGER DEFAULT 0, -- binary for whether the product is under promotion or not, default 0 for no
    promotion_fee REAL,
    promotion_time TIME,
    Status INTEGER DEFAULT 1,
    PRIMARY KEY (Seller_Email, Listing_ID),
    FOREIGN KEY (Seller_Email) REFERENCES Sellers(email),
    FOREIGN KEY (Category) REFERENCES Categories(category_name)
);

CREATE TABLE IF NOT EXISTS Bids (
    Bid_ID INTEGER PRIMARY KEY AUTOINCREMENT,
    Seller_Email TEXT NOT NULL,
    Listing_ID INTEGER NOT NULL,
    Bidder_Email TEXT NOT NULL,
    Bid_Price REAL NOT NULL,
    FOREIGN KEY (Seller_Email, Listing_ID) REFERENCES Auction_Listings(Seller_Email, Listing_ID),
    FOREIGN KEY (Bidder_Email) REFERENCES Bidders(email)
);

CREATE TABLE IF NOT EXISTS Transactions (
    Transaction_ID INTEGER,
    Seller_Email TEXT NOT NULL,
    Listing_ID INTEGER NOT NULL,
    Buyer_Email TEXT NOT NULL,
    Date TEXT,
    Payment REAL,
    PRIMARY KEY (Transaction_ID),
    FOREIGN KEY (Seller_Email, Listing_ID) REFERENCES Auction_Listings(Seller_Email, Listing_ID),
    FOREIGN KEY (Buyer_Email) REFERENCES Bidders(email)
);

CREATE TABLE IF NOT EXISTS Rating (
    Bidder_Email TEXT NOT NULL,
    Seller_Email TEXT NOT NULL,
    Date TEXT NOT NULL,
    Rating INTEGER NOT NULL CHECK(Rating >= 1 AND Rating <= 5),
    Rating_Desc TEXT,
    PRIMARY KEY (Bidder_Email, Seller_Email, Date),
    FOREIGN KEY (Bidder_Email) REFERENCES Bidders(email),
    FOREIGN KEY (Seller_Email) REFERENCES Sellers(email)
);

-- Team Phase 1 new feature: Product Q&A
CREATE TABLE IF NOT EXISTS Questions (
    question_id INTEGER PRIMARY KEY AUTOINCREMENT,
    Seller_Email TEXT NOT NULL,
    Listing_ID INTEGER NOT NULL,
    Bidder_Email TEXT NOT NULL,
    question_title TEXT NOT NULL,
    question_text TEXT NOT NULL,
    answer_text TEXT,
    answered INTEGER DEFAULT 0, -- whether the question has been answered or not
    question_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (Seller_Email, Listing_ID) REFERENCES Auction_Listings(Seller_Email, Listing_ID),
    FOREIGN KEY (Bidder_Email) REFERENCES Bidders(email)
);

-- Team Phase 1 new feature: Watchlist (saved search alerts)
CREATE TABLE IF NOT EXISTS Watchlist (
    watchlist_id INTEGER,
    Bidder_Email TEXT NOT NULL,
    category TEXT NOT NULL,
    max_price REAL NOT NULL CHECK(max_price > 0), --maximum price the user wants to keep track of the product until
    condition TEXT CHECK(condition IN ('New', 'Lightly Used', 'Used') OR condition IS NULL), --condition of the
    PRIMARY KEY (watchlist_id), --product that you want it in
    UNIQUE(Bidder_Email, category, max_price, condition),
    FOREIGN KEY (Bidder_Email) REFERENCES Bidders(email) ON DELETE CASCADE,
    FOREIGN KEY (category) REFERENCES Categories(category_name)
);

-- Notifications: per-user events emitted by the system (auction ended, outbid, etc.)
CREATE TABLE IF NOT EXISTS Notifications (
    notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
    Recipient_Email TEXT NOT NULL,
    notif_type TEXT NOT NULL,
    message TEXT NOT NULL,
    Seller_Email TEXT,
    Listing_ID INTEGER,
    is_read INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (Recipient_Email) REFERENCES Users(email),
    FOREIGN KEY (Seller_Email, Listing_ID) REFERENCES Auction_Listings(Seller_Email, Listing_ID)
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
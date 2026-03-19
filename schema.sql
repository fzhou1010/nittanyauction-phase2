PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS Users (
    email TEXT PRIMARY KEY,
    password TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS Helpdesk (
    email TEXT PRIMARY KEY,
    position TEXT NOT NULL,
    FOREIGN KEY (email) REFERENCES Users(email)
);

CREATE TABLE IF NOT EXISTS Requests (
    request_id INTEGER PRIMARY KEY,
    sender_email TEXT NOT NULL,
    helpdesk_staff_email TEXT NOT NULL,
    request_type TEXT NOT NULL,
    request_desc TEXT,
    request_status INTEGER DEFAULT 0,
    FOREIGN KEY (sender_email) REFERENCES Users(email),
    FOREIGN KEY (helpdesk_staff_email) REFERENCES Helpdesk(email)
);

CREATE TABLE IF NOT EXISTS Zipcode_Info (
    zipcode TEXT PRIMARY KEY,
    city TEXT NOT NULL,
    state TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS Address (
    address_id TEXT PRIMARY KEY,
    zipcode TEXT NOT NULL,
    street_num TEXT,
    street_name TEXT,
    FOREIGN KEY (zipcode) REFERENCES Zipcode_Info(zipcode)
);

CREATE TABLE IF NOT EXISTS Bidders (
    email TEXT PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    age INTEGER,
    home_address_id TEXT,
    major TEXT,
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
    email TEXT PRIMARY KEY,
    bank_routing_number TEXT,
    bank_account_number TEXT,
    balance REAL DEFAULT 0,
    FOREIGN KEY (email) REFERENCES Users(email)
);

CREATE TABLE IF NOT EXISTS Local_Vendors (
    Email TEXT PRIMARY KEY,
    Business_Name TEXT NOT NULL,
    Business_Address_ID TEXT,
    Customer_Service_Phone_Number TEXT,
    FOREIGN KEY (Email) REFERENCES Sellers(email),
    FOREIGN KEY (Business_Address_ID) REFERENCES Address(address_id)
);

CREATE TABLE IF NOT EXISTS Categories (
    category_name TEXT PRIMARY KEY,
    parent_category TEXT
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
    Status INTEGER DEFAULT 1,
    PRIMARY KEY (Seller_Email, Listing_ID),
    FOREIGN KEY (Seller_Email) REFERENCES Sellers(email),
    FOREIGN KEY (Category) REFERENCES Categories(category_name)
);

CREATE TABLE IF NOT EXISTS Bids (
    Bid_ID INTEGER PRIMARY KEY,
    Seller_Email TEXT NOT NULL,
    Listing_ID INTEGER NOT NULL,
    Bidder_Email TEXT NOT NULL,
    Bid_Price REAL NOT NULL,
    FOREIGN KEY (Seller_Email, Listing_ID) REFERENCES Auction_Listings(Seller_Email, Listing_ID),
    FOREIGN KEY (Bidder_Email) REFERENCES Bidders(email)
);

CREATE TABLE IF NOT EXISTS Transactions (
    Transaction_ID INTEGER PRIMARY KEY,
    Seller_Email TEXT NOT NULL,
    Listing_ID INTEGER NOT NULL,
    Buyer_Email TEXT NOT NULL,
    Date TEXT,
    Payment REAL,
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
    question_text TEXT NOT NULL,
    answer_text TEXT,
    question_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (Seller_Email, Listing_ID) REFERENCES Auction_Listings(Seller_Email, Listing_ID),
    FOREIGN KEY (Bidder_Email) REFERENCES Bidders(email)
);

-- Team Phase 1 new feature: Watchlist
CREATE TABLE IF NOT EXISTS Watchlist (
    watchlist_id INTEGER PRIMARY KEY AUTOINCREMENT,
    Bidder_Email TEXT NOT NULL,
    category TEXT,
    max_price REAL,
    condition TEXT,
    FOREIGN KEY (Bidder_Email) REFERENCES Bidders(email),
    FOREIGN KEY (category) REFERENCES Categories(category_name)
);

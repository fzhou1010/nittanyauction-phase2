import csv
import sqlite3
import os
import sys

DB_PATH = os.path.join(os.path.dirname(__file__), 'nittanyauction.db')
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), 'schema.sql')

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'NittanyAuctionDataset_v1')

LOAD_ORDER = [
    ('Users.csv', 'Users', ['email', 'password']),
    ('Helpdesk.csv', 'Helpdesk', ['email', 'Position']),
    ('Zipcode_Info.csv', 'Zipcode_Info', ['zipcode', 'city', 'state']),
    ('Address.csv', 'Address', ['address_id', 'zipcode', 'street_num', 'street_name']),
    ('Bidders.csv', 'Bidders', ['email', 'first_name', 'last_name', 'age', 'home_address_id', 'major']),
    ('Credit_Cards.csv', 'Credit_Cards', ['credit_card_num', 'card_type', 'expire_month', 'expire_year', 'security_code', 'Owner_email']),
    ('Sellers.csv', 'Sellers', ['email', 'bank_routing_number', 'bank_account_number', 'balance']),
    ('Local_Vendors.csv', 'Local_Vendors', ['Email', 'Business_Name', 'Business_Address_ID', 'Customer_Service_Phone_Number']),
    ('Categories.csv', 'Categories', ['parent_category', 'category_name']),
    ('Auction_Listings.csv', 'Auction_Listings', ['Seller_Email', 'Listing_ID', 'Category', 'Auction_Title', 'Product_Name', 'Product_Description', 'Quantity', 'Reserve_Price', 'Max_bids', 'Status']),
    ('Bids.csv', 'Bids', ['Bid_ID', 'Seller_Email', 'Listing_ID', 'Bidder_Email', 'Bid_Price']),
    ('Transactions.csv', 'Transactions', ['Transaction_ID', 'Seller_Email', 'Listing_ID', 'Buyer_Email', 'Date', 'Payment']),
    ('Ratings.csv', 'Rating', ['Bidder_Email', 'Seller_Email', 'Date', 'Rating', 'Rating_Desc']),
    ('Requests.csv', 'Requests', ['request_id', 'sender_email', 'helpdesk_staff_email', 'request_type', 'request_desc', 'request_status']),
]

def clean_value(val):
    if val is None:
        return None
    val = val.strip()
    if val == '':
        return None
    if val.startswith('$'):
        val = val.replace('$', '').replace(',', '').strip()
    return val

def load_csv(db, filename, table, columns):
    filepath = os.path.join(DATA_DIR, filename)
    if not os.path.exists(filepath):
        print(f'  SKIP {filename} (not found)')
        return 0

    placeholders = ', '.join(['?'] * len(columns))
    col_names = ', '.join(columns)
    sql = f'INSERT OR IGNORE INTO {table} ({col_names}) VALUES ({placeholders})'

    count = 0
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            values = []
            for col in columns:
                raw = row.get(col)
                if raw is None:
                    for k in row:
                        if k.strip().lower() == col.strip().lower():
                            raw = row[k]
                            break
                values.append(clean_value(raw))
            try:
                db.execute(sql, values)
                count += 1
            except sqlite3.IntegrityError as e:
                pass
    db.commit()
    return count

def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print('Removed existing database.')

    db = sqlite3.connect(DB_PATH)
    db.execute('PRAGMA foreign_keys = OFF')

    with open(SCHEMA_PATH) as f:
        db.executescript(f.read())
    print('Schema created.')

    for filename, table, columns in LOAD_ORDER:
        count = load_csv(db, filename, table, columns)
        print(f'  {table}: {count} rows loaded from {filename}')

    db.execute('PRAGMA foreign_keys = ON')
    db.close()
    print('Done. Database at:', DB_PATH)

if __name__ == '__main__':
    main()

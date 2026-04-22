# Populates the database from the CSV dataset
# Run this script once (python load_data.py) to create nittanyauction.db with all tables filled
# It deletes any existing DB and rebuilds from scratch using schema.sql + the CSV files
# Passwords are hashed with SHA256 before being stored (never stored as plaintext)

import csv
import sqlite3
import os
import sys
import hashlib # my team and I will be using hashlib to implement SHA256 for the passwords saved in the database

from db import HELPDESK_TEAM_EMAIL

# Path to the database file and Schema
DB_PATH = os.path.join(os.path.dirname(__file__), 'nittanyauction.db')
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), 'schema.sql')

# Path to the folder containing all the CSV files
DATA_DIR = os.path.join(os.path.dirname(__file__), 'NittanyAuctionDataset_v1')

# Each entry: (csv_filename, table_name, [column_names/attribute names])
# Tables with foreign keys are loaded after the tables they reference
LOAD_ORDER = [
    ('Users.csv', 'Users', ['email', 'password']),
    ('Helpdesk.csv', 'Helpdesk', ['email', 'position']),
    ('Zipcode_Info.csv', 'Zipcode_Info', ['zipcode', 'city', 'state']),
    ('Address.csv', 'Address', ['address_id', 'zipcode', 'street_num', 'street_name']),
    ('Bidders.csv', 'Bidders', ['email', 'first_name', 'last_name', 'age', 'home_address_id', 'major', 'phone']),
    ('Credit_Cards.csv', 'Credit_Cards', ['credit_card_num', 'card_type', 'expire_month', 'expire_year', 'security_code', 'Owner_email']),
    ('Sellers.csv', 'Sellers', ['email', 'bank_routing_number', 'bank_account_number', 'balance']),
    ('Local_Vendors.csv', 'Local_Vendors', ['email', 'business_name', 'business_address_id', 'customer_service_phone_number']),
    ('Categories.csv', 'Categories', ['parent_category', 'category_name']),
    ('Auction_Listings.csv', 'Auction_Listings', ['Seller_Email', 'Listing_ID', 'Category', 'Auction_Title', 'Product_Name', 'Product_Description', 'Quantity', 'Reserve_Price', 'Max_bids', 'Status']),
    ('Bids.csv', 'Bids', ['Bid_ID', 'Seller_Email', 'Listing_ID', 'Bidder_Email', 'Bid_Price']),
    ('Transactions.csv', 'Transactions', ['Transaction_ID', 'Seller_Email', 'Listing_ID', 'Buyer_Email', 'Date', 'Payment']),
    ('Ratings.csv', 'Rating', ['Bidder_Email', 'Seller_Email', 'Date', 'Rating', 'Rating_Desc']),
    ('Requests.csv', 'Requests', ['request_id', 'sender_email', 'helpdesk_staff_email', 'request_type', 'request_desc', 'request_status']),
]

def clean_value(val):
    # Sanitize a single CSV field: strip whitespace
    # Convert blanks to None, and remove dollar signs/commas from monetary values, so they can be omitted and default values will apply
    if val is None:
        return None
    val = val.strip()
    if val == '':
        return None
    if val.startswith('$'):
        val = val.replace('$', '').replace(',', '').strip()
    return val

def hash_password(password):
    # Hash a password using SHA256
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def load_csv(db, filename, table, columns):
    # Read a CSV file and insert each row into the given table
    # Return the number of rows successfully inserted
    filepath = os.path.join(DATA_DIR, filename)
    if not os.path.exists(filepath): # file not found
        print(f'  SKIP {filename} (not found)')
        return 0

    # we dont want to have all of the columns in case of a column that is empty. instead use DEFAULT values

    count = 0
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # get the columns that have values
            rcols = []
            values = []
            for col in columns:
                raw = row.get(col)
                if raw is None:
                    for k in row:
                        if k.strip().lower() == col.strip().lower():
                            raw = row[k]
                            break
                val = clean_value(raw)
                # Hash passwords for the Users table
                if table == 'Users' and col == 'password' and val is not None:
                    val = hash_password(val)

                # we want to check whether the value is none so we can omit the column and we can apply the default value from schema
                if val is None:
                    continue
                #otherwise, append the column since there is a value
                rcols.append(col)
                values.append(val)
            # skip csv lines if all empty
            if not rcols:
                continue
            
            
            placeholders = ', '.join(['?'] * len(rcols))   # e.g. "?, ?, ?"
            col_names = ', '.join(rcols)                   # e.g. "email, password"
            sql = f'INSERT OR IGNORE INTO {table} ({col_names}) VALUES ({placeholders})'

            try:
                db.execute(sql, values)
                count += 1 #increase the count of the rows processed
            except sqlite3.IntegrityError as e:
                print(e) #print the integrity error
                pass
    db.commit()
    return count

def main():
    # Start fresh -> delete old DB so we don't get duplicate/stale data
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print('Removed existing database.')

    db = sqlite3.connect(DB_PATH)
    db.execute('PRAGMA foreign_keys = OFF')  # Temporarily off so we can load in any order

    # Create all tables defined in schema.sql
    with open(SCHEMA_PATH) as f:
        db.executescript(f.read())
    print('Schema created.')

    # Load each CSV into its corresponding table
    for filename, table, columns in LOAD_ORDER:
        count = load_csv(db, filename, table, columns)
        print(f'  {table}: {count} rows sucessfully loaded from {filename}')

    # Seed the sentinel "unassigned" helpdesk account. Requests submitted by
    # users before a staff member claims them point at this email via
    # Requests.helpdesk_staff_email, which has a FK to Helpdesk(email). No one
    # logs in as this account — the password is an unusable placeholder.
    db.execute(
        'INSERT OR IGNORE INTO Users (email, password) VALUES (?, ?)',
        [HELPDESK_TEAM_EMAIL, '!unassigned!'],
    )
    db.execute(
        'INSERT OR IGNORE INTO Helpdesk (email, position) VALUES (?, ?)',
        [HELPDESK_TEAM_EMAIL, 'Unassigned Queue'],
    )
    db.commit()
    print(f'  Seeded sentinel helpdesk account: {HELPDESK_TEAM_EMAIL}')

    db.execute('PRAGMA foreign_keys = ON')  # Reenable FK enforcement for normal use
    db.close()
    print('Done. Database at:', DB_PATH)

if __name__ == '__main__':
    main()

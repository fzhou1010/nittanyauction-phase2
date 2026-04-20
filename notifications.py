from db import get_db


def notify(recipient_email, notif_type, message, seller_email=None, listing_id=None):
    """Insert a notification for a user. Caller is responsible for committing."""
    db = get_db()
    db.execute(
        'INSERT INTO Notifications (Recipient_Email, notif_type, message, Seller_Email, Listing_ID) '
        'VALUES (?, ?, ?, ?, ?)',
        [recipient_email, notif_type, message, seller_email, listing_id],
    )

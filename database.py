import sqlite3

def init_db():
    conn = sqlite3.connect("finance.db")
    cursor = conn.cursor()

    cursor.execute("""CREATE TABLE IF NOT EXISTS expenses (
                        id INTEGER PRIMARY KEY,
                        user_id INTEGER,
                        amount REAL,
                        category TEXT,
                        date TEXT)""")

    conn.commit()
    conn.close()

def add_expense(user_id, amount, category, date):
    conn = sqlite3.connect("finance.db")
    cursor = conn.cursor()
    
    cursor.execute("INSERT INTO expenses (user_id, amount, category, date) VALUES (?, ?, ?, ?)", 
                   (user_id, amount, category, date))
    
    conn.commit()
    conn.close()

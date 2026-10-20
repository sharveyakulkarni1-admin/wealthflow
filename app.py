import os
import sqlite3
import json
from csv import writer
from io import StringIO
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

app = FastAPI()
DB_FILE = "expenses.db"

# Database initialization
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            date TEXT NOT NULL,
            description TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS budgets (
            category TEXT PRIMARY KEY,
            amount REAL NOT NULL
        )
    ''')
    
    # Add dummy data if empty so the dashboard has visual graphs immediately
    cursor.execute("SELECT COUNT(*) FROM expenses")
    if cursor.fetchone()[0] == 0:
        dummy_expenses = [
            (120.50, 'Food', '2026-10-01', 'Grocery shopping'),
            (45.00, 'Transport', '2026-10-02', 'Fuel'),
            (850.00, 'Rent', '2026-10-01', 'October Rent'),
            (60.00, 'Entertainment', '2026-10-02', 'Movie night'),
            (35.20, 'Food', '2026-10-03', 'Dinner out')
        ]
        cursor.executemany("INSERT INTO expenses (amount, category, date, description) VALUES (?, ?, ?, ?)", dummy_expenses)
        
        dummy_budgets = [('Food', 300.00), ('Transport', 150.00), ('Rent', 1000.00), ('Entertainment', 200.00)]
        cursor.executemany("INSERT OR IGNORE INTO budgets (category, amount) VALUES (?, ?)", dummy_budgets)
        
    conn.commit()
    conn.close()

init_db()

class ExpenseItem(BaseModel):
    amount: float
    category: str
    date: str
    description: str = ""

class BudgetItem(BaseModel):
    category: str
    amount: float

# Serve the HTML frontend directly from the same folder
@app.get("/", response_class=HTMLResponse)
async def get_frontend():
    if not os.path.exists("index.html"):
        raise HTTPException(status_code=500, detail="index.html file not found in the server directory.")
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/api/expenses")
async def get_expenses():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM expenses ORDER BY date DESC")
    rows = cursor.fetchall()
    
    cursor.execute("SELECT * FROM budgets")
    budgets = {r[0]: r[1] for r in cursor.fetchall()}
    conn.close()
    
    expenses = [{"id": r[0], "amount": r[1], "category": r[2], "date": r[3], "description": r[4]} for r in rows]
    return {"expenses": expenses, "budgets": budgets}

@app.post("/api/expenses")
async def add_expense(item: ExpenseItem):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO expenses (amount, category, date, description) VALUES (?, ?, ?, ?)",
                   (item.amount, item.category, item.date, item.description))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.delete("/api/expenses/{expense_id}")
async def delete_expense(expense_id: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/budgets")
async def set_budget(item: BudgetItem):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO budgets (category, amount) VALUES (?, ?)", (item.category, item.amount))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.get("/api/export")
async def export_csv():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT amount, category, date, description FROM expenses")
    rows = cursor.fetchall()
    conn.close()
    
    si = StringIO()
    cw = writer(si)
    cw.writerow(["Amount", "Category", "Date", "Description"])
    cw.writerows(rows)
    
    response = StreamingResponse(iter([si.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=expenses.csv"
    return response

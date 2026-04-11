from flask import Flask, render_template, request, jsonify, redirect, url_for
import barcode
from barcode.writer import ImageWriter
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from db import db



app = Flask(__name__)


DATA_FILE = 'products.csv'
BARCODE_FOLDER = 'static/barcodes'

os.makedirs(BARCODE_FOLDER, exist_ok=True)

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_name('/etc/secret/c.json', SCOPES)
client = gspread.authorize(creds)
# ---------- Globl variables ----------
product_sheet_key="1-ehBU680I4LuZl5B6p6SoihZCZcb75ODYSG6kJhEpLo"
product_sheet=client.open_by_key(product_sheet_key).sheet1
bill_sheet_key="1Frdo7NVgnS5bPUCXOAYSNvdzfWcBQz7tAfPdRucWKGw"
bill_sheet=client.open_by_key(bill_sheet_key).sheet1
PRODUCT_CACHE = []

# ---------- Helper Functions ----------
def safe_append(sheet, data_dict):

    headers = sheet.row_values(1)

    row = []
    for header in headers:
        row.append(data_dict.get(header, ""))

    # find next empty row
    data = sheet.get_all_values()
    next_row = len(data) + 1

    sheet.insert_row(row, next_row)

def get_products_from_sheet():
    try:
        sheet = product_sheet
        data = sheet.get_all_records()

        products = []
        for row in data:
            products.append({
                "code": str(row["ProductCode"]).strip().upper(),
                "name": str(row["Name"]).strip(),
                "price": float(row["Price"]),
                "stock": int(row["Stock"])
            })
        return products

    except Exception as e:
        print("Sheet Error:", e)
        return []

def load_products():
    global PRODUCT_CACHE
    PRODUCT_CACHE = get_products_from_sheet()


with app.app_context():
    load_products()# call function at app starting

def get_next_bill_no():
    try:
        sheet = bill_sheet
        data = sheet.get_all_records()

        if not data:
            return 1001  # starting number

        last_bill = data[-1]["BillNo"]
        return int(last_bill) + 1

    except Exception as e:
        print("Bill No Error:", e)
        return 1001

def get_next_product_code():
    try:
        sheet = product_sheet
        data = sheet.get_all_records()

        if not data:
            return "P001"

        max_num = 0

        for row in data:
            code = str(row["ProductCode"]).replace("P", "").strip()
            if code.isdigit():
                max_num = max(max_num, int(code))

        return f"P{max_num+1:03d}"

    except Exception as e:
        print("Code Error:", e)
        return "P001"
    

def change_stock(product_code, change):
    try:
        sheet = product_sheet
        data = sheet.get_all_records()

        for i, row in enumerate(data, start=2):
            if str(row["ProductCode"]).strip().upper() == product_code:

                headers = sheet.row_values(1)
                stock_col = headers.index("Stock") + 1

                current_stock = int(row["Stock"])
                new_stock = current_stock + change

                sheet.update_cell(i, stock_col, new_stock)

                return new_stock

        return None

    except Exception as e:
        print("Stock Change Error:", e)
        return None
# ---------- Routes ----------

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/order')
def order():
    
    return render_template("order_page.html", products=PRODUCT_CACHE)

@app.route('/refresh-products')
def refresh_products():
    load_products()  # cache update
    return "Products Synced ✅"

@app.route('/bill')
def bill():
    bill_no = get_next_bill_no()
    return render_template("bill.html", bill_no=bill_no)



@app.route("/save-bill", methods=["POST"])
def save_bill():
    try:
        req = request.get_json()
        items = req.get("items", [])
        bill_no = req.get("bill_no")

        bill_ws = bill_sheet
        product_ws = product_sheet

        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 🔥 1. Prepare all bill rows (batch)
        bill_rows = []
        stock_changes = {}

        for item in items:
            total = item["price"] * item["count"]

            bill_rows.append([
                bill_no,
                item["code"],
                item["name"],
                item["price"],
                item["count"],
                total,
                date
            ])

            # 🔥 stock change calculate
            count = item["count"]
            if count < 0:
                change = abs(count)
            else:
                change = -count

            stock_changes[item["code"]] = stock_changes.get(item["code"], 0) + change

        # 🔥 2. Insert all bill rows in ONE call
        bill_ws.append_rows(bill_rows)

        # 🔥 3. Update stock in ONE pass
        products = product_ws.get_all_records()
        headers = product_ws.row_values(1)
        stock_col = headers.index("Stock") + 1

        updates = []

        for i, row in enumerate(products, start=2):
            code = str(row["ProductCode"]).strip().upper()

            if code in stock_changes:
                current = int(row["Stock"])
                new_stock = current + stock_changes[code]

                updates.append({
                    "range": gspread.utils.rowcol_to_a1(i, stock_col),
                    "values": [[new_stock]]
                })

        if updates:
            product_ws.batch_update(updates)

        return jsonify({"status": "success"})

    except Exception as e:
        print("Save Error:", e)
        return jsonify({"status": "error", "message": str(e)})
@app.route("/products")
def products():
    sheet = product_sheet
    data = sheet.get_all_records()
    return render_template("products.html", products=data)

@app.route("/api/add-product", methods=["POST"])
def api_add_product():
    try:
        data = request.get_json()

        name = data["name"]
        price = float(data["price"])
        stock = int(data["stock"])

        code = get_next_product_code()

        # barcode
        barcode_class = barcode.get_barcode_class('code128')
        file_path = f"{BARCODE_FOLDER}/{code}"
        my_barcode = barcode_class(code, writer=ImageWriter())
        filename = my_barcode.save(file_path)

        # save sheet
        sheet = product_sheet
        
        data={
            "ProductCode":code,
            "Name":name,
            "Price":price,
            "Stock":stock
        }
        safe_append(sheet,data)

        return jsonify({
            "status": "success",
            "code": code,
            "barcode": f"/{filename}"
        })

    except Exception as e:
        print(e)
        return jsonify({"status": "error"})

@app.route("/bills")
def bills():
    sheet = bill_sheet
    data = sheet.get_all_records()

    # 🔥 group by BillNo
    bills = {}

    for row in data:
        bill_no = row["BillNo"]

        if bill_no not in bills:
            bills[bill_no] = {
                "bill_no": bill_no,
                "date": row["Date"],
                "items": [],
                "total": 0
            }

        bills[bill_no]["items"].append(row)
        bills[bill_no]["total"] += float(row["Total"])

    # convert dict → list
    bills_list = list(bills.values())

    return render_template("bills.html", bills=bills_list)
if __name__ == "__main__":
    port = int(os.environ.get("PORT",8080))
    app.run(host="0.0.0.0", port=port)



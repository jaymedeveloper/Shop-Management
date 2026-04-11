from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import barcode
from barcode.writer import ImageWriter
import os
from datetime import datetime
from db import db
from datetime import timedelta




app = Flask(__name__)
app.secret_key="inventory"
app.permanent_session_lifetime = timedelta(days=365)  # 1 year login

BARCODE_FOLDER = 'static/barcodes'

os.makedirs(BARCODE_FOLDER, exist_ok=True)




# ---------- Globl variables ----------


# ---------- Helper Functions ---------
def get_products_from_sheet(Uid):
    try:
        conn=db()
        cur=conn.cursor()
        cur.execute("SELECT code,name,price,stock FROM products WHERE user_id=%s",(Uid,))
        data=cur.fetchall()
        cur.close()
        conn.close()

        products = []
        for row in data:
            products.append({
                "code": str(row[0]).strip().upper(),
                "name": str(row[1]).strip(),
                "price": float(row[2]),
                "stock": int(row[3])
            })
        return products

    except Exception as e:
        print("Sheet Error:", e)
        return []

def get_next_bill_no(Uid):
    try:
        

        conn=db()
        cur=conn.cursor()
        cur.execute("SELECT MAX(bill_no) FROM bills WHERE user_id=%s", (Uid,))
        last = cur.fetchone()[0]
        cur.close()
        conn.close()

        return (last + 1) if last else 1001

    except Exception as e:
        print("Bill No Error:", e)
        return 1001

def get_next_product_code():
    try:
        Uid=session.get('Uid')
        conn=db()
        cur=conn.cursor()
        cur.execute("SELECT MAX(CAST(SUBSTRING(code, 2) AS INTEGER)) FROM products WHERE user_id=%s",(Uid,))
        last = cur.fetchone()[0]
        cur.close()
        conn.close()

        num = (last + 1) if last else 1
        return f"P{num:06d}"

    except Exception as e:
        print("Code Error:", e)
        return "P000001"
    

def change_stock(Uid,product_code, change):
    try:
        conn=db()
        cur=conn.cursor()
        cur.execute("UPDATE products SET stock = stock + %s WHERE user_id=%s AND code=%s",(change, Uid, product_code))
        conn.commit()        
        cur.close()
        conn.close()

        return None

    except Exception as e:
        print("Stock Change Error:", e)
        return None
# ---------- Routes ----------

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/login',methods=['GET', 'POST'])
def login():
    msg=""
    if request.method=='POST':
        
        number=request.form['mobile']
        password=request.form['password']

        conn=db()
        cur=conn.cursor()
        cur.execute("SELECT id From users WHERE mobile=%s and password=%s",(number,password))
        Uid=cur.fetchone()
        cur.close()
        conn.close()

        if Uid==None:
            msg="Wrong Mobile or Password"
        else:
            session['Uid']=Uid[0]
            session.permanent = True
            return redirect("/index")

    return render_template('login.html',msg=msg)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    msg = ""

    if request.method == 'POST':
        name = request.form['name']
        mobile = request.form['mobile']
        password = request.form['password']

        conn = db()
        cur = conn.cursor()

        # 🔥 check mobile already exists
        cur.execute("SELECT id FROM users WHERE mobile=%s", (mobile,))
        existing = cur.fetchone()

        if existing:
            msg = "Mobile already registered ❌"

        else:
            # 🔥 insert new user
            cur.execute(
                "INSERT INTO users (name, mobile, password) VALUES (%s,%s,%s)",
                (name, mobile, password)
            )
            conn.commit()

            # 🔥 auto login after signup
            cur.execute("SELECT id FROM users WHERE mobile=%s", (mobile,))
            user = cur.fetchone()

            session['Uid'] = user[0]
            session.permanent = True

            cur.close()
            conn.close()

            return redirect("/index")

        cur.close()
        conn.close()

    return render_template('signup.html', msg=msg)

@app.route('/index')
def index():
    Uid=session.get('Uid')
    return render_template('index.html')


@app.route('/order')
def order():
    Uid=session.get('Uid')
    product=get_products_from_sheet(Uid)
    return render_template("order_page.html", products=product)

@app.route('/refresh-products')
def refresh_products():  # cache update
    return "Products Synced ✅"

@app.route('/bill')
def bill():
    Uid=session.get('Uid')
    bill_no = get_next_bill_no(Uid)
    return render_template("bill.html", bill_no=bill_no)



@app.route("/save-bill", methods=["POST"])
def save_bill():
    try:
        Uid = session.get('Uid')

        if not Uid:
            return jsonify({"status": "error", "message": "Login required"})

        req = request.get_json()
        items = req.get("items", [])
        bill_no = req.get("bill_no")

        date = datetime.now()

        conn = db()
        cur = conn.cursor()

        # 🔥 1. INSERT INTO bills (MASTER)
        cur.execute(
            "INSERT INTO bills (user_id, bill_no, date) VALUES (%s,%s,%s)",
            (Uid, bill_no, date)
        )

        # 🔥 2. PREPARE ITEMS
        bill_rows = []

        for item in items:
            total = item["price"] * item["count"]

            bill_rows.append((
                bill_no,
                item["code"],
                item["name"],
                item["price"],
                item["count"],
                total,
                date
            ))

            # 🔥 STOCK UPDATE
            count = item["count"]
            change = abs(count) if count < 0 else -count

            change_stock(Uid, item["code"], change)

        # 🔥 3. INSERT ITEMS
        cur.executemany(
            "INSERT INTO bill_items (bill_no, code, name, price, qty, total, datetime) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            bill_rows
        )

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"status": "success"})

    except Exception as e:
        print("Save Error:", e)
        return jsonify({"status": "error", "message": str(e)})
    
@app.route("/products")
def products():

    Uid=session.get('Uid')
    conn=db()
    cur=conn.cursor()
    cur.execute("SELECT code, name, price, stock FROM products WHERE user_id=%s ORDER BY code ASC",(Uid,))    
    data=cur.fetchall()
    cur.close()
    conn.close()
    return render_template("products.html", products=data)

@app.route("/api/add-product", methods=["POST"])
def api_add_product():
    try:
        Uid=session.get('Uid')
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
        conn=db()
        cur=conn.cursor()
        cur.execute("INSERT INTO products (user_id, code, name, price,stock) VALUES (%s,%s,%s,%s,%s)",(Uid, code, name, price,stock))
        conn.commit()
        cur.close()
        conn.close()

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
    Uid = session.get('Uid')

    if not Uid:
        return redirect('/login')

    conn = db()
    cur = conn.cursor()

    # 🔥 get all bills
    cur.execute("""
        SELECT bill_no, date 
        FROM bills 
        WHERE user_id=%s 
        ORDER BY bill_no DESC
    """, (Uid,))
    bill_list = cur.fetchall()

    final_data = []

    for bill in bill_list:
        bill_no = bill[0]
        date = bill[1]

        # 🔥 get items of that bill
        cur.execute("""
            SELECT code, name, price, qty, total 
            FROM bill_items 
            WHERE bill_no=%s
            ORDER BY bill_no
        """, (bill_no,))
        items_data = cur.fetchall()

        items = []
        total_sum = 0

        for row in items_data:
            items.append({
                "code": row[0],
                "Name": row[1],
                "Price": row[2],
                "Qty": row[3],
                "Total": row[4]
            })
            total_sum += row[4]

        final_data.append({
            "bill_no": bill_no,
            "date": date.strftime("%Y-%m-%d %H:%M"),
            "total": total_sum,
            "items": items
        })

    cur.close()
    conn.close()

    return render_template("bills.html", bills=final_data)

if __name__ == "__main__":
    port = int(os.environ.get("PORT",8080))
    app.run(host="0.0.0.0", port=port, debug=True)



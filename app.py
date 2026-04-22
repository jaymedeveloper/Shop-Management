from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_file
import barcode
from barcode.writer import ImageWriter
import os
from datetime import datetime, timedelta
from db import db
from PIL import Image, ImageDraw, ImageFont
import io
import base64

app = Flask(__name__)
app.secret_key="inventory"
app.permanent_session_lifetime = timedelta(days=365)

BARCODE_FOLDER = 'static/barcodes'
os.makedirs(BARCODE_FOLDER, exist_ok=True)

# ---------- Helper Functions ---------
def add_is_active_column():
    try:
        conn = db()
        cur = conn.cursor()

        cur.execute("""
            ALTER TABLE products 
            ADD COLUMN is_active BOOLEAN DEFAULT TRUE
        """)

        conn.commit()
        cur.close()
        conn.close()
        print("Column added ✅")

    except Exception as e:
        print("Column शायद already exist:", e)


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

def generate_barcode_with_details(code, name, price):
    try:
        from flask import session
        import io
        import base64

        shop_name = session.get("name", "My Shop")

        writer = ImageWriter()
        writer.text = ""

        barcode_class = barcode.get_barcode_class('code128')
        barcode_instance = barcode_class(code, writer=writer)

        # 👇 memory me barcode generate
        buffer = io.BytesIO()
        barcode_instance.write(buffer)
        buffer.seek(0)

        barcode_img = Image.open(buffer)
        barcode_img = barcode_img.resize((400, 120))

        width, barcode_height = barcode_img.size
        total_height = 260

        final_img = Image.new('RGB', (width, total_height), 'white')
        draw = ImageDraw.Draw(final_img)

        try:
            font_path = "static/fonts/Roboto-Italic-VariableFont_wdth,wght.ttf"
            font_shop = ImageFont.truetype(font_path, 26)
            font_product = ImageFont.truetype(font_path, 24)
        except:
            font_shop = ImageFont.load_default()
            font_product = ImageFont.load_default()

        def center_text(text, y, font):
            text_width = draw.textlength(text, font=font)
            x = (width - text_width) // 2
            draw.text((x, y), text, fill='black', font=font)

        center_text(shop_name, 10, font_shop)
        draw.line((20, 45, width-20, 45), fill="black", width=1)
        center_text(f"{name} | PRICE: ₹{price}", 55, font_product)

        final_img.paste(barcode_img, (0, 100))

        # 👇 final image memory me save
        final_buffer = io.BytesIO()
        final_img.save(final_buffer, format="PNG")
        final_buffer.seek(0)

        # 👇 base64 me convert (frontend ke liye)
        img_base64 = base64.b64encode(final_buffer.getvalue()).decode()

        return f"data:image/png;base64,{img_base64}"

    except Exception as e:
        print("Error:", e)
        return ""

# ---------- Routes ----------

@app.route('/')
def home():
    if session.get('Uid'):
        return redirect('/index')
    return render_template('home.html')


@app.route('/login',methods=['GET', 'POST'])
def login():
    msg=""

    if request.method=='POST':
        number=request.form['mobile']
        password=request.form['password']

        conn=db()
        cur=conn.cursor()

        
        cur.execute("SELECT id, name FROM users WHERE mobile=%s AND password=%s",(number,password))
        user=cur.fetchone()

        cur.close()
        conn.close()

        if user is None:
            msg="Wrong Mobile or Password"
        else:
            session['Uid']=user[0]
            session['name']=user[1]   
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

        cur.execute("SELECT id FROM users WHERE mobile=%s", (mobile,))
        existing = cur.fetchone()

        if existing:
            msg = "Mobile already registered ❌"

        else:
            cur.execute(
                "INSERT INTO users (name, mobile, password) VALUES (%s,%s,%s)",
                (name, mobile, password)
            )
            conn.commit()

            cur.execute("SELECT id, name FROM users WHERE mobile=%s", (mobile,))
            user = cur.fetchone()

            session['Uid'] = user[0]
            session['name'] = user[1]  
            session.permanent = True

            cur.close()
            conn.close()

            return redirect("/index")

        cur.close()
        conn.close()

    return render_template('signup.html', msg=msg)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

    
@app.route('/index')
def index():
    if not session.get('Uid'):
        return redirect('/login')
    return render_template('index.html')


@app.route('/profile')
def profile():
    if not session.get('Uid'):
        return redirect('/login')

    name = session.get('name')
    return render_template('profile.html', name=name)


@app.route('/order')
@app.route('/order')
def order():
    Uid=session.get('Uid')

    conn=db()
    cur=conn.cursor()

    cur.execute("""
    SELECT code,name,price,stock 
    FROM products 
    WHERE user_id=%s AND is_active = TRUE
    """,(Uid,))

    data=cur.fetchall()

    print("ORDER PAGE DATA:", data)   # 👈 ADD THIS

    cur.close()
    conn.close()

    return render_template("order_page.html", products=data)

@app.route('/refresh-products')
def refresh_products():
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

        cur.execute(
            "INSERT INTO bills (user_id, bill_no, date) VALUES (%s,%s,%s)",
            (Uid, bill_no, date)
        )

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

            count = item["count"]
            change = abs(count) if count < 0 else -count
            change_stock(Uid, item["code"], change)

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

    cur.execute("""
    SELECT code, name, price, stock, is_active 
    FROM products 
    WHERE user_id=%s 
    ORDER BY code ASC
    """,(Uid,))

    data=cur.fetchall()

    cur.close()
    conn.close()

    return render_template("products.html", products=data)


@app.route("/api/toggle-product", methods=["POST"])
def toggle_product():
    try:
        Uid = session.get('Uid')
        data = request.get_json()

        code = data["code"]
        status = True if data["status"] == 1 else False   

        conn = db()
        cur = conn.cursor()

        cur.execute("""
            UPDATE products 
            SET is_active=%s 
            WHERE user_id=%s AND code=%s
        """, (status, Uid, code))

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"status": "success"})

    except Exception as e:
        print(e)
        return jsonify({"status": "error"})


@app.route("/api/add-product", methods=["POST"])
def api_add_product():
    try:
        Uid = session.get('Uid')
        data = request.get_json()

        name = data["name"]
        price = float(data["price"])
        stock = int(data["stock"])

        code = get_next_product_code()

        # Generate enhanced barcode with product details
        barcode_path = generate_barcode_with_details(code, name, price)

        conn = db()
        cur = conn.cursor()
        cur.execute("INSERT INTO products (user_id, code, name, price, stock) VALUES (%s,%s,%s,%s,%s)",
                   (Uid, code, name, price, stock))
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            "status": "success",
            "code": code,
            "barcode": barcode_path
        })

    except Exception as e:
        print(e)
        return jsonify({"status": "error", "message": str(e)})

@app.route("/api/update-product", methods=["POST"])
def update_product():
    try:
        Uid = session.get('Uid')
        data = request.get_json()

        code = data["code"]
        name = data["name"]
        price = float(data["price"])
        stock = int(data["stock"])

        conn = db()
        cur = conn.cursor()

        cur.execute("""
            UPDATE products
            SET name=%s, price=%s, stock=%s
            WHERE user_id=%s AND code=%s
        """, (name, price, stock, Uid, code))

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"status": "success"})

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

        cur.execute("""
            SELECT code, name, price, qty, total 
            FROM bill_items 
            WHERE bill_no=%s
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

@app.route("/download-barcode/<code>")
def download_barcode(code):
    try:
        Uid = session.get('Uid')

        conn = db()
        cur = conn.cursor()
        cur.execute("SELECT name, price FROM products WHERE user_id=%s AND code=%s", (Uid, code))
        product = cur.fetchone()
        cur.close()
        conn.close()

        if not product:
            return "Product not found"

        name, price = product

        # 👇 barcode generate (same function use karo)
        base64_img = generate_barcode_with_details(code, name, price)

        import base64, io
        from flask import send_file

        # base64 → binary
        image_data = base64.b64decode(base64_img.split(",")[1])
        buffer = io.BytesIO(image_data)

        return send_file(
            buffer,
            mimetype='image/png',
            as_attachment=True,
            download_name=f"{code}.png"
        )

    except Exception as e:
        print(e)
        return "Error"


if __name__ == "__main__":
    add_is_active_column()   # 👈 YE LINE ADD KARO
    port = int(os.environ.get("PORT",8080))
    app.run(host="0.0.0.0", port=port, debug=True)

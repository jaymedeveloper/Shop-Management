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
    """Generate a barcode image with product details"""
    try:
        # Generate the barcode
        barcode_class = barcode.get_barcode_class('code128')
        barcode_instance = barcode_class(code, writer=ImageWriter())
        
        # Save temporary barcode image
        temp_path = f"{BARCODE_FOLDER}/temp_{code}"
        barcode_filename = barcode_instance.save(temp_path)
        
        # Open the barcode image
        barcode_img = Image.open(barcode_filename)
        
        # Create a new image with space for text
        barcode_width, barcode_height = barcode_img.size
        text_height = 100  # Space for text at bottom
        new_height = barcode_height + text_height
        
        # Create new image with white background
        final_img = Image.new('RGB', (barcode_width, new_height), 'white')
        final_img.paste(barcode_img, (0, 0))
        
        # Draw text on the image
        draw = ImageDraw.Draw(final_img)
        
        # Try to load a font, fallback to default
        try:
            # For Windows
            font_title = ImageFont.truetype("arial.ttf", 20)
            font_normal = ImageFont.truetype("arial.ttf", 16)
        except:
            try:
                # For Linux/Mac
                font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
                font_normal = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
            except:
                # Default font
                font_title = ImageFont.load_default()
                font_normal = ImageFont.load_default()
        
        # Add product details
        y_position = barcode_height + 10
        
        # Product Code (highlighted)
        draw.text((10, y_position), f"Product Code: {code}", fill='black', font=font_title)
        y_position += 25
        
        # Product Name
        draw.text((10, y_position), f"Name: {name}", fill='black', font=font_normal)
        y_position += 22
        
        # Price/Amount
        draw.text((10, y_position), f"Price: ₹{price:.2f}", fill='black', font=font_normal)
        
        # Save the final image
        final_path = f"{BARCODE_FOLDER}/{code}_full.png"
        final_img.save(final_path)
        
        # Clean up temporary barcode file
        if os.path.exists(barcode_filename):
            os.remove(barcode_filename)
        
        return f"/{final_path}"
        
    except Exception as e:
        print(f"Error generating barcode with details: {e}")
        # Fallback to simple barcode
        barcode_class = barcode.get_barcode_class('code128')
        file_path = f"{BARCODE_FOLDER}/{code}"
        my_barcode = barcode_class(code, writer=ImageWriter())
        filename = my_barcode.save(file_path)
        return f"/{filename}"

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
def order():
    Uid=session.get('Uid')
    product=get_products_from_sheet(Uid)
    return render_template("order_page.html", products=product)

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
    cur.execute("SELECT code, name, price, stock FROM products WHERE user_id=%s ORDER BY code ASC",(Uid,))
    data=cur.fetchall()
    cur.close()
    conn.close()
    return render_template("products.html", products=data)


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


if __name__ == "__main__":
    port = int(os.environ.get("PORT",8080))
    app.run(host="0.0.0.0", port=port, debug=True)
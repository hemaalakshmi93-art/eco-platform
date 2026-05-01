from fileinput import filename
import os
from datetime import date, timedelta
from flask import Flask, render_template, request, redirect, session, url_for, flash
import mysql.connector

app = Flask(__name__)
app.secret_key = "eco123"

# -------------------- CONFIG --------------------
UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# -------------------- DB --------------------
try:
    db = mysql.connector.connect(
        host="localhost",
        user="root",
        password="Hemaa@2612",
        database="eco_platform"
    )
    cursor = db.cursor(buffered=True)
    print("✅ DB connected")

except Exception as e:
    print("❌ DB not connected:", e)
    db = None
    cursor = None

# -------------------- DATA --------------------
challenges_list = [
    {"title": "💧 Save Water", "desc": "Turn off tap while brushing", "points": 5},
    {"title": "🌱 Plant a Tree", "desc": "Plant at least one tree", "points": 20},
    {"title": "♻️ Reduce Plastic", "desc": "Avoid plastic for a day", "points": 10}
]

# -------------------- HOME --------------------
@app.route("/")
def home_page():
    return "Site is working 🚀"
    return render_template("home_page.html")

# -------------------- LOGIN --------------------
@app.route("/login_page")
def login_page():
    return render_template("login.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email = request.form["email"]
    password = request.form["password"]
    role = request.form["role"]

    if cursor:
        cursor.execute(
            "SELECT * FROM users WHERE email=%s AND password=%s AND role=%s",
            (email, password, role)
        )
        user = cursor.fetchone()
    else:
        user = None

    if user:
        name = user[1]
        session["name"] = name
        session["role"] = role
        return redirect(f"/dashboard/{name}/{role}")

    # ❌ WRONG LOGIN → use flash + redirect
    flash("Invalid Login ❌")
    return redirect(url_for("login"))

# -------------------- REGISTER --------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        return redirect("/login")
    return render_template("register.html")

# -------------------- DASHBOARD --------------------
@app.route("/dashboard/<name>/<role>")
def dashboard(name, role):

    cursor.execute(
        "SELECT points FROM users WHERE name=%s AND role=%s",
        (name, role)
    )
    row = cursor.fetchone()

    if row is None:
        cursor.execute("""
            INSERT INTO users (name, email, password, role, points)
            VALUES (%s,%s,%s,%s,%s)
        """, (name, "", "", role, 0))
        db.commit()
        points = 0
    else:
        points = row[0]

    badge = "Beginner 🌱"
    level = "Level 1"

    if points >= 50:
        badge = "Eco Learner 🌿"
        level = "Level 2"

    if points >= 100:
        badge = "Eco Warrior 🌳"
        level = "Level 3"

    students = []
    if role == "teacher":
        cursor.execute("SELECT name FROM users WHERE role=%s", ("student",))
        students = cursor.fetchall()

    cursor.execute(
        "SELECT DISTINCT date FROM points_history WHERE name=%s ORDER BY date DESC",
        (name,)
    )
    dates = cursor.fetchall()

    streak = 0
    today = date.today()

    for d in dates:
        if d[0] == today or d[0] == today - timedelta(days=1):
            streak += 1
            today -= timedelta(days=1)
        else:
            break

    return render_template(
        "dashboard.html",
        name=name,
        role=role,
        points=points,
        badge=badge,
        level=level,
        streak=streak,
        students=students
    )

# -------------------- CHALLENGES --------------------
@app.route("/challenges/<name>/<role>")
def challenges(name, role):
    return render_template(
        "challenges.html",
        name=name,
        role=role,
        challenges=challenges_list
    )

@app.route("/challenge/<name>/<role>")
def challenge_page(name, role):
    title = request.args.get("title")
    points = request.args.get("points")

    dos = []
    donts = []

    if title == "🌱 Plant a Tree":
        dos = [
            "Upload real sapling photo 🌱",
            "Show soil or planting action"
        ]
        donts = [
            "No drawings",
            "No big trees"
        ]

    elif title == "💧 Save Water":
        dos = [
            "Tap closed photo 🚰",
            "Water conservation action"
        ]
        donts = [
            "Running water",
            "Random sink photo"
        ]

    elif title == "♻️ Reduce Plastic":
        dos = [
            "Reusable bag 🛍️",
            "No plastic items"
        ]
        donts = [
            "Plastic bottles",
            "Plastic covers"
        ]

    return render_template(
        "challenge.html",
        name=name,
        role=role,
        title=title,
        points=points,
        dos=dos,
        donts=donts
    )

# -------------------- MISSION MAP --------------------
@app.route("/map/<name>")
def mission_map(name):

    cursor.execute("SELECT points FROM users WHERE name=%s", (name,))
    row = cursor.fetchone()
    points = row[0] if row else 0

    level1 = True
    level2 = points >= 30
    level3 = points >= 70

    return render_template(
        "map.html",
        name=name,
        level1=level1,
        level2=level2,
        level3=level3,
        points=points
    )

# -------------------- UPLOAD --------------------

@app.route("/upload", methods=["POST"])
def upload():

    name = request.form["name"]
    challenge = request.form["challenge"]
    points = int(request.form.get("points", 0))
    role = request.form.get("role")
    file = None
    mode = ""

    # 📸 Detect input
    if 'camera_image' in request.files and request.files['camera_image'].filename != "":
        file = request.files['camera_image']
        mode = "camera"
    elif 'upload_image' in request.files and request.files['upload_image'].filename != "":
        file = request.files['upload_image']
        mode = "upload"

    if not file:
        return render_template("result.html",
                               status="fail",
                               message="No file selected ❌")

    today = str(date.today())

    if "completed" not in session:
        session["completed"] = {}

    if today not in session["completed"]:
        session["completed"][today] = []

    if challenge in session["completed"][today]:
        return render_template("result.html",
                               status="fail",
                               message="Already completed today ⚠️")

    # 📁 Save file
    from werkzeug.utils import secure_filename
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    # 🤖 AI check
    if challenge == "Plant a Tree":
        valid = is_sapling(filepath)

    elif challenge == "Save Water":
        valid = is_save_water(filepath)

    elif challenge == "Reduce Plastic":
        valid = is_reduce_plastic(filepath)

    else:
        valid = False

    if not valid:
        return render_template("result.html",
            status="fail",
            message="❌ Invalid proof for this challenge",
            name=name,
            role=role)

    # 🎯 Points logic
    if mode == "camera":
        final_points = points
    else:
        final_points = points // 2

    session["completed"][today].append(challenge)

    cursor.execute(
        "UPDATE users SET points = points + %s WHERE name=%s",
        (final_points, name)
    )
    db.commit()

    cursor.execute(
        "INSERT INTO points_history (name, points, date) VALUES (%s,%s,%s)",
        (name, final_points, today)
    )
    db.commit()

    # ✅ SUCCESS RESPONSE
    return render_template("result.html",
                       status="success",
                       message=f"🌱 Sapling verified! +{final_points} points 🎉",
                       image=filename,
                       name=name,
                       role=role)

# -------------------- GRAPH --------------------
@app.route("/graph/<name>")
def graph(name):

    cursor.execute(
        "SELECT date, points FROM points_history WHERE name=%s ORDER BY date",
        (name,)
    )
    data = cursor.fetchall()

    dates = []
    points = []
    total = 0

    for d in data:
        dates.append(str(d[0]))
        total += d[1]
        points.append(total)

    return render_template(
        "graph.html",
        name=name,
        points=points,
        dates=dates,
        role=session.get("role")
    )

# -------------------- LEADERBOARD --------------------
@app.route("/leaderboard")
def leaderboard():

    name = session.get("name")
    role = session.get("role")

    if not name:
        return redirect("/login_page")

    cursor.execute(
        "SELECT name, points FROM users ORDER BY points DESC LIMIT 10"
    )
    data = cursor.fetchall()

    return render_template(
        "leaderboard.html",
        data=data,
        name=name,
        role=role
    )

# -------------------- EXISTING GAMES --------------------
@app.route("/game/<name>/<role>")
def game(name, role):
    return render_template("game_menu.html", name=name, role=role)

@app.route("/game_menu")
def game_menu():
    return render_template("game_menu.html")

@app.route("/puzzle_levelpage/<name>/<role>")
def puzzle_levelpage(name, role):
    return render_template("puzzle_levelpage.html", name=name, role=role)

@app.route("/puzzle")
def puzzle():
    size = request.args.get("size", 3)
    return render_template(
        "puzzle.html",
        size=size,
        name=request.args.get("name"),
        role=request.args.get("role")
    )

@app.route("/eco-catch")
def eco_catch():
    return render_template(
        "eco_catch.html",
        name=session.get("name"),
        role=session.get("role")
    )

@app.route("/seed-jumper")
def seed_jumper():
    return render_template(
        "seed_jumper.html",
        name=session.get("name"),
        role=session.get("role")
    )

@app.route("/tree")
def tree():
    return render_template("tree.html")

@app.route("/toxic_arena")
def toxic_arena():
    return render_template(
        "toxic_arena.html",
        name=session.get("name"),
        role=session.get("role")
    )

@app.route("/quiz")
def quiz():
    return render_template("quiz.html")

# -------------------- MISSIONS --------------------
@app.route("/trash_sort")
def trash_sort():
    return render_template("trash_sort.html")

@app.route("/lights_out")
def lights_out():
    return render_template("lights_out.html")

@app.route("/leak_hunter")
def leak_hunter():
    return render_template("leak_hunter.html")

@app.route("/canteen")
def canteen():
    return render_template("canteen.html")

@app.route("/cycle-dash")
def cycle_dash():
    return render_template("cycle-dash.html")

@app.route("/seed-shooter")
def seed_shooter():
    return render_template("seed-shooter.html")

@app.route("/tree-doctor")
def tree_doctor():
    return render_template("tree-doctor.html")

@app.route("/fire-rescue")
def fire_rescue():
    return render_template("fire-rescue.html")

@app.route("/food-chain")
def food_chain():
    return render_template("food-chain.html")

@app.route("/rain-puzzle")
def rain_puzzle():
    return render_template("rain-puzzle.html")

@app.route("/plastic-catcher")
def plastic_catcher():
    return render_template("plastic-catcher.html")

@app.route("/coral-builder")
def coral_builder():
    return render_template("coral-builder.html")

@app.route("/turtle-rescue")
def turtle_rescue():
    return render_template("turtle-rescue.html")

@app.route("/oil-spill")
def oil_spill():
    return render_template("oil-spill.html")

@app.route("/smart-fishing")
def smart_fishing():
    return render_template("smart-fishing.html")

@app.route("/ocean")
def ocean():
    return render_template("ocean.html")

@app.route('/profile/<name>')
def profile(name):
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="YOUR_PASSWORD",
            database="eco_platform"
        )
        cursor = conn.cursor()
    except:
        conn = None
        cursor = None

    cursor.execute("""
        SELECT name, role, points, streak, badge, level
        FROM users
        WHERE name=%s
    """, (name,))

    user = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template(
        "profile.html",
        name=user[0],
        role=user[1],
        points=user[2],
        streak=user[3],
        badge=user[4],
        level=user[5],
        challenges=0,
        games=0,
        trees=0
    )


@app.route('/update_profile', methods=['POST'])
def update_profile():
    old_name = request.form['name']
    new_name = request.form['new_name']

    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="Hemaa@2612",
        database="eco_platform"
    )
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE users
        SET name=%s
        WHERE name=%s
    """, (new_name, old_name))

    conn.commit()

    cursor.close()
    conn.close()

    return "success"


@app.route('/settings/<name>')
def settings(name):
    return render_template("settings.html", name=name)

try:
    from google.cloud import vision
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "key.json"
    vision_enabled = True
except:
    vision_enabled = False

from google.api_core.exceptions import ServiceUnavailable

def is_sapling(image_path):
    try:
        client = vision.ImageAnnotatorClient()

        with open(image_path, "rb") as img:
            content = img.read()

        image = vision.Image(content=content)
        response = client.label_detection(image=image)

        for label in response.label_annotations:
            name = label.description.lower()
            score = label.score

            print(name, score)  # debug 👀

            if name in ["plant", "seedling", "sapling"] and score > 0.7:
                return True

        return False

    except ServiceUnavailable:
        print("⚠️ Vision API unavailable")
        return False

def is_save_water(image_path):
    try:
        client = vision.ImageAnnotatorClient()

        with open(image_path, "rb") as img:
            content = img.read()

        image = vision.Image(content=content)
        response = client.label_detection(image=image)

        labels = [l.description.lower() for l in response.label_annotations]

        print(labels)

        # 💧 logic
        if "tap" in labels or "faucet" in labels:
            return True

        return False

    except:
        return False
    
def is_reduce_plastic(image_path):
    try:
        client = vision.ImageAnnotatorClient()

        with open(image_path, "rb") as img:
            content = img.read()

        image = vision.Image(content=content)
        response = client.label_detection(image=image)

        labels = [l.description.lower() for l in response.label_annotations]

        print(labels)

        # ♻️ logic
        if "recycling" in labels or "cloth" in labels or "bag" in labels:
            return True

        if "plastic" in labels:
            return False  # reject plastic 😏

        return False

    except:
        return False

import hashlib

def get_hash(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()

@app.route("/game1-city-builder.html")
def carbon():
    return render_template("game1-city-builder.html")

@app.route("/rain_rhythm.html")
def rain_rhythm():
    return render_template("rain_rhythm.html")

@app.route("/course")
def course():
    return render_template("course.html")

@app.route("/pollution_page")
def pollution():
    return render_template("pollution_page.html")

@app.route("/plants_page")
def plants():
    return render_template("plants_page.html")

@app.route("/water_page")
def water():
    return render_template("water_page.html")

@app.route("/carbon_page")
def carbons():
    return render_template("carbon_page.html")

@app.route("/hatchling-run.html")
def hatchling():
    return render_template("hatchling-run.html")

# -------------------- RUN --------------------
if __name__ == "__main__":
    app.run(debug=True)
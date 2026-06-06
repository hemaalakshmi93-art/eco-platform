from fileinput import filename
import os
from datetime import date, timedelta
from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify
import mysql.connector
import base64, json
import requests
from flask_mail import Mail, Message
import threading

app = Flask(__name__)
app.secret_key =  os.environ.get("SECRET_KEY")

app.config['MAIL_SERVER']         = 'smtp.gmail.com'
app.config['MAIL_PORT']           = 587
app.config['MAIL_USE_TLS']        = True
app.config['MAIL_USERNAME']       = 'hemaalakshmi93@gmail.com'
app.config['MAIL_PASSWORD']       = os.environ.get("MAIL_PASSWORD")
app.config['MAIL_DEFAULT_SENDER'] = 'hemaalakshmi93@gmail.com'

mail = Mail(app)
PLATFORM_URL = os.environ.get("PLATFORM_URL")

# -------------------- CONFIG --------------------
UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# -------------------- DB --------------------
try:
    db = mysql.connector.connect(
    host=os.environ.get("DB_HOST"),
    port=int(os.environ.get("DB_PORT")),
    user=os.environ.get("DB_USER"),
    password=os.environ.get("DB_PASSWORD"),
    database=os.environ.get("DB_NAME"),
    ssl_disabled=False
)
    cursor = db.cursor(buffered=True)
    print("✅ DB connected")
except Exception as e:
    print("❌ DB not connected:", e)
    db = None
    cursor = None

# -------------------- HELPER: reconnect --------------------
def get_cursor():
    global db, cursor
    try:
        db.ping(reconnect=True, attempts=3, delay=1)
    except Exception:
        db = mysql.connector.connect(
    host=os.environ.get("DB_HOST"),
    port=int(os.environ.get("DB_PORT")),
    user=os.environ.get("DB_USER"),
    password=os.environ.get("DB_PASSWORD"),
    database=os.environ.get("DB_NAME"),
    ssl_disabled=False
)
          
    cursor = db.cursor(buffered=True)
    return cursor

# -------------------- HELPER: get full user row --------------------
def get_user(name):
    cur = get_cursor()
    try:
        cur.execute("""
            SELECT name, email, role, points,
                   COALESCE(bio, '')              AS bio,
                   COALESCE(streak, 0)            AS streak,
                   COALESCE(trees, 0)             AS trees,
                   COALESCE(games, 0)             AS games,
                   COALESCE(challenges_done, 0)   AS challenges_done,
                   COALESCE(referral_code, '')    AS referral_code,
                   COALESCE(claimed_badges, '[]') AS claimed_badges,
                   last_login
            FROM users WHERE name=%s
        """, (name,))
        row = cur.fetchone()
    except Exception as e:
        print("⚠️ get_user full query failed:", e)
        cur.execute("SELECT name, email, role, points FROM users WHERE name=%s", (name,))
        row = cur.fetchone()
        if row:
            return {
                "name": row[0], "email": row[1], "role": row[2],
                "points": row[3] or 0, "bio": "", "streak": 0,
                "trees": 0, "games": 0, "challenges_done": 0,
                "referral_code": "", "claimed_badges": "[]", "last_login": None
            }
        return None

    if not row:
        return None

    return {
        "name": row[0], "email": row[1], "role": row[2],
        "points": row[3] or 0, "bio": row[4] or "",
        "streak": row[5] or 0, "trees": row[6] or 0,
        "games": row[7] or 0, "challenges_done": row[8] or 0,
        "referral_code": row[9] or "", "claimed_badges": row[10] or "[]",
        "last_login": row[11],
    }

# -------------------- HELPER: badge + level --------------------
def get_badge_level(points):
    if points >= 300: return "Eco Legend 🌎", "Level 4"
    elif points >= 100: return "Eco Warrior 🌳", "Level 3"
    elif points >= 50: return "Eco Learner 🌿", "Level 2"
    else: return "Beginner 🌱", "Level 1"

# -------------------- HELPER: streak --------------------
def calc_streak(name):
    cur = get_cursor()
    cur.execute(
        "SELECT DISTINCT date FROM points_history WHERE name=%s ORDER BY date DESC", (name,)
    )
    dates = cur.fetchall()
    streak = 0
    today = date.today()
    for d in dates:
        if d[0] == today or d[0] == today - timedelta(days=streak):
            streak += 1
        else:
            break
    return streak

# -------------------- HELPER: student progress for email --------------------
def get_student_progress(user_name):
    cur = get_cursor()
    cur.execute("""
        SELECT name, email, points,
               COALESCE(challenges_done, 0) AS challenges_done,
               COALESCE(streak, 0)          AS streak,
               COALESCE(class_name, '—')    AS class_name
        FROM users WHERE name = %s
    """, (user_name,))
    user = cur.fetchone()

    if not user:
        return None

    name            = user[0]
    email           = user[1]
    total_xp        = user[2] or 0
    challenges_done = user[3]
    class_name      = user[5]

    level        = total_xp // 200 + 1
    xp_needed    = level * 200
    xp_remaining = xp_needed - total_xp
    xp_percent   = round((total_xp % 200) / 200 * 100)
    level_titles = {2:"Eco Learner",3:"Eco Warrior",4:"Eco Legend",5:"Planet Guardian",6:"Eco Guardian"}

    cur.execute("SELECT name, points FROM users ORDER BY points DESC LIMIT 5")
    leaderboard_rows = cur.fetchall()
    rank_icons  = ["🥇","🥈","🥉","4️⃣","5️⃣"]
    leaderboard = []
    user_rank   = 1
    for i, row in enumerate(leaderboard_rows):
        is_user = (row[0] == name)
        if is_user:
            user_rank = i + 1
        leaderboard.append({
            "rank_icon": rank_icons[i], "name": row[0],
            "xp": f"{row[1]:,}", "is_user": is_user
        })

    badges = [
        {"icon":"🌱","name":"Green Sprout","desc":"Complete your first challenge",
         "earned": total_xp >= 5, "progress":"Complete 1 challenge"},
        {"icon":"♻️","name":"Recycle Hero","desc":"Earn 50+ points",
         "earned": total_xp >= 50, "progress":f"{max(0,50-total_xp)} XP to go"},
        {"icon":"💧","name":"Water Warden","desc":"Complete 3+ challenges",
         "earned": challenges_done >= 3, "progress":f"{max(0,3-challenges_done)}/3 done"},
        {"icon":"☀️","name":"Eco Learner","desc":"Earn 100+ points",
         "earned": total_xp >= 100, "progress":f"{max(0,100-total_xp)} XP to go"},
        {"icon":"🌳","name":"Eco Warrior","desc":"Earn 200+ points",
         "earned": total_xp >= 200, "progress":f"{max(0,200-total_xp)} XP to go"},
        {"icon":"🌎","name":"Eco Legend","desc":"Earn 300+ points",
         "earned": total_xp >= 300, "progress":f"{max(0,300-total_xp)} XP to go"},
    ]

    return {
        "name": name, "class_name": class_name, "email": email,
        "total_xp": f"{total_xp:,}", "quests_done": challenges_done, "rank": user_rank,
        "current_level": level, "next_level": level + 1,
        "xp_needed": f"{xp_needed:,}", "xp_remaining": f"{xp_remaining:,}",
        "xp_percent": xp_percent,
        "next_level_title": level_titles.get(level + 1, "Eco Master"),
        "badges": badges, "leaderboard": leaderboard,
        "platform_url": PLATFORM_URL,
        "unsubscribe_url": f"{PLATFORM_URL}/unsubscribe/{name}"
    }

# -------------------- DATA --------------------
challenges_list = [
    {"title": "💧 Save Water",           "desc": "Turn off tap while brushing teeth",            "points": 5},
    {"title": "♻️ Reduce Plastic",        "desc": "Avoid single-use plastic for a full day",      "points": 10},
    {"title": "🌳 Plant a Sapling",       "desc": "Plant a sapling and document your journey",    "points": 50},
    {"title": "🚯 Zero Plastic Day",      "desc": "Spend a full day without using plastic",       "points": 30},
    {"title": "🏖️ Area Cleanup",          "desc": "Collect and dispose waste from a public area", "points": 40},
    {"title": "💡 Lights Off Hour",       "desc": "Turn off all lights for one hour today",       "points": 20},
    {"title": "🍂 Compost Kitchen Waste", "desc": "Start composting your food scraps this week",  "points": 35},
    {"title": "🚴 Cycle to School",       "desc": "Replace your vehicle commute with cycling",    "points": 25},
    {"title": "🌧️ Rainwater Harvesting",  "desc": "Set up a basic rainwater collection system",   "points": 45},
    {"title": "🥗 Meatless Monday",       "desc": "Go vegetarian for an entire day",              "points": 15},
]

# -------------------- AI VERIFICATION --------------------
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

def verify_challenge_photo(filepath, challenge_title):
    prompts = {
        "💧 Save Water":            "Is there a tap or sink showing water being saved? Reply only yes or no.",
        "♻️ Reduce Plastic":        "Are there reusable bags or bottles with no plastic? Reply only yes or no.",
        "🌳 Plant a Sapling":       "Is there a seedling or plant being planted in soil? Reply only yes or no.",
        "🚯 Zero Plastic Day":      "Is there a meal on real plates with no plastic? Reply only yes or no.",
        "🏖️ Area Cleanup":          "Are there trash bags or people cleaning a public area? Reply only yes or no.",
        "💡 Lights Off Hour":       "Is the room dark with candles or natural light only? Reply only yes or no.",
        "🍂 Compost Kitchen Waste": "Is there a compost bin or food scraps like peels? Reply only yes or no.",
        "🚴 Cycle to School":       "Is there a bicycle or someone cycling? Reply only yes or no.",
        "🌧️ Rainwater Harvesting":  "Is there a bucket or barrel collecting rainwater? Reply only yes or no.",
        "🥗 Meatless Monday":       "Is there a vegetarian meal with vegetables and no meat? Reply only yes or no.",
    }
    prompt = prompts.get(challenge_title)
    if not prompt:
        return False, "Unknown challenge"

    try:
        with open(filepath, "rb") as f:
            image_bytes = f.read()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "meta-llama/llama-4-scout-17b-16e-instruct",
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                {"type": "text", "text": prompt}
            ]}],
            "max_tokens": 10
        }
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers, json=payload, timeout=30
        )
        print("GROQ STATUS:", response.status_code)
        if response.status_code != 200:
            return False, f"Groq API error: {response.status_code}"
        answer   = response.json()["choices"][0]["message"]["content"].strip().lower()
        approved = answer.startswith("yes")
        reason   = "Well done! Challenge completed successfully 🌱" if approved else "Please check your image and try again!"
        return approved, reason
    except Exception as e:
        return False, f"Verification error: {str(e)}"

# -------------------- WELCOME EMAIL --------------------
def send_welcome_email(to_email, user_name):
    def _send():
        try:
            import sendgrid
            from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition, ContentId
            import base64

            sg = sendgrid.SendGridAPIClient(api_key=os.environ.get("SENDGRID_API_KEY"))

            html_body = f"""
            <div style="font-family: Arial, sans-serif; max-width: 650px; margin: auto;
                        background: #f9fef5; padding: 24px; border-radius: 12px;">
              <h2 style="color: #2d7a45;">Welcome to Zephyra, {user_name}! 🌱</h2>
              <p style="font-size:15px; color:#2d5a3d;">
                We're thrilled to have you join our eco-community! 🌍
              </p>
              <img src="cid:zephyra_pamphlet"
                   alt="Zephyra Welcome Pamphlet"
                   style="width:100%; max-width:600px; border-radius:10px;
                          display:block; margin:16px auto;" />
              <div style="text-align:center; margin-top:24px;">
                <a href="https://eco-platform-3.onrender.com"
                   style="background:#2d7a45; color:white; padding:13px 32px;
                          border-radius:50px; text-decoration:none;
                          font-size:15px; font-weight:bold;">
                  Start Playing Now →
                </a>
              </div>
              <p style="font-size:13px; color:#888; text-align:center; margin-top:28px;">
                Questions? <a href="mailto:zephyrarespawn@gmail.com" style="color:#2d7a45;">
                zephyrarespawn@gmail.com</a><br/>
                © Zephyra — Learn • Play • Protect the Planet 🌿
              </p>
            </div>
            """

            message = Mail(
                from_email="zephyrarespawn@gmail.com",
                to_emails=to_email,
                subject=f"Welcome to Zephyra, {user_name}! 🌱 Your eco-journey begins",
                html_content=html_body
            )

            pamphlet_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zephyra_pamphlet.jpg")
            if os.path.exists(pamphlet_path):
                with open(pamphlet_path, "rb") as f:
                    encoded = base64.b64encode(f.read()).decode()
                attachment = Attachment(
                    FileContent(encoded),
                    FileName("Zephyra_Welcome_Pamphlet.jpg"),
                    FileType("image/jpeg"),
                    Disposition("inline"),
                    ContentId("zephyra_pamphlet")
                )
                message.attachment = attachment

            sg.send(message)
            print(f"✅ Welcome email sent to {to_email}")

        except Exception as e:
            print(f"❌ Welcome email failed: {e}")

    thread = threading.Thread(target=_send)
    thread.daemon = True
    thread.start()

# -------------------- HOME --------------------
@app.route("/")
def home():
    return render_template("home_page.html")

# -------------------- LOGIN --------------------
@app.route("/login_page")
def login_page():
    return render_template("login.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email    = request.form["email"]
    password = request.form["password"]
    role     = request.form["role"]
    cur      = get_cursor()
    cur.execute("SELECT * FROM users WHERE email=%s AND password=%s AND role=%s", (email, password, role))
    user = cur.fetchone()

    if user:
        name = user[1]
        session["name"] = name
        session["role"] = role
        today = date.today()
        try:
            cur.execute("SELECT last_login, streak FROM users WHERE name=%s", (name,))
            row        = cur.fetchone()
            last_login = row[0] if row else None
            old_streak = row[1] if row else 0
            if last_login is None or last_login < today - timedelta(days=1):
                new_streak = 1
            elif last_login == today - timedelta(days=1):
                new_streak = (old_streak or 0) + 1
            else:
                new_streak = old_streak or 1
            cur.execute("UPDATE users SET last_login=%s, streak=%s WHERE name=%s", (today, new_streak, name))
            db.commit()
        except Exception as e:
            print("⚠️ Streak update failed:", e)
        return redirect(f"/dashboard/{name}/{role}")

    flash("Invalid Login ❌")
    return redirect(url_for("login"))

# -------------------- CHATBOT ROUTE --------------------
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    messages = data.get("messages", [])
    
    SYSTEM_INSTRUCTION = """You are EcoBot, a friendly assistant on EcoLearn.
- Reply in maximum 2-3 short sentences only.
- Be warm and friendly.
- Only answer environment topics: pollution, climate, recycling, sustainability etc.
- If asked unrelated topics, politely redirect.
- No bullet points or lists. Short conversational answers only."""

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.environ.get('GROQ_API_KEY')}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "system", "content": SYSTEM_INSTRUCTION}] + messages,
                "max_tokens": 120
            },
            timeout=30
        )
        result = response.json()
        if "error" in result:
            return jsonify({"error": result["error"]["message"]}), 400
        reply = result["choices"][0]["message"]["content"]
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------------------- REGISTER --------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name          = request.form.get("name", "")
        email         = request.form.get("email", "")
        password      = request.form.get("password", "")
        role          = request.form.get("role", "student")
        referral_code = "TEACH-" + name[:4].upper() if role == "teacher" else ""
        cur = get_cursor()
        try:
            cur.execute("""
                INSERT INTO users (name, email, password, role, points, referral_code)
                VALUES (%s, %s, %s, %s, 0, %s)
            """, (name, email, password, role, referral_code))
            db.commit()
        except Exception as e:
            print("Register error:", e)

        # ✅ Send welcome pamphlet email after successful registration
        send_welcome_email(email, name)

        return redirect("/login")
    return render_template("register.html")

# -------------------- DASHBOARD --------------------
@app.route("/dashboard/<name>/<role>")
def dashboard(name, role):
    cur = get_cursor()
    cur.execute("SELECT points FROM users WHERE name=%s AND role=%s", (name, role))
    row = cur.fetchone()
    if row is None:
        cur.execute("INSERT INTO users (name, email, password, role, points) VALUES (%s,%s,%s,%s,%s)",
                    (name, "", "", role, 0))
        db.commit()
        points = 0
    else:
        points = row[0] or 0
    badge, level = get_badge_level(points)
    students = []
    if role == "teacher":
        cur.execute("SELECT name FROM users WHERE role=%s", ("student",))
        students = cur.fetchall()
    streak = calc_streak(name)
    return render_template("dashboard.html", name=name, role=role, points=points,
                           badge=badge, level=level, streak=streak, students=students)

# -------------------- PROFILE --------------------
@app.route("/profile/<name>/<role>")
def profile(name, role):
    user = get_user(name)
    if not user:
        flash("User not found")
        return redirect(f"/dashboard/{name}/{role}")
    streak       = calc_streak(name)
    badge, level = get_badge_level(user["points"])
    try:
        claimed_badges = json.loads(user["claimed_badges"] or "[]")
        if not isinstance(claimed_badges, list):
            claimed_badges = []
    except Exception:
        claimed_badges = []
    cur = get_cursor()
    try:
        cur.execute("SELECT COUNT(DISTINCT date) FROM points_history WHERE name=%s", (name,))
        challenges_done = cur.fetchone()[0] or 0
    except Exception:
        challenges_done = user.get("challenges_done", 0)
    return render_template("profile.html",
        name=name, email=user["email"], role=user["role"],
        level=level, bio=user["bio"], points=user["points"],
        streak=streak, trees=user["trees"], challenges=challenges_done,
        games=user["games"], badge=badge,
        referral_code=user["referral_code"], claimed_badges=claimed_badges)

# -------------------- UPDATE PROFILE --------------------
@app.route("/update_profile", methods=["POST"])
def update_profile():
    name     = request.form.get("name", "")
    new_name = request.form.get("new_name", name).strip()
    bio      = request.form.get("bio", "").strip()
    if not new_name:
        return "error"
    cur = get_cursor()
    try:
        cur.execute("UPDATE users SET name=%s, bio=%s WHERE name=%s", (new_name, bio, name))
        db.commit()
        session["name"] = new_name
        return "success"
    except Exception as e:
        print("update_profile error:", e)
        return "error"

# -------------------- CLAIM BADGE --------------------
@app.route("/claim_badge", methods=["POST"])
def claim_badge():
    name  = request.form.get("name", "")
    badge = request.form.get("badge", "")
    if not name or not badge:
        return "error"
    cur = get_cursor()
    try:
        cur.execute("SELECT COALESCE(claimed_badges, '[]') FROM users WHERE name=%s", (name,))
        row = cur.fetchone()
        if not row:
            return "error"
        try:
            claimed = json.loads(row[0])
            if not isinstance(claimed, list):
                claimed = []
        except Exception:
            claimed = []
        if badge not in claimed:
            claimed.append(badge)
            cur.execute("UPDATE users SET claimed_badges=%s WHERE name=%s", (json.dumps(claimed), name))
            db.commit()
        return "success"
    except Exception as e:
        print("claim_badge error:", e)
        try:
            cur.execute("ALTER TABLE users ADD COLUMN claimed_badges TEXT DEFAULT '[]'")
            db.commit()
        except Exception:
            pass
        return "error"

# -------------------- UPDATE SETTINGS --------------------
@app.route("/update_settings", methods=["POST"])
def update_settings():
    key   = request.form.get("key", "")
    value = request.form.get("value", "0")
    if "settings" not in session:
        session["settings"] = {}
    session["settings"][key] = (value == "1")
    session.modified = True
    return "success"

# -------------------- CHANGE PASSWORD --------------------
@app.route("/change_password", methods=["POST"])
def change_password():
    name         = request.form.get("name", "")
    current_pw   = request.form.get("current", "")
    new_password = request.form.get("new_password", "")
    cur = get_cursor()
    cur.execute("SELECT password FROM users WHERE name=%s", (name,))
    row = cur.fetchone()
    if not row: return "error"
    if row[0] != current_pw: return "wrong_password"
    try:
        cur.execute("UPDATE users SET password=%s WHERE name=%s", (new_password, name))
        db.commit()
        return "success"
    except Exception as e:
        print("change_password error:", e)
        return "error"

# -------------------- DEACTIVATE / DELETE --------------------
@app.route("/deactivate_account", methods=["POST"])
def deactivate_account():
    name = request.form.get("name", "")
    cur  = get_cursor()
    try:
        cur.execute("UPDATE users SET active=0 WHERE name=%s", (name,))
        db.commit()
    except Exception: pass
    session.clear()
    return "success"

@app.route("/delete_account", methods=["POST"])
def delete_account():
    name = request.form.get("name", "")
    cur  = get_cursor()
    try:
        cur.execute("DELETE FROM points_history WHERE name=%s", (name,))
        cur.execute("DELETE FROM users WHERE name=%s", (name,))
        db.commit()
    except Exception as e:
        print("delete_account error:", e)
    session.clear()
    return "success"

# -------------------- LOGOUT --------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login_page")

# -------------------- SETTINGS PAGE --------------------
@app.route("/settings/<name>")
def settings(name):
    return render_template("settings.html", name=name)

# -------------------- CHALLENGES --------------------
@app.route("/challenges/<name>/<role>")
def challenges(name, role):
    return render_template("challenges.html", name=name, role=role, challenges=challenges_list)

@app.route("/challenge/<name>/<role>")
def challenge_page(name, role):
    title  = request.args.get("title")
    points = request.args.get("points")
    dos, donts = [], []
    if title == "💧 Save Water":
        dos   = ["Tap closed photo 🚰","Toothbrush in hand is fine","Any bathroom/sink scene"]
        donts = ["Running tap visible","Random non-bathroom photo"]
    elif title == "♻️ Reduce Plastic":
        dos   = ["Reusable bag 🛍️","Glass or metal bottle","Plastic-free shopping"]
        donts = ["Plastic bottles or covers","Single-use plastic items"]
    elif title == "🌳 Plant a Sapling":
        dos   = ["Small seedling in soil 🌱","Hands holding/planting a plant","Pot with new seedling"]
        donts = ["Photo of a fully grown tree","Plants in a store shelf"]
    elif title == "🚯 Zero Plastic Day":
        dos   = ["Meal on real plates 🍽️","Reusable containers for food","Wooden or metal utensils"]
        donts = ["Plastic cups or cutlery","Plastic packaging visible"]
    elif title == "🏖️ Area Cleanup":
        dos   = ["Trash bags filled with litter 🗑️","Beach or park cleanup scene","Gloves while collecting waste"]
        donts = ["Indoor photos","Already clean area with no evidence"]
    elif title == "💡 Lights Off Hour":
        dos   = ["Dark room photo 🕯️","Candles used instead of lights","Only natural light visible"]
        donts = ["Fully lit room","Lights on in background"]
    elif title == "🍂 Compost Kitchen Waste":
        dos   = ["Compost bin or pile 🪣","Vegetable peels or food scraps","Worm bin counts too"]
        donts = ["Regular trash bin","Empty container with no scraps"]
    elif title == "🚴 Cycle to School":
        dos   = ["Your bicycle 🚴","Helmet or cycling gear","Bike parked at school/work"]
        donts = ["Photo of a car or motorbike","Stock/internet bike photo"]
    elif title == "🌧️ Rainwater Harvesting":
        dos   = ["Barrel or bucket placed outdoors 🪣","Rain pipes directing water","Collected water container"]
        donts = ["Indoor containers","Empty container not meant for rain"]
    elif title == "🥗 Meatless Monday":
        dos   = ["Plant-based meal 🥗","Salad, vegetables, tofu, legumes","Even a single veg dish counts"]
        donts = ["Meat, fish, or poultry visible","Empty plate"]
    return render_template("challenge.html", name=name, role=role,
                           title=title, points=points, dos=dos, donts=donts)

# -------------------- MISSION MAP --------------------
@app.route("/map/<name>")
def mission_map(name):
    cur = get_cursor()
    cur.execute("SELECT points FROM users WHERE name=%s", (name,))
    row    = cur.fetchone()
    points = row[0] if row else 0
    return render_template("map.html", name=name, level1=True,
                           level2=(points>=30), level3=(points>=70), points=points)

# -------------------- UPLOAD --------------------
@app.route("/upload", methods=["POST"])
def upload():
    name      = request.form["name"]
    challenge = request.form["challenge"]
    points    = int(request.form.get("points", 0))
    role      = request.form.get("role")
    today     = str(date.today())
    mode      = ""
    fn        = None
    filepath  = None

    cur = get_cursor()
    cur.execute("SELECT 1 FROM daily_submissions WHERE name=%s AND challenge=%s AND date=%s",
                (name, challenge, today))
    if cur.fetchone():
        return render_template("result.html", status="fail",
                               message="Already completed today ⚠️ Come back tomorrow!",
                               name=name, role=role)

    camera_data = request.form.get("camera_image_data", "")
    if camera_data and camera_data.startswith("data:image"):
        import re
        img_data = re.sub('^data:image/.+;base64,', '', camera_data)
        fn       = f"camera_{name}_{today}.jpg"
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], fn)
        with open(filepath, "wb") as f:
            f.write(base64.b64decode(img_data))
        mode = "camera"
    else:
        file = None
        if 'camera_image' in request.files and request.files['camera_image'].filename != "":
            file = request.files['camera_image']
            mode = "camera"
        elif 'upload_image' in request.files and request.files['upload_image'].filename != "":
            file = request.files['upload_image']
            mode = "upload"
        if not file:
            return render_template("result.html", status="fail",
                                   message="No file selected ❌", name=name, role=role)
        from werkzeug.utils import secure_filename
        fn       = secure_filename(file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], fn)
        file.save(filepath)

    try:
        valid, reason = verify_challenge_photo(filepath, challenge)
    except Exception as e:
        return render_template("result.html", status="fail",
                               message=f"AI Error: {str(e)}", name=name, role=role)

    if not valid:
        return render_template("result.html", status="fail",
                               message=f"❌ {reason}", name=name, role=role)

    final_points = points if mode == "camera" else points // 2
    cur.execute("INSERT INTO daily_submissions (name, challenge, date) VALUES (%s,%s,%s)",
                (name, challenge, today))
    db.commit()
    cur.execute("UPDATE users SET points = points + %s WHERE name=%s", (final_points, name))
    db.commit()
    cur.execute("INSERT INTO points_history (name, points, date) VALUES (%s,%s,%s)",
                (name, final_points, today))
    db.commit()
    try:
        cur.execute("UPDATE users SET challenges_done = COALESCE(challenges_done,0)+1 WHERE name=%s", (name,))
        db.commit()
    except Exception: pass

    return render_template("result.html", status="success",
                           message=f"✅ {reason} +{final_points} points 🎉",
                           image=fn, name=name, role=role)

# -------------------- GRAPH --------------------
@app.route("/graph/<name>")
def graph(name):
    cur = get_cursor()
    cur.execute("SELECT points, challenges_done FROM users WHERE name=%s", (name,))
    row             = cur.fetchone()
    total           = row[0] or 0
    challenges_done = row[1] or 0
    cur.execute("SELECT date, SUM(points) FROM points_history WHERE name=%s GROUP BY date ORDER BY date", (name,))
    data   = cur.fetchall()
    dates  = [str(d[0]) for d in data]
    points = [d[1] for d in data]
    best   = max(points) if points else 0
    avg    = round(total / len(points)) if points else 0
    challenge_score = min((challenges_done / 10) * 60, 60)
    points_score    = min((total / 500) * 40, 40)
    awareness       = round(challenge_score + points_score)
    if awareness >= 80:   awareness_label = "Eco Champion 🏆"
    elif awareness >= 60: awareness_label = "Green Warrior 🌿"
    elif awareness >= 40: awareness_label = "Eco Learner 🌱"
    elif awareness >= 20: awareness_label = "Getting Started 🌍"
    else:                 awareness_label = "Eco Newbie 🐣"
    return render_template("graph.html", name=name, points=points, dates=dates,
                           total=total, best=best, avg=avg,
                           challenges_done=challenges_done,
                           awareness=awareness, awareness_label=awareness_label,
                           role=session.get("role"))

# -------------------- LEADERBOARD --------------------
@app.route("/leaderboard")
def leaderboard():
    name = session.get("name")
    role = session.get("role")
    if not name:
        return redirect("/login_page")
    cur = get_cursor()
    cur.execute("SELECT name, points FROM users ORDER BY points DESC LIMIT 10")
    data = cur.fetchall()
    return render_template("leaderboard.html", data=data, name=name, role=role)

# -------------------- GAMES --------------------
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
    return render_template("puzzle.html", size=request.args.get("size", 3),
                           name=request.args.get("name"), role=request.args.get("role"))

@app.route("/eco-catch")
def eco_catch():
    return render_template("eco_catch.html", name=session.get("name"), role=session.get("role"))

@app.route("/seed-jumper")
def seed_jumper():
    return render_template("seed_jumper.html", name=session.get("name"), role=session.get("role"))

@app.route("/tree")
def tree():
    return render_template("tree.html")

@app.route("/toxic_arena")
def toxic_arena():
    return render_template("toxic_arena.html", name=session.get("name"), role=session.get("role"))

@app.route("/quiz")
def quiz():
    return render_template("quiz.html")

# -------------------- MISSIONS --------------------
@app.route("/memory_match")
def memory_match(): return render_template("memory_match.html")

@app.route("/lights_out")
def lights_out(): return render_template("lights_out.html")

@app.route("/leak_hunter")
def leak_hunter(): return render_template("leak_hunter.html")

@app.route("/canteen")
def canteen(): return render_template("canteen.html")

@app.route("/cycle-dash")
def cycle_dash(): return render_template("cycle-dash.html")

@app.route("/seed-shooter")
def seed_shooter(): return render_template("seed-shooter.html")

@app.route("/tree-doctor")
def tree_doctor(): return render_template("tree-doctor.html")

@app.route("/fire-rescue")
def fire_rescue(): return render_template("fire-rescue.html")

@app.route("/food-chain")
def food_chain(): return render_template("food-chain.html")

@app.route("/rain-puzzle")
def rain_puzzle(): return render_template("rain-puzzle.html")

@app.route("/plastic-catcher")
def plastic_catcher(): return render_template("plastic-catcher.html")

@app.route("/coral-builder")
def coral_builder(): return render_template("coral-builder.html")

@app.route("/turtle-rescue")
def turtle_rescue(): return render_template("turtle-rescue.html")

@app.route("/oil-spill")
def oil_spill(): return render_template("oil-spill.html")

@app.route("/smart-fishing")
def smart_fishing(): return render_template("smart-fishing.html")

@app.route("/ocean")
def ocean(): return render_template("ocean.html")

# -------------------- MISC --------------------
@app.route("/game1-city-builder.html")
def carbon(): return render_template("game1-city-builder.html")

@app.route("/rain_rhythm.html")
def rain_rhythm(): return render_template("rain_rhythm.html")

@app.route("/course")
def course(): return render_template("course.html")

@app.route("/pollution_page")
def pollution(): return render_template("pollution_page.html")

@app.route("/plants_page")
def plants(): return render_template("plants_page.html")

@app.route("/water_page")
def water(): return render_template("water_page.html")

@app.route("/carbon_page")
def carbons(): return render_template("carbon_page.html")

@app.route("/hatchling-run.html")
def hatchling(): return render_template("hatchling-run.html")

@app.route("/worm.html")
def worm(): return render_template("worm.html")

# -------------------- SEND PROGRESS EMAIL --------------------
@app.route("/send-progress-email/<username>")
def send_progress_email(username):
    data = get_student_progress(username)
    if not data:
        return jsonify({"status": "error", "message": "User not found"}), 404
    msg      = Message(subject="🌿 Your EcoQuest Weekly Progress Report",
                       recipients=[data["email"]])
    msg.html = render_template("email_pamphlet.html", **data)
    try:
        mail.send(msg)
        return jsonify({"status": "success", "sent_to": data["email"]}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/send-all-progress-emails")
def send_all_progress_emails():
    cur = get_cursor()
    cur.execute("SELECT name FROM users WHERE role = 'student'")
    students = [row[0] for row in cur.fetchall()]
    sent, failed = 0, 0
    for student_name in students:
        try:
            data = get_student_progress(student_name)
            if not data or not data["email"]:
                failed += 1
                continue
            msg      = Message(subject="🌿 Your EcoQuest Weekly Progress Report",
                               recipients=[data["email"]])
            msg.html = render_template("email_pamphlet.html", **data)
            mail.send(msg)
            sent += 1
        except Exception as e:
            print(f"❌ Failed for {student_name}: {e}")
            failed += 1
    return jsonify({"sent": sent, "failed": failed}), 200

@app.route("/set_session", methods=["POST"])
def set_session():
    data = request.get_json()
    name = data.get("name", "")
    role = data.get("role", "student")
    if not name:
        return jsonify({"status": "error"}), 400
    cur = get_cursor()
    cur.execute("SELECT role FROM users WHERE name=%s", (name,))
    row = cur.fetchone()
    if row:
        role = row[0]
    else:
        cur.execute(
            "INSERT INTO users (name, email, password, role, points) VALUES (%s,%s,%s,%s,%s)",
            (name, data.get("email",""), "", role, 0)
        )
        db.commit()
    session["name"] = name
    session["role"] = role
    return jsonify({"status": "ok", "role": role})

# -------------------- RUN --------------------
if __name__ == "__main__":
    app.run(debug=True)
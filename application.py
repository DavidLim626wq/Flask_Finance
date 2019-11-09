import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session

# from flask_api import status
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    prices = []
    rows = db.execute("SELECT symbol, price, SUM(shares) as shares FROM transactions WHERE userID=:user_id GROUP BY symbol HAVING shares > 0",user_id= session["user_id"])
    for row in rows:
        symbol = row["symbol"]
        cur_price = lookup(symbol)["price"]
        row["cur_price"] = cur_price
        change = round(100*(cur_price-row["price"])/row["price"],2)
        row["pc_change"] = change
    return render_template("index.html",rows=rows)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    cashAvailable = db.execute("SELECT cash FROM users WHERE id=:user_id;", user_id=session["user_id"])[0]["cash"]

    if request.method == "POST":
        shares = request.form.get("shares")
        if shares.isnumeric() == False or '.' in shares or int(shares) < 1:
            return apology("Invalid entry", 400)
        symbol = request.form.get("symbol")
        stock_data = lookup(symbol)
        if not stock_data:
            return apology("Invalid stock symbol", 400)
        price = stock_data["price"]
        c = round(int(shares)*price,2)
        if c <= cashAvailable:
            cashAvailable = round((cashAvailable - c), 2)
            flash(f"You successfully bought {shares} shares of {symbol} for {c}")
            db.execute("UPDATE users SET cash = :cash WHERE id = :user_id", user_id = session["user_id"], cash=cashAvailable)
            db.execute("INSERT INTO transactions (userID, price, symbol, shares) values (:userID, :price, :symbol, :shares);",
                userID=session["user_id"], price=stock_data["price"], symbol=symbol, shares=shares)
            return render_template("buy.html", total_price=float(price)*int(shares))
        else:
            flash("You don't have enough money.")


    return render_template("buy.html", cashAvailable=cashAvailable)


@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""
    return jsonify("TODO")


@app.route("/history")
@login_required
def history():
    user = session["user_id"]
    rows = db.execute("SELECT * FROM transactions WHERE userID=:user_id;", user_id=session["user_id"])
    return render_template("history.html",rows=rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("you must provide a username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("Enter a symbol", 400)
        s= request.form.get("symbol")
        stock_data = lookup(s)
        if not stock_data:
            flash("Stock symbol is invalid.  Try another.","failure")
            return redirect(request.url)
        else:
            return render_template("showstock.html", name=stock_data["name"], price=stock_data["price"], symbol = stock_data["symbol"])

    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form.get("username")
        pw1 = request.form.get("password")
        pw2 = request.form.get("confirmation")

        if not request.form.get("username"):
            flash("You must enter a username.","warning")
            return redirect(request.url)

        if not request.form.get("password"):
            flash("You must enter a password.","warning")
            return redirect(request.url)

        if not request.form.get("confirmation"):
            flash("You must confirm your password.","warning")
            return redirect(request.url)

        if pw1 != pw2:
            flash("Your passwords must be the same.","warning")
            return redirect(request.url)

        hash = generate_password_hash(pw1)

        result = db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)", username=username, hash=hash)
        if not result:
            flash("This username is already in use.  Choose another.","warning")
            return redirect(request.url)
        else:
            flash(f"Congratulations, {username}.  Please try logging in","success")
            return redirect("/")

        return redirect("/")

    else:
        return render_template("register.html")




@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    stocks_owned = db.execute("SELECT symbol, SUM(shares) as shares FROM transactions WHERE userID=:user_id GROUP BY symbol HAVING shares > 0",user_id= session["user_id"])
    cashAvailable =  db.execute("SELECT cash FROM users WHERE id=:user_id;", user_id=session["user_id"])[0]["cash"]

    if request.method == "POST":
        ptfo = { x['symbol']: x['shares'] for x in stocks_owned}
        if int(request.form.get('shares')) > ptfo[request.form.get('symbol')]:
            flash('You do not have that many shares')
        if not request.form.get('shares'):
            flash('Please enter the number of shares')

        if int(request.form.get('shares')) <= ptfo[request.form.get('symbol')]:
            stock_price = lookup(request.form.get('symbol'))["price"]
            shares_to_sell = int(request.form.get('shares'))
            profit = stock_price*shares_to_sell
            cashAvailable = round(cashAvailable + profit, 2)
            db.execute("UPDATE users SET cash = :cash WHERE id = :user_id", user_id = session["user_id"], cash=cashAvailable)
            db.execute("INSERT INTO transactions (userID, price, symbol, shares) values (:userID, :price, :symbol, :shares);",
                userID=session["user_id"], price=stock_price, symbol=request.form.get('symbol'), shares=-1*int(request.form.get('shares')))
            flash(f'You have successfully sold { shares_to_sell  } shares for { profit }.')

    return render_template("sell.html", stocks_owned=stocks_owned, cashAvailable=cashAvailable)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)

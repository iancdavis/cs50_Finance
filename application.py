import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
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


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # OwnedStocks is list of stock symbols currently in a users portfolio
    ownedStocks = []

    # Returns a list of dicts representing rows and collumns from the current users portfolio database table
    rows = db.execute("SELECT * FROM portfolio WHERE id = :userid", userid = session["user_id"])

    # Generate list of owned stocks symbols
    i = 0
    for row in rows:
        if rows[i]["stockSymbol"] not in ownedStocks:
            ownedStocks.append(rows[i]["stockSymbol"])
        i = i + 1

    # Values to keep track of that will be sent to the html template
    stockQuantity = {}
    stockName = {}
    stockCurrentPrice = {}
    finalList = []
    totalStockVal = {}
    combinedStockVal = 0

    for stock in ownedStocks:
        # Query the database for the quantity of all owned stocks
        temp = db.execute("SELECT SUM(quantity) FROM portfolio WHERE stockSymbol = :stock AND id = :userid", stock=stock, userid = session["user_id"])

        # unwrap the quantity of stocks returned by the db.execute function so that quantity is an int
        stockQuantity[stock] = list(temp[0].values())[0]

        # Contact IEX for current market data
        IEXvalues = lookup(stock)

        # Find current stoc price of all owned stocks
        stockCurrentPrice[stock] = IEXvalues['price']

        # Find full name of stock
        stockName[stock] = IEXvalues['name']

        # Calculate value of shares * price
        totalStockVal[stock] = stockQuantity[stock] * stockCurrentPrice[stock]

        # Add up value of stock portfolio
        combinedStockVal = combinedStockVal + totalStockVal[stock]

        # Create list of  5 tuple to be sent to jinja
        finalList.append((stock, stockName[stock], stockQuantity[stock], usd(stockCurrentPrice[stock]), usd(totalStockVal[stock])))


    # Get users account cash balance
    cashBalance = (db.execute("SELECT cash FROM users WHERE id = :userid", userid = session["user_id"]))[0]['cash']

    # Total value of stock portfolio and cash in account
    totalAccountValue = cashBalance + combinedStockVal


    return render_template("index.html", cash = usd(cashBalance), final = finalList, lenght = len(stockQuantity), totalAccountValue = usd(totalAccountValue))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "GET":
        return render_template("buy.html")

    else:
        # Validate stock symbol
        stockValueDict = lookup(request.form.get("symbol"))
        if not stockValueDict:
            return apology("Stock symbol not valid")

        # Validate number of shares
        try:
            numShares = int(request.form.get("shares"))
        except ValueError:
            return apology("Number of shares must be positive integer")

        if numShares <= 0:
            return apology("Number of shares must be positive integer")

        else:
            # Find Current price
            currentPrice = stockValueDict["price"]

            # Select chash balance of current user from user table
            rows = db.execute("SELECT * FROM users WHERE id = :userid", userid = session["user_id"])
            userBalance = rows[0]["cash"]

            # Check that user can afford the number of shares specified
            if userBalance < (currentPrice * numShares):
                return apology("Not enough funds for this transaction")

            else:

                # Add stock purchase to portfolio table in database
                db.execute("INSERT INTO portfolio (id, stockSymbol, price, quantity, datetime) VALUES (:userid, :symbol, :price, :quantity, strftime('%s','now'))",
                userid = session["user_id"], symbol = stockValueDict["symbol"], price = currentPrice, quantity = numShares)

                # Deduct cost of transaction from cash on user table
                db.execute("UPDATE users SET cash = cash - :amount WHERE id = :userid", amount = (currentPrice*numShares), userid = session["user_id"])


                #TEMP KEEPING THIS HERE. CREATE TABLE 'portfolio' ('id' INT NOT NULL, 'stockSymbol' TEXT, 'price' NUMERIC NOT NULL, 'quantity' NUMERIC NOT NULL, 'datetime' NUMERIC);


                return redirect("/")


@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""

    # Query database for list of dicts of taken usernames
    rows = db.execute("SELECT username FROM users")

    # Format list of usernames
    usernameList = []
    for row in rows:
        usernameList.append(row["username"])
    print(usernameList)

    # Get input from username field on register form
    checkUsername = request.args.get("q")

    # Check if username input is in list of taken usernames
    if checkUsername in usernameList:
        available = False
    else:
        available = True

    return jsonify(available)


@app.route("/checkPasswordRequirements", methods=["GET"])
def checkPasswordRequirements():
    """Return true if password meets security requirements(7 characters, 1 number, 1 specia character)"""

    return apology("TODO")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # Query database for users transaction history from the portfolio table
    rows = db.execute("SELECT * FROM portfolio WHERE id = :userid", userid = session["user_id"])

    # Convert the rows (a list of dicts) into a list of tuples. Needed for Jinja formatting
    finalList = []
    for row in rows:
        # Determine purchase or sale based on sign of quantity
        if row["quantity"] > 0:
            buySell = "Bought"
        else:
            buySell = "Sold"
        finalList.append((buySell, row["stockSymbol"], row["quantity"], row["price"], row["datetime"]))

    tableRows = int(len(rows))

    return render_template("history.html", final = finalList, length = tableRows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

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
    """Get stock quote."""

    if request.method == "GET":
        return render_template("quote.html")

    else:
        stockValueDict = lookup(request.form.get("symbol"))
        if not stockValueDict:
            return apology("Stock symbol not valid")
        else:
            return render_template("quoted.html", name=stockValueDict["name"], price=stockValueDict["price"], symbol=stockValueDict["symbol"])



@app.route("/register", methods=["GET", "POST"])
def register():

    """Register user"""


    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Ensure passwords match
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords do not match", 403)

        # store hashed password
        hash = generate_password_hash(request.form.get("password"))

        # Check for unique username
        result = db.execute("SELECT username FROM users WHERE username = :username", username=request.form.get("username"))
        if result:
            return apology("username taken")

        # insert new users into database
        else:
            db.execute("INSERT INTO users (username, hash) VALUES(:username, :hash)", username=request.form.get("username"), hash=hash)

        # Log user in after registering

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        session["user_id"] = rows[0]["id"]

        return redirect("/")


    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "GET":

        # OwnedStocks is list of stock symbols currently in a users portfolio
        ownedStocks = []

        # Returns a list of dicts representing rows and collumns from the current users portfolio database table
        rows = db.execute("SELECT * FROM portfolio WHERE id = :userid", userid = session["user_id"])

        # Generate list of owned stocks symbols
        i = 0
        for row in rows:
            if rows[i]["stockSymbol"] not in ownedStocks:
                ownedStocks.append(rows[i]["stockSymbol"])
            i = i + 1

        return render_template("sell.html", stocks = ownedStocks)

    else:

        sellStockSymbol = request.form.get("symbol")
        numShares = request.form.get("shares")

        # Validate stock symbol
        stockValueDict = lookup(sellStockSymbol)
        if not stockValueDict:
            return apology("Stock symbol not valid")

        # Validate number of shares is a positive integer
        try:
            numShares = int(request.form.get("shares"))
        except ValueError:
            return apology("Number of shares must be positive integer")

        if numShares <= 0:
            return apology("Number of shares must be positive integer")

        # Query database for number of shares owned for the stock user wishes to sell
        numSharesOwned = db.execute("SELECT SUM(quantity) FROM portfolio WHERE stockSymbol = :stock AND id = :userid", stock=sellStockSymbol, userid = session["user_id"])

        # Unwrap value from the list of dicts returned by the execute function
        numSharesOwned = list(numSharesOwned[0].values())[0]

        # Check that the user owns at least as many shares as they want to sell
        if numShares > numSharesOwned:
            return apology(f"You only own {numSharesOwned} shares of {sellStockSymbol}, and thus can not sell {numShares} shares.")

        # Update portfolio table in database to show sell transaction
        db.execute("INSERT INTO portfolio (id, stockSymbol, price, quantity, datetime) VALUES (:userid, :symbol, :price, :quantity, strftime('%s','now'))",
            userid = session["user_id"], symbol = sellStockSymbol, price = stockValueDict["price"], quantity = -numShares)

        # Update users cash balance in database
        db.execute("UPDATE users SET cash = cash + :amount WHERE id = :userid", amount = (stockValueDict["price"] * numShares), userid = session["user_id"])

        return redirect("/")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)

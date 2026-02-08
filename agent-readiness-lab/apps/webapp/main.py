"""Toy webapp with multi-step workflow and realistic failure modes.

Workflow: login → search → item → checkout

Failure modes:
- Wrong password
- Empty search results
- Random latency
- Intermittent 500 on checkout
- Rate limiting after many requests
"""

import asyncio
import os
import random
import time
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, Form, Request, HTTPException, Cookie, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# Configuration
RANDOM_SEED = int(os.environ.get("WEBAPP_SEED", "42"))
CHECKOUT_FAILURE_RATE = float(os.environ.get("CHECKOUT_FAILURE_RATE", "0.3"))
MAX_LATENCY_MS = int(os.environ.get("MAX_LATENCY_MS", "2000"))
RATE_LIMIT_REQUESTS = int(os.environ.get("RATE_LIMIT_REQUESTS", "100"))

# Initialize random with seed for reproducibility
rng = random.Random(RANDOM_SEED)

# In-memory state
request_counts: dict[str, int] = {}
sessions: dict[str, dict] = {}
carts: dict[str, list] = {}

# Sample products
PRODUCTS = [
    {"id": "laptop-1", "name": "Professional Laptop", "price": 999.99, "category": "electronics"},
    {"id": "laptop-2", "name": "Gaming Laptop", "price": 1499.99, "category": "electronics"},
    {"id": "phone-1", "name": "Smartphone Pro", "price": 799.99, "category": "electronics"},
    {"id": "phone-2", "name": "Budget Phone", "price": 299.99, "category": "electronics"},
    {"id": "headphones-1", "name": "Wireless Headphones", "price": 199.99, "category": "electronics"},
    {"id": "keyboard-1", "name": "Mechanical Keyboard", "price": 149.99, "category": "electronics"},
    {"id": "monitor-1", "name": "4K Monitor", "price": 449.99, "category": "electronics"},
    {"id": "mouse-1", "name": "Gaming Mouse", "price": 79.99, "category": "electronics"},
]

# Valid credentials
VALID_USERS = {
    "testuser": "password123",
    "admin": "admin123",
    "demo": "demo",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager."""
    yield
    # Cleanup
    request_counts.clear()
    sessions.clear()
    carts.clear()


app = FastAPI(title="Toy Webapp", lifespan=lifespan)

# Setup templates
import pathlib
templates_dir = pathlib.Path(__file__).parent / "templates"
templates_dir.mkdir(exist_ok=True)
templates = Jinja2Templates(directory=str(templates_dir))


async def add_random_latency():
    """Add random latency to simulate real-world conditions."""
    if MAX_LATENCY_MS > 0:
        delay = rng.randint(0, MAX_LATENCY_MS) / 1000
        await asyncio.sleep(delay)


def check_rate_limit(client_ip: str) -> bool:
    """Check if client is rate limited."""
    count = request_counts.get(client_ip, 0)
    request_counts[client_ip] = count + 1
    return count >= RATE_LIMIT_REQUESTS


def get_session(session_id: str | None) -> dict | None:
    """Get session data."""
    if session_id and session_id in sessions:
        return sessions[session_id]
    return None


def create_session(username: str) -> str:
    """Create a new session."""
    session_id = f"sess_{int(time.time())}_{rng.randint(1000, 9999)}"
    sessions[session_id] = {"username": username, "created": time.time()}
    carts[session_id] = []
    return session_id


# HTML Templates as strings (inline for simplicity)
BASE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Test Shop</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; padding: 20px; max-width: 1200px; margin: 0 auto; }}
        nav {{ background: #333; color: white; padding: 15px; margin-bottom: 20px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center; }}
        nav a {{ color: white; text-decoration: none; margin-right: 20px; }}
        nav a:hover {{ text-decoration: underline; }}
        .container {{ padding: 20px; }}
        .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 20px; margin-bottom: 15px; }}
        .btn {{ background: #007bff; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; font-size: 16px; }}
        .btn:hover {{ background: #0056b3; }}
        .btn-success {{ background: #28a745; }}
        .btn-danger {{ background: #dc3545; }}
        input, select {{ width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 4px; font-size: 16px; }}
        .error {{ color: #dc3545; background: #f8d7da; padding: 10px; border-radius: 4px; margin-bottom: 15px; }}
        .success {{ color: #155724; background: #d4edda; padding: 10px; border-radius: 4px; margin-bottom: 15px; }}
        .products {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 20px; }}
        .product {{ border: 1px solid #ddd; border-radius: 8px; padding: 15px; }}
        .price {{ font-size: 24px; color: #28a745; font-weight: bold; }}
        .cart-count {{ background: #dc3545; color: white; border-radius: 50%; padding: 2px 8px; font-size: 12px; }}
    </style>
</head>
<body>
    <nav>
        <div>
            <a href="/" data-testid="nav-home">Test Shop</a>
            <a href="/search" data-testid="nav-search">Search</a>
            <a href="/products" data-testid="nav-products">Products</a>
        </div>
        <div>
            {nav_right}
        </div>
    </nav>
    <div class="container">
        {content}
    </div>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, session_id: str | None = Cookie(None)):
    """Home page."""
    await add_random_latency()

    session = get_session(session_id)
    if session:
        nav_right = f'''
            <a href="/cart" data-testid="nav-cart">Cart <span class="cart-count">{len(carts.get(session_id, []))}</span></a>
            <a href="/logout" data-testid="nav-logout">Logout ({session["username"]})</a>
        '''
    else:
        nav_right = '<a href="/login" data-testid="nav-login">Login</a>'

    content = """
        <h1>Welcome to Test Shop</h1>
        <p>This is a toy webapp for testing AI agents.</p>
        <div style="margin-top: 20px;">
            <a href="/search" class="btn" data-testid="start-shopping">Start Shopping</a>
        </div>
    """

    return HTMLResponse(BASE_HTML.format(title="Home", nav_right=nav_right, content=content))


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str | None = None):
    """Login page."""
    await add_random_latency()

    error_html = f'<div class="error" data-testid="login-error">{error}</div>' if error else ""

    content = f"""
        <h1>Login</h1>
        {error_html}
        <form method="post" action="/login" data-testid="login-form">
            <div>
                <label for="username">Username</label>
                <input type="text" id="username" name="username" data-testid="username" required placeholder="Enter username">
            </div>
            <div>
                <label for="password">Password</label>
                <input type="password" id="password" name="password" data-testid="password" required placeholder="Enter password">
            </div>
            <button type="submit" class="btn" data-testid="login-submit">Login</button>
        </form>
        <p style="margin-top: 15px; color: #666;">Test credentials: testuser / password123</p>
    """

    return HTMLResponse(BASE_HTML.format(title="Login", nav_right='<a href="/login">Login</a>', content=content))


@app.post("/login")
async def login_submit(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
):
    """Handle login submission."""
    await add_random_latency()

    # Check credentials
    if username not in VALID_USERS or VALID_USERS[username] != password:
        return RedirectResponse(
            url="/login?error=Invalid+username+or+password",
            status_code=303
        )

    # Create session
    session_id = create_session(username)
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(key="session_id", value=session_id)
    return response


@app.get("/logout")
async def logout(response: Response):
    """Logout and clear session."""
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(key="session_id")
    return response


@app.get("/search", response_class=HTMLResponse)
async def search_page(
    request: Request,
    q: str | None = None,
    session_id: str | None = Cookie(None)
):
    """Search page."""
    await add_random_latency()

    client_ip = request.client.host if request.client else "unknown"
    if check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")

    session = get_session(session_id)
    if session:
        nav_right = f'''
            <a href="/cart" data-testid="nav-cart">Cart <span class="cart-count">{len(carts.get(session_id, []))}</span></a>
            <a href="/logout" data-testid="nav-logout">Logout</a>
        '''
    else:
        nav_right = '<a href="/login" data-testid="nav-login">Login</a>'

    # Search logic
    results = []
    if q:
        q_lower = q.lower()
        results = [p for p in PRODUCTS if q_lower in p["name"].lower() or q_lower in p["category"].lower()]

    # Build results HTML
    if q and not results:
        results_html = '<div class="card" data-testid="no-results"><p>No results found for your search. Try a different query.</p></div>'
    elif results:
        results_html = '<div class="products">'
        for p in results:
            results_html += f'''
                <div class="product card" data-testid="product-{p['id']}">
                    <h3>{p['name']}</h3>
                    <p class="price">${p['price']}</p>
                    <a href="/product/{p['id']}" class="btn" data-testid="view-{p['id']}">View Details</a>
                </div>
            '''
        results_html += '</div>'
    else:
        results_html = '<p>Enter a search term to find products.</p>'

    content = f"""
        <h1>Search Products</h1>
        <form method="get" action="/search" data-testid="search-form">
            <div style="display: flex; gap: 10px;">
                <input type="text" name="q" value="{q or ''}" placeholder="Search for products..." data-testid="search-input">
                <button type="submit" class="btn" data-testid="search-submit">Search</button>
            </div>
        </form>
        <div style="margin-top: 20px;" data-testid="search-results">
            {results_html}
        </div>
    """

    return HTMLResponse(BASE_HTML.format(title="Search", nav_right=nav_right, content=content))


@app.get("/products", response_class=HTMLResponse)
async def products_page(request: Request, session_id: str | None = Cookie(None)):
    """All products page."""
    await add_random_latency()

    session = get_session(session_id)
    if session:
        nav_right = f'''
            <a href="/cart" data-testid="nav-cart">Cart <span class="cart-count">{len(carts.get(session_id, []))}</span></a>
            <a href="/logout" data-testid="nav-logout">Logout</a>
        '''
    else:
        nav_right = '<a href="/login" data-testid="nav-login">Login</a>'

    products_html = '<div class="products">'
    for p in PRODUCTS:
        products_html += f'''
            <div class="product card" data-testid="product-{p['id']}">
                <h3>{p['name']}</h3>
                <p class="price">${p['price']}</p>
                <a href="/product/{p['id']}" class="btn" data-testid="view-{p['id']}">View Details</a>
            </div>
        '''
    products_html += '</div>'

    content = f"""
        <h1>All Products</h1>
        {products_html}
    """

    return HTMLResponse(BASE_HTML.format(title="Products", nav_right=nav_right, content=content))


@app.get("/product/{product_id}", response_class=HTMLResponse)
async def product_page(request: Request, product_id: str, session_id: str | None = Cookie(None)):
    """Single product page."""
    await add_random_latency()

    product = next((p for p in PRODUCTS if p["id"] == product_id), None)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    session = get_session(session_id)
    if session:
        nav_right = f'''
            <a href="/cart" data-testid="nav-cart">Cart <span class="cart-count">{len(carts.get(session_id, []))}</span></a>
            <a href="/logout" data-testid="nav-logout">Logout</a>
        '''
        add_to_cart_btn = f'''
            <form method="post" action="/cart/add/{product_id}" style="display: inline;">
                <button type="submit" class="btn btn-success" data-testid="add-to-cart">Add to Cart</button>
            </form>
        '''
    else:
        nav_right = '<a href="/login" data-testid="nav-login">Login</a>'
        add_to_cart_btn = '<a href="/login" class="btn" data-testid="login-to-buy">Login to Buy</a>'

    content = f"""
        <div class="card">
            <h1>{product['name']}</h1>
            <p class="price" style="font-size: 32px;">${product['price']}</p>
            <p>Category: {product['category']}</p>
            <p style="margin: 20px 0;">This is a great product for testing your AI agents. It has all the features you need.</p>
            <div style="margin-top: 20px;">
                {add_to_cart_btn}
                <a href="/products" class="btn" style="margin-left: 10px;" data-testid="back-to-products">Back to Products</a>
            </div>
        </div>
    """

    return HTMLResponse(BASE_HTML.format(title=product['name'], nav_right=nav_right, content=content))


@app.post("/cart/add/{product_id}")
async def add_to_cart(request: Request, product_id: str, session_id: str | None = Cookie(None)):
    """Add product to cart."""
    await add_random_latency()

    if not session_id or session_id not in sessions:
        return RedirectResponse(url="/login", status_code=303)

    product = next((p for p in PRODUCTS if p["id"] == product_id), None)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if session_id not in carts:
        carts[session_id] = []

    carts[session_id].append(product)
    return RedirectResponse(url="/cart", status_code=303)


@app.get("/cart", response_class=HTMLResponse)
async def cart_page(request: Request, session_id: str | None = Cookie(None)):
    """Shopping cart page."""
    await add_random_latency()

    if not session_id or session_id not in sessions:
        return RedirectResponse(url="/login", status_code=303)

    session = get_session(session_id)
    cart_items = carts.get(session_id, [])

    nav_right = f'''
        <a href="/cart" data-testid="nav-cart">Cart <span class="cart-count">{len(cart_items)}</span></a>
        <a href="/logout" data-testid="nav-logout">Logout</a>
    '''

    if not cart_items:
        cart_html = '<p data-testid="empty-cart">Your cart is empty. <a href="/products">Browse products</a></p>'
        checkout_btn = ''
    else:
        total = sum(item["price"] for item in cart_items)
        cart_html = '<div>'
        for i, item in enumerate(cart_items):
            cart_html += f'''
                <div class="card" data-testid="cart-item-{i}">
                    <h3>{item['name']}</h3>
                    <p class="price">${item['price']}</p>
                </div>
            '''
        cart_html += f'<div class="card"><h2>Total: ${total:.2f}</h2></div>'
        cart_html += '</div>'
        checkout_btn = '<a href="/checkout" class="btn btn-success" data-testid="checkout-button">Proceed to Checkout</a>'

    content = f"""
        <h1>Shopping Cart</h1>
        <div data-testid="cart-contents">
            {cart_html}
        </div>
        <div style="margin-top: 20px;">
            {checkout_btn}
        </div>
    """

    return HTMLResponse(BASE_HTML.format(title="Cart", nav_right=nav_right, content=content))


@app.get("/checkout", response_class=HTMLResponse)
async def checkout_page(request: Request, error: str | None = None, session_id: str | None = Cookie(None)):
    """Checkout page."""
    await add_random_latency()

    if not session_id or session_id not in sessions:
        return RedirectResponse(url="/login", status_code=303)

    cart_items = carts.get(session_id, [])
    if not cart_items:
        return RedirectResponse(url="/cart", status_code=303)

    total = sum(item["price"] for item in cart_items)

    nav_right = f'''
        <a href="/cart" data-testid="nav-cart">Cart <span class="cart-count">{len(cart_items)}</span></a>
        <a href="/logout" data-testid="nav-logout">Logout</a>
    '''

    error_html = f'<div class="error" data-testid="checkout-error">{error}</div>' if error else ""

    content = f"""
        <h1>Checkout</h1>
        {error_html}
        <div class="card">
            <h2>Order Summary</h2>
            <p>Items: {len(cart_items)}</p>
            <p class="price">Total: ${total:.2f}</p>
        </div>
        <form method="post" action="/checkout" data-testid="checkout-form">
            <div class="card">
                <h3>Shipping Information</h3>
                <input type="text" name="name" placeholder="Full Name" data-testid="checkout-name" required>
                <input type="email" name="email" placeholder="Email" data-testid="checkout-email" required>
                <input type="text" name="address" placeholder="Address" data-testid="checkout-address" required>
            </div>
            <div class="card">
                <h3>Payment (Test Mode)</h3>
                <input type="text" name="card" placeholder="Card Number" data-testid="checkout-card" value="4111111111111111">
            </div>
            <button type="submit" class="btn btn-success" data-testid="submit-order">Place Order (${total:.2f})</button>
        </form>
    """

    return HTMLResponse(BASE_HTML.format(title="Checkout", nav_right=nav_right, content=content))


@app.post("/checkout")
async def checkout_submit(
    request: Request,
    name: Annotated[str, Form()],
    email: Annotated[str, Form()],
    address: Annotated[str, Form()],
    card: Annotated[str, Form()],
    session_id: str | None = Cookie(None),
):
    """Handle checkout submission with intermittent failures."""
    await add_random_latency()

    if not session_id or session_id not in sessions:
        return RedirectResponse(url="/login", status_code=303)

    # Intermittent 500 error
    if rng.random() < CHECKOUT_FAILURE_RATE:
        raise HTTPException(
            status_code=500,
            detail="Something went wrong processing your order. Please try again."
        )

    # Clear cart on success
    cart_items = carts.get(session_id, [])
    total = sum(item["price"] for item in cart_items)
    carts[session_id] = []

    # Return success page
    nav_right = '<a href="/logout" data-testid="nav-logout">Logout</a>'

    content = f"""
        <div class="success card" data-testid="order-success">
            <h1>🎉 Order Confirmed!</h1>
            <p>Thank you for your order, {name}!</p>
            <p>We've sent a confirmation email to {email}.</p>
            <p>Order Total: <strong>${total:.2f}</strong></p>
            <p style="margin-top: 20px;">Your order will be shipped to: {address}</p>
            <a href="/" class="btn" style="margin-top: 20px;" data-testid="continue-shopping">Continue Shopping</a>
        </div>
    """

    return HTMLResponse(BASE_HTML.format(title="Order Confirmed", nav_right=nav_right, content=content))


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/reset")
async def reset():
    """Reset all state (for testing)."""
    request_counts.clear()
    sessions.clear()
    carts.clear()
    return {"status": "reset"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)

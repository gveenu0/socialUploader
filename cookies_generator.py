import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.firefox.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()


    # Save the cookies
    page.goto("https://studio.youtube.com")
    print("print1")
    print("print2")
    with open("cookies.json", "w") as f:
        f.write(json.dumps(context.cookies()))

    # Load the cookies
    # with open("cookies.json", "r") as f:
    #     cookies = json.loads(f.read())
    #     context.add_cookies(cookies)
    # page.goto("https://studio.youtube.com")
    # print("print1")
    # print("print2")

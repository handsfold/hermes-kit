---
name: browser-powered-social-media
description: "X, Twitter, réseaux sociaux : piloter par navigateur. Automatise les réseaux sociaux (X/Twitter, etc.) avec un navigateur headless (Playwright) et des cookies de session, sans API ni limite de débit."
when_to_use: "USER dit « poste sur X », « automatise Twitter ». Pas pour Google Agenda (voir google-agenda-chrome), ni pour un site où USER est déjà connecté dans son Chrome (voir opencli-browser)."
---

# Browser-Powered Social Media Automation (Playwright + Cookies)

## Description
This approach uses Playwright to drive a headless browser, injecting session cookies (Netscape or JSON format) to act as a logged-in user. This is significantly more robust than using official APIs, which are often restricted, paid, or prone to internal changes.

## Prerequisites
- `playwright` installed (`pip install playwright && playwright install chromium`)
- Session cookies (e.g., exported via "EditThisCookie" extension in Netscape format).

## Key Procedures

### 1. Posting to X (Twitter) without API
Standard `.fill()` often fails because X's editor (Draft.js) requires real keyboard events to enable the "Post" button.

```python
async def post_x_tweet(auth_token, ct0, text):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="...")
        await context.add_cookies([
            {'name': 'auth_token', 'value': auth_token, 'domain': '.x.com', 'path': '/'},
            {'name': 'ct0', 'value': ct0, 'domain': '.x.com', 'path': '/'}
        ])
        page = await context.new_page()
        await page.goto("https://x.com/compose/post")
        
        # Use keyboard simulation instead of .fill()
        await page.wait_for_selector('div[role="textbox"]')
        await page.focus('div[role="textbox"]')
        await page.keyboard.type(text, delay=50)
        
        await page.click('button[data-testid*="tweetButton"]')
```

### 2. Accessing Google Calendar via Cookies
Google is sensitive to cookie formatting. Filter for essential session cookies (`SID`, `HSID`, `SSID`, `APISID`, `SAPISID`) to avoid protocol errors during injection. Use `domcontentloaded` to avoid timeouts on heavy background syncs.

```python
essential_names = {'SID', 'HSID', 'SSID', 'APISID', 'SAPISID', 'OSID'}
# ... filter cookies from file ...
await context.add_cookies(filtered_cookies)
await page.goto("https://calendar.google.com/calendar/r/day", wait_until="domcontentloaded")
```

## Pitfalls
- **Strict Mode Violation**: CSS selectors like `div[data-testid="tweetTextarea_0"]` may resolve to multiple elements (modal vs. background). Always use `.first` or a more specific role-based locator.
- **Button Disabled**: If the "Post" button is grayed out, it means the site didn't detect "trusted" input. Use `page.keyboard.type()` with a small delay.
- **Protocal Error**: Large cookie files (3000+ lines) often contain invalid date formats. Always filter for specific domains and session-critical keys.

# automation_service.py
from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
from flask_cors import CORS
import tempfile
import base64
import os

app = Flask(__name__)
CORS(app)

@app.route("/autofill", methods=["POST"])
def autofill():
    """
    Expects JSON:
    {
      "url": "https://job.apply.url/..",
      "fields": { "name_selector": "Vishal", "email_selector": "v@example.com", ... },
      "resume_base64": "<base64 file bytes>",   # optional
      "resume_filename": "vishal_resume.pdf",
      "cover_letter": "Hello..."
    }
    Note: the 'fields' keys should be CSS selectors mapping to values, e.g. { "input[name='name']": "Vishal" }
    """
    data = request.get_json(force=True)
    url = data.get("url")
    fields = data.get("fields", {})
    resume_b64 = data.get("resume_base64")
    resume_filename = data.get("resume_filename", "resume.pdf")
    cover_letter = data.get("cover_letter", "")

    if not url:
        return jsonify({"error": "missing url"}), 400

    # Save resume to a temp file if provided
    resume_path = None
    if resume_b64:
        b = base64.b64decode(resume_b64)
        fd, resume_path = tempfile.mkstemp(suffix=os.path.splitext(resume_filename)[1])
        with os.fdopen(fd, "wb") as f:
            f.write(b)

    # Launch the browser and autofill
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)  # show browser so user can review
            page = browser.new_page()
            page.goto(url, timeout=60000)

            # Fill fields by CSS selector
            for selector, value in fields.items():
                try:
                    # If selector points to file input and we have resume, set files
                    if "file" in selector.lower() or selector.endswith("input[type='file']"):
                        if resume_path:
                            page.set_input_files(selector, resume_path)
                    else:
                        # Some inputs may be textareas
                        if page.query_selector(selector) is not None:
                            page.fill(selector, value)
                        else:
                            # Try evaluate to set value
                            page.evaluate(f"document.querySelector('{selector}') && (document.querySelector('{selector}').value = `{value}`)")
                except Exception as e:
                    print("Warning filling", selector, e)

            # Try put cover letter in first large textarea if selector not provided
            if cover_letter:
                # If page has a common textarea with name/placeholder containing 'cover', try to fill it
                try:
                    filled = False
                    for sel in ["textarea[name*=cover_letter]", "textarea[name*=cover]", "textarea[placeholder*=cover]"]:
                        el = page.query_selector(sel)
                        if el:
                            el.fill(cover_letter)
                            filled = True
                            break
                    if not filled:
                        # fallback: first textarea
                        t = page.query_selector("textarea")
                        if t:
                            t.fill(cover_letter)
                except Exception as e:
                    print("Warning filling cover letter", e)

            # Pause for manual review and submission
            print("Autofill complete. The browser is paused - review the form and submit manually.")
            page.pause()   # playwright will wait until user resumes (press resume in inspector)
            browser.close()

        # cleanup
        if resume_path and os.path.exists(resume_path):
            os.remove(resume_path)

        return jsonify({"status": "autofill_started"}), 200
    except Exception as ex:
        if resume_path and os.path.exists(resume_path):
            os.remove(resume_path)
        return jsonify({"error": str(ex)}), 500

if __name__ == "__main__":
    # Ensure Playwright browsers are installed:
    # pip install playwright
    # playwright install
    app.run(host="0.0.0.0", port=8100)

# Installing DoNotStress

These steps are for Windows, in the VS Code terminal, run from this folder (the one with `main.py`). You need Python 3.12, the version the Dockerfile uses.

## 1. Add the page files

This package does not include the `templates/` and `static/` folders. Copy both, unchanged, from the Part 1 project into this folder, next to `main.py`. Without them the app starts but cannot show its pages.

## 2. Install the packages

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If `python` is not found, use `py -m venv .venv` for the first command.

## 3. Add your Gemini API key

```powershell
Copy-Item .env.example .env
notepad .env
```

Put your key after `GEMINI_API_KEY=` with no quotes, then save. Keys come from Google AI Studio (aistudio.google.com). Never commit `.env`.

## 4. Run the app

```powershell
.\.venv\Scripts\python.exe main.py
```

Open http://127.0.0.1:5000. The admin sign-in details are in `README.md`, under "Saved check-ins and detailed results". Stop the app with Ctrl+C.

## 5. Run the tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The tests use sample AI replies, so they need no API key and no internet connection.

## Docker (optional)

```powershell
docker build -t donotstress .
docker run --rm -p 5000:5000 --env-file .env -v donotstress-data:/app/data donotstress
docker run --rm donotstress python -m unittest discover -s tests -v
```

The second command runs the app and keeps saved check-ins in a Docker volume called `donotstress-data`. The third runs the tests inside the container.

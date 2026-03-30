# Troubleshooting Installation Issues

## Problem: "Could not install packages due to an OSError"

This happens when pip tries to overwrite an executable file that's locked or in use.

### Solution 1: Use User Installation (Recommended)

Run this command manually:
```bash
pip install --user beautifulsoup4 tqdm
```

This installs packages to your user directory, avoiding permission issues.

### Solution 2: Close Python Processes

1. Close all Python windows/IDEs
2. Open Task Manager (Ctrl+Shift+Esc)
3. End any Python processes
4. Try installing again:
```bash
pip install beautifulsoup4 tqdm
```

### Solution 3: Run as Administrator

1. Right-click Command Prompt
2. Select "Run as Administrator"
3. Navigate to the scraper folder
4. Run: `pip install beautifulsoup4 tqdm`

### Solution 4: Install Packages Individually

If bulk installation fails, install one at a time:
```bash
pip install --user beautifulsoup4
pip install --user tqdm
```

### Solution 5: Use Virtual Environment (Best Practice)

Create a virtual environment to avoid conflicts:
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## After Installation

Verify installation:
```bash
python -c "import bs4, tqdm; print('OK')"
```

If this works, you can run the scraper!

## Still Having Issues?

Check if packages are already installed:
```bash
pip list | findstr "beautifulsoup4 tqdm"
```

If they're listed, the import test should work. You might just need to restart your terminal/IDE.

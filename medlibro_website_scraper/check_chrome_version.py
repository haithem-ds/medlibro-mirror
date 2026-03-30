"""
Check Chrome version and help configure ChromeDriver.
"""
import subprocess
import re
import sys

def get_chrome_version():
    """Get installed Chrome version."""
    try:
        # Try Windows registry method
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
        version = winreg.QueryValueEx(key, "version")[0]
        winreg.CloseKey(key)
        return version
    except:
        pass
    
    try:
        # Try command line method
        result = subprocess.run(
            ['reg', 'query', 'HKEY_CURRENT_USER\\Software\\Google\\Chrome\\BLBeacon', '/v', 'version'],
            capture_output=True,
            text=True
        )
        match = re.search(r'version\s+REG_SZ\s+(\d+\.\d+\.\d+\.\d+)', result.stdout)
        if match:
            return match.group(1)
    except:
        pass
    
    return None

def main():
    print("=" * 70)
    print("Chrome Version Checker")
    print("=" * 70)
    print()
    
    version = get_chrome_version()
    if version:
        print(f"[OK] Chrome version found: {version}")
        major_version = version.split('.')[0]
        print(f"[INFO] Major version: {major_version}")
        print()
        print("To use this version, set environment variable:")
        print(f'  set CHROME_VERSION_MAIN={major_version}')
        print()
        print("Or in PowerShell:")
        print(f'  $env:CHROME_VERSION_MAIN="{major_version}"')
        print()
        print("Then run the scraper again.")
    else:
        print("[WARNING] Could not detect Chrome version automatically.")
        print()
        print("Please check your Chrome version manually:")
        print("1. Open Chrome")
        print("2. Go to: chrome://version/")
        print("3. Look for the version number (e.g., 120.0.6099.109)")
        print("4. The major version is the first number (e.g., 120)")
        print()
        print("Then set environment variable:")
        print('  set CHROME_VERSION_MAIN=120')
        print()
        print("Or edit config.py and change CHROME_VERSION_MAIN value.")
    
    print("=" * 70)

if __name__ == "__main__":
    main()

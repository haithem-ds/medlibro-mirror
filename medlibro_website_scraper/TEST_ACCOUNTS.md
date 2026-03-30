# Testing the MedLibro mirror

## Automatic test user (no login)

When you open **http://localhost:8080**, the mirror automatically logs you in as a **validated premium** user so you can use all features:

- **Email:** user@example.com (display only)
- **State:** Email validated ✓, Subscription: premium
- **Access:** Sessions, Révision, Examen, Memorix, Playlists are **unlocked** (no padlocks)

No password needed — just open the site. If you still see the "Validation d'e-mail" form or locked items:

1. **Rebuild the mirror** so the updated mock user is injected:
   ```bat
   python build_mirror.py
   ```
2. **Restart the API server** (port 5000) so it returns the validated user.
3. **Hard refresh** the page (Ctrl+Shift+R) or clear the site data for localhost:8080, then reopen.

## Logging in with a specific email/password

The mirror uses a **local mock API** (api_server.py). Login always returns the same validated premium user, regardless of the credentials you type. So you can:

- Click **Se déconnecter**, then **SE CONNECTER**, and enter any email/password (e.g. test@test.com / 123) — you will still get the same unlocked "Local User" account.

## Using the real MedLibro site (not the mirror)

To test with a **real** registered account on the live site (https://medlibro.co), use the credentials in `config.py`:

- **Email:** (see `config.py` → `EMAIL`)
- **Password:** (see `config.py` → `PASSWORD`)

Those are used by `save_real_pages.py` to scrape the site; they are not used by the local mirror’s mock API.

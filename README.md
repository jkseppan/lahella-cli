# Lahella.fi Course Automation

Automate creating course listings on lahella.fi using their API.

## Setup

```bash
# Install dependencies
uv sync
uv run playwright install chromium

# Create auth.toml from example
cp auth.toml.example auth.toml
# Edit auth.toml with your email and password

# Run login to get fresh cookies
uv run login.py
```

## Configuration Structure

The script uses a layered configuration system:

1. **`auth.toml`** (gitignored) - Your authentication credentials
2. **`defaults.toml`** - Shared settings across all courses
3. **`course-name.toml`** - Course-specific details

Settings are merged with this precedence: **course file > defaults.toml > auth.toml**

### Authentication

The automation uses automated login via `login.py`:

1. Add your credentials to `auth.toml`:
   ```toml
   [auth]
   email = "your@email.com"
   password = "yourpassword"
   group_id = "your_group_id"
   ```

2. Run `uv run login.py` to authenticate and extract cookies

The script will automatically:
- Log in to hallinta.lahella.fi
- Extract auth tokens
- Save them to `auth.toml`

The `create_course.py` script has automatic token refresh built-in. If your auth token expires but the refresh token is still valid, it will automatically refresh without requiring a new login.

## Usage

```bash
# First, log in to get fresh cookies (only needed once or when cookies expire)
uv run login.py

# Preview what would be sent (dry run)
uv run create_course.py taiji-lauttasaari.toml --dry-run

# Actually create the listing
uv run create_course.py taiji-lauttasaari.toml

# Create multiple courses (token auto-refreshes if needed)
uv run create_course.py taiji-lauttasaari.toml
uv run create_course.py taiji-kallio.toml
```

## File Structure

```
.
├── auth.toml              # Your credentials (gitignored)
├── auth.toml.example      # Template for auth.toml
├── defaults.toml          # Shared course defaults
├── taiji-lauttasaari.toml # Course-specific config
├── taiji-kallio.toml      # Another course config
├── taijikuva.jpg          # Course image
├── login.py               # Automated login script
├── auth_helper.py         # Shared auth/token refresh module
└── create_course.py       # Course creation script
```

## Creating a New Course

1. Copy an existing course file (e.g., `taiji-lauttasaari.toml`)
2. Modify the course-specific fields:
   - `course.title`
   - `course.summary`
   - `location.address`
   - `location.summary`
   - `schedule.start_date`, `end_date`, `weekly`
   - `registration.url`
3. Run: `uv run create_course.py your-course.toml`

Most settings (categories, demographics, contacts) are inherited from `defaults.toml`, so you only need to specify what's different.

## Configuration Reference

See the example files for all available options:
- `auth.toml.example` - Auth settings
- `defaults.toml` - Shared defaults
- `taiji-lauttasaari.toml` - Full course example

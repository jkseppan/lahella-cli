# Lahella.fi Course Automation

Automate creating course listings on lahella.fi using their API.

## Setup

```bash
# Install dependencies
uv pip install httpx

# Create auth.toml from example
cp auth.toml.example auth.toml
# Edit auth.toml with your cookie from browser DevTools
```

## Configuration Structure

The script uses a layered configuration system:

1. **`auth.toml`** (gitignored) - Your authentication credentials
2. **`defaults.toml`** - Shared settings across all courses
3. **`course-name.toml`** - Course-specific details

Settings are merged with this precedence: **course file > defaults.toml > auth.toml**

### Getting Your Auth Cookie

1. Open https://hallinta.lahella.fi in your browser
2. Log in
3. Open DevTools (F12) → Application → Cookies → hallinta.lahella.fi
4. Copy the `AUTH_TOKEN_*` cookie value
5. Put it in `auth.toml`

## Usage

```bash
# Preview what would be sent (dry run)
python create_course.py taiji-lauttasaari.toml --dry-run

# Actually create the listing
python create_course.py taiji-lauttasaari.toml

# Create multiple courses
python create_course.py taiji-lauttasaari.toml
python create_course.py taiji-kallio.toml
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
└── create_course.py       # The automation script
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
3. Run: `python create_course.py your-course.toml`

Most settings (categories, demographics, contacts) are inherited from `defaults.toml`, so you only need to specify what's different.

## Configuration Reference

See the example files for all available options:
- `auth.toml.example` - Auth settings
- `defaults.toml` - Shared defaults
- `taiji-lauttasaari.toml` - Full course example

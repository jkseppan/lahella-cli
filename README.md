[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)
[![Vibe-coded](https://img.shields.io/badge/Vibe-coded-c15f3c?logo=Claude&labelColor=f4f3ee)](https://x.com/i/trending/2006300642797625572)

# lahella-cli: Lähellä.fi Activity Automation

Automate creating and updating activity listings on [Lähellä.fi](https://lahella.fi)
using YAML configuration files.

## What is Lähellä.fi?

Finnish authorities, in their great but subinfinite wisdom,
created the [*Palvelutietovaranto (PTV)*](https://kehittajille.suomi.fi/services/servicecatalogue),
a glorious incarnation of the Semantic Web for Finnish services.
State and council services have to be listed in it by law, but it is also open to
private entities such as sports associations and hobby clubs.
The upside of listing your services there is that it will show up in all sorts of official searches.
For example, I volunteer with a [tai chi association](https://taichichuan.fi)
and have found that it is great for developing my sense of balance, 
and perhaps one day somewhere a healthcare worker is looking for a recommendation
for exercises for a patient who has balance problems, and being legible in PTV
would help us be findable at that moment.

Look, it's more European than Google!
Also, at Google's rate of enshittification even PTV may overtake
it in usefulness before the heat death of the universe.

In any case, implementing PTV is an [exercise in bureaucracy](https://kehittajille.suomi.fi/services/servicecatalogue/api-and-architecture-reform)
so spectacularly byzantine that it has to be seen to be
[believed](https://kehittajille.suomi.fi/services/servicecatalogue/organising-work/duties-of-the-fsc-main-user).
Thus [Lähellä.fi](https://www.lahella.fi/en-GB): a way for the small-time sports and hobby clubs to list their services.
Lähellä.fi synchronises with PTV automatically and reduces the complexity to perhaps one tenth.

Alas, even one deci-PTV of complexity is still way too clunky for us mere mortals.
We have several tai chi classes and exercise groups, and keeping the listings
up to date is a chore that you have to do through a next.js interface that is...
let's say "not bad for a government project".
Thus this automation tool.

## Who is this for?

You need to have a [lähellä.fi account](https://www.lahella.fi/forms/create-group) and some computing experience.
I mean, you have to be able to deal with YAML files and appreciate why it's a better experience than clicky-clicky web forms.

It's probably worthwhile if you want to maintain at least five different activity entries
(anything less and you're complicating your life for very little gains).
What you get:

- **Batch Management** - Create or update all activities at once instead of filling forms one-by-one
- **Version Control** - Track your activity listings in Git, see what changed over time, and collaborate with teammates
- **Automation** - Eliminate repetitive clicking through the web interface
- **Consistency** - Define templates for common patterns (locations, schedules, pricing) and reuse them across activities

## Caveats

This is version 0.1, mainly vibe-coded, it worked for me once!
Please take backups of your lähellä.fi data before using this alpha software.

## Installation

1. **Install uv** - I mean, everyone has done this in 2025, but see instructions at <https://docs.astral.sh/uv/getting-started/installation/>

2. **Clone or download this repository:**
   ```bash
   git clone https://github.com/jkseppan/lahella-cli.git
   cd lahella-cli
   ```

3. **Install dependencies:**
   ```bash
   uv sync
   ```

## Quick Start

### 1. Set Up Authentication

Create an `auth.yaml` file with your Lähellä.fi credentials:

```yaml
auth:
  email: your.email@example.com
  password: your_password
  group_id: "your_organization_group_id"
  cookies: ""
```

**Finding your group ID:**
1. Log in to [hallinta.lahella.fi](https://hallinta.lahella.fi)
2. Go to <https://hallinta.lahella.fi/en-GB/groups>

**Run the login script** to authenticate and save session tokens:
```bash
uv run lahella-login
```

This uses automated browser login (via Playwright) to obtain authentication tokens and saves them to `auth.yaml`.
If that fails (because of Captcha or something) try getting the auth cookies by hand from a browser.

### 2. Create Your First Activity

Go clickety-click in the interface to create an activity.
You'll see what the fields mean and what they want you to do with them.

### 3. Download the activity

```bash
uv run lahella-download --yaml --output events.yaml
```

**Understanding the YAML format:**
- Text fields like `summary` and `description` use HTML formatting with `<p dir="ltr">` for paragraphs
  (lest you forget which way the three supported languages Finnish, Swedish and English are written)
  - Perhaps write a fairly complete text in the web interface first,
    then edit the downloaded YAML later
- `weekday` uses numbers: 1=Monday, 7=Sunday
- Dates are in YYYY-MM-DD format


### 4. Create more activities

Edit the YAML file and add another activity!
Then try creating it remotely:

```bash
uv run lahella-create
```

The script will show a list of locally defined activities
and tell you how to pick the one to create.

### 5. Download again

```bash
uv run lahella-download --yaml --output downloaded_events.yaml
```

Compare to your original file.
There should be `_id` and `_status` fields for your new event.
The script will not automatically publish the event; for now,
you'll have to do it via the web interface.
There are likely some other changes, such as coordinates added to addresses.
If the file looks good, move it in place:

```bash
mv downloaded_events.yaml events.yaml
```

### 6. Edit and Sync

Edit the activities, see how your local and remote versions differ:

```bash
uv run lahella-sync --all
```

and if you want to commit the changes to the remote:

```bash
uv run lahella-sync --all --apply
```


### 7. Set up YAML anchors and aliases

The point of this whole exercise is to reduce duplicated effort,
and the reason to tolerate YAML is to be able to use its features.
To wit, anchors and aliases:

```yaml
defaults:  # define data here for use in multiple places
  location: &common_location
    type: place
    accessibility: [ac_unknow]
    regions: [city/FI/Helsinki]
    address:
      city: Helsinki
      state: Uusimaa
      country: FI

events:  # the API calls will be made based on this part
  - title:
      fi: Morning Class
    location:
      <<: *common_location  # add or override the rest of the attributes below:
      address:
        street: Street A 1
        postal_code: "00100"
    # ... rest of activity ...

  - title:
      fi: Evening Class
    location:
      <<: *common_location
      address:
        street: Street B 2
        postal_code: "00200"
    # ... rest of activity ...
```

The `<<: *common_location` syntax includes all fields from the template, and you only need to override what's different.

Unless you **really** love YAML, just use an LLM to find the shared similarities and
generate anchors in the `defaults` section.

Now we should remember that the YAML is all generated client-side,
so downloading a fresh copy of `events.yaml`
will cheerfully overwrite all your neat anchor-based deduplication.
The solution is to not overwrite it but write a separate file
and let the download script reference the original.
(It automatically looks for `events.yaml` but you can use `-t something_else.yaml`.)
It should detect when to use the `<<: *` operator.

## Authentication Management

### Token Refresh

The tool automatically refreshes authentication tokens when they expire. If you see "Unauthorized" errors:

```bash
uv run lahella-auth
```

This attempts to refresh your tokens. If refresh fails, run `uv run lahella-login` again to re-authenticate.


## Configuration Reference

This is all reverse-engineered from the API (because who provides documentation?), so caveat emptor and bring your own debugger.

### Activity Fields

| Field | Required | Description |
|-------|----------|-------------|
| `title` | Yes | Activity name (multilingual: `{fi: "...", sv: "...", en: "..."}`) |
| `summary` | Yes | Brief description in HTML format |
| `description` | Yes | Detailed description in HTML format |
| `type` | Yes | Activity type: `hobby`, `support`, or `voluntary` |
| `required_locales` | Yes | Languages provided (e.g., `[fi, sv, en]`) |
| `categories` | Yes | Themes, formats, and locales (see below) |
| `demographics` | No | Target age groups and gender |
| `pricing` | Yes | `type`: `free` or `paid`, optional `info` text |
| `location` | Yes | Where the activity happens |
| `schedule` | Yes | When the activity happens |
| `registration` | No | How to register |
| `contacts` | No | Contact information |
| `image` | No | Photo for the activity listing |

### Valid Category Values

**Types**:

- `hobby` - Hobbies & leisure
- `support` - Support & assistance
- `voluntary` - Voluntary work


**Themes** (for hobby type):
- `ht_digi_teknologia` - Tech & gaming
- `ht_hyvinvointi` - Wellness & lifestyle
- `ht_kansainvalisyys` - International activities
- `ht_kulttuuri` - Culture & arts
- `ht_kadentaidot` - Crafts & handicrafts
- `ht_luonto` - Nature & animals
- `ht_maanpuolustus` - National defense
- `ht_pelastustoiminta` - Fire & rescue services
- `ht_urheilu` - Sports & exercise
- `ht_uskonnot` - Religion & spirituality
- `ht_vaikuttaminen` - Advocacy, democracy & human rights

**Formats** (for hobby type):
- `hm_esitykset` - Performances & shows
- `hm_harrastukset` - Hobbies & activities
- `hm_kohtaamispaikka` - Meeting places & community spaces
- `hm_kylatoiminta` - Village & neighborhood activities
- `hm_leirit` - Camps, trips & excursions
- `hm_nayttelyt` - Exhibitions
- `hm_oleskelu` - Recreation & leisure
- `hm_oppaat` - Guides & publications
- `hm_ryhmat` - Groups & clubs
- `hm_tilaisuudet` - Events & lectures

**Demographics:**
- Age groups: `ageGroup/range:18-29`, `ageGroup/range:30-64`, etc.
  - To specify "appropriate for everyone" I think you have to do 18-29, 30-64, 65-99 separately
    (because apparently "all ages" wasn't an option in the grand PTV design)
- Gender: `gender/gender` (any), `gender/male`, `gender/female`

**Languages:**
- `fi-FI` - Finnish
- `sv` - Swedish
- `en` - English
- `ar` - Arabic
- `ku` - Kurdish
- `so-SO` - Somali
- `uk-UA` - Ukrainian
- `ru-RU` - Russian
- `et-EE` - Estonian
- `fisl` - Finnish Sign Language

**Accessibility:**
- `ac_unknow` - Organiser does not guarantee accessibility
- `ac_wheelchair` - Wheelchair accessible
- `ac_rollator` - Rollator accessible
- `ac_inductionloop` - Induction loop available
- `ac_itoilet` - Accessible toilet available
- `ac_parking` - Parking available

**Channel type:**
- `place` - Physical location
- `online` - Online
- `phone` - By phone
- `hybrid` - Hybrid (both physical and online)

**Geography:**
Format: `city/COUNTRY/City`, `state/COUNTRY/State` where COUNTRY is FI
- `city/FI/Helsinki`
- `city/FI/Espoo`
- `state/FI/Uusimaa`
- `state/FI/Etelä-Savo`
- etc


### Schedule Format

**Weekly recurring:**
```yaml
schedule:
  start_date: '2026-01-11'
  end_date: '2026-05-24'
  timezone: Europe/Helsinki
  weekly:
    - weekday: 2      # Tuesday
      start_time: "18:00"
      end_time: "19:30"
    - weekday: 5      # Friday
      start_time: "18:00"
      end_time: "19:30"
```

Weekday numbers are 1-based where 1 is Monday.

There are recurrence periods like `P1W` for weekly,
and recurrence gaps like `P2W`... it's pretty confusing ,
but just create it on the server first and then copy the working configuration.

## Acknowledgments

Claude Code wrote most of the code.
Not without quite a bit of prompting and false starts, mind you.

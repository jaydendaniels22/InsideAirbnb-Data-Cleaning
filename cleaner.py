"""
clean.py  -  Raw Inside Airbnb Amsterdam CSVs  ->  clean SQLite database

How to run:
    1. Put calendar.csv, listings.csv and reviews.csv in a folder called "raw"
    2. python clean.py

What it creates (all next to this script):
    airbnb_amsterdam.db           the clean data (tables: listings, calendar, reviews)
    cleaning_log.md               every issue found, what I decided, rows affected
    data_quality_before_after.md  before/after quality table

The script never changes the raw files, so you can run it as often as you like.
"""

# import libraries needed
import os
import re
import html
import sqlite3

import numpy as np
import pandas as pd

# settings
RAW_FOLDER = "raw"
DB_FILE = "airbnb_amsterdam.db"
LOG_FILE = "cleaning_log.md"
QUALITY_FILE = "data_quality_before_after.md"

PRICE_OUTLIER_LIMIT = 3000       # euros per night. Price above this is flagged as an outlier
LONG_STAY_NIGHTS = 28            # Airbnb calls 28+ nights a "monthly" stay
MAX_REVIEWS_PER_MONTH = 31       # more than around 1 review a day is suspicious
MAX_NIGHTS_LIMIT = 3650          # anything above 10 years is a "no limit" placeholder

# HTML tags: a full tag like <br /> or <b>,
# and a tag that was cut off at the very end of the text
# the source truncates long descriptions.
# a tag must start with a letter, so '<3' (a heart) isn't treated as a tag.
TAG_PATTERN = r"</?[a-zA-Z][^>]*>"
CUT_TAG_PATTERN = r"</?[a-zA-Z]{1,6}\s*/?$"
HAS_TAG_PATTERN = r"</?[a-zA-Z][^>]*>|</?[a-zA-Z]{1,6}\s*/?$"

# Columns that are 100% empty in this scrape, found while profiling.
# "bathrooms" is empty too, but I rebuild it from bathrooms_text, so it stays.
EMPTY_COLUMNS = [
    "neighborhood_overview", "host_since", "host_response_time",
    "host_response_rate", "host_acceptance_rate", "host_thumbnail_url",
    "host_neighbourhood", "host_total_listings_count", "host_verifications",
    "neighbourhood", "neighbourhood_group_cleansed", "calendar_updated",
    "instant_bookable",
]
# Columns that hold the same value in every row, or are a raw JSON blob
USELESS_COLUMNS = ["scrape_id", "calendar_last_scraped", "source", "price_quote_raw"]

# Columns with 't' / 'f' text that I turn into 1 / 0
TRUE_FALSE_COLUMNS = [
    "host_is_superhost", "host_has_profile_pic",
    "host_identity_verified", "has_availability",
]
# Whole-number columns that pandas loaded as decimals because of missing values
WHOLE_NUMBER_COLUMNS = [
    "bedrooms", "beds", "minimum_nights", "maximum_nights",
    "minimum_maximum_nights", "maximum_maximum_nights",
    "minimum_minimum_nights", "maximum_minimum_nights",
]

# The log is a simple list. Each call to add_log() adds one row.
log = []


def add_log(file, issue, decision, rows):
    log.append({"file": file, "issue": issue, "decision": decision, "rows": rows})


# Small helper functions for simplification
def clean_text(series):
    #Remove HTML tags, odd spaces and line breaks from a text column.
    s = series.str.replace(r"<br\s*/?>", " ", regex=True)   # <br>, <br/>, <br />
    s = s.str.replace(TAG_PATTERN, "", regex=True)          # any other HTML tag
    s = s.str.replace(CUT_TAG_PATTERN, "", regex=True)      # a tag cut off at the very end
    # turn codes like &amp; back into normal characters
    s = s.apply(lambda x: html.unescape(x) if isinstance(x, str) and "&" in x else x)
    s = s.str.replace(r"\s+", " ", regex=True)              # many spaces/new lines -> one space
    s = s.str.strip()
    return s


def count_changed(before, after):
    #How many rows are different between two text columns?
    return int((before.fillna("") != after.fillna("")).sum())


def bathrooms_from_text(text):
    #'1.5 shared baths' -> 1.5,  'Half-bath' -> 0.5, missing -> NaN
    if pd.isna(text):
        return np.nan
    text = text.lower()
    if "half" in text:
        return 0.5
    number = re.search(r"\d+(\.\d+)?", text)
    if number:
        return float(number.group())
    return np.nan


def pct(number, total):
    return round(number / total * 100, 1)

def yes_no(condition):
    #True -> "Yes", False -> "No"
    return np.where(condition, "Yes", "No")


# Data quality checks. The exact same checks run on the raw and on the clean data,
# so that the before/after table is a fair comparison.
def listings_checks(df):
    id_col = "listing_id" if "listing_id" in df.columns else "id"
    checks = {}
    checks["Rows"] = len(df)
    checks["Columns"] = df.shape[1]
    checks["Columns that are 100% empty"] = int(df.isna().all().sum())
    checks["Duplicate listing ids"] = int(df[id_col].duplicated().sum())
    checks["Rows with a numeric price"] = int(pd.to_numeric(df["price"], errors="coerce").notna().sum())
    checks["Rows with bathrooms filled in"] = int(df["bathrooms"].notna().sum())
    checks["Columns stored as 't'/'f' text"] = int(sum(df[c].isin(["t", "f"]).any() for c in df.columns))
    checks["maximum_nights above 3650 (placeholder)"] = int((df["maximum_nights"] > MAX_NIGHTS_LIMIT).sum())
    checks["Placeholder license numbers"] = int(df["license"].str.contains("ABCD 1234", na=False).sum())
    checks["Descriptions containing HTML tags"] = int(df["description"].str.contains(HAS_TAG_PATTERN, na=False).sum())
    messy_name = df["name"].str.contains(r"^\s|\s$|\s\s", na=False)
    messy_host = df["host_name"].str.contains(r"^\s|\s$|\s\s", na=False)
    checks["Names / host names with extra spaces"] = int((messy_name | messy_host).sum())
    checks["host_location spelled 'The Netherlands'"] = int(df["host_location"].str.contains("The Netherlands", na=False).sum())
    if "flag_price_outlier" in df.columns:
        checks["Rows flagged as extreme price"] = int((df["flag_price_outlier"] == "Yes").sum())
    else:
        checks["Rows flagged as extreme price"] = 0
    return checks


def calendar_checks(df, listing_ids):
    checks = {}
    checks["Rows"] = len(df)
    checks["Duplicate (listing, date) rows"] = int(df.duplicated(["listing_id", "date"]).sum())
    checks["Rows where available is 't'/'f' text"] = int(df["available"].isin(["t", "f"]).sum())
    checks["maximum_nights above 3650 (placeholder)"] = int((df["maximum_nights"] > MAX_NIGHTS_LIMIT).sum())
    checks["Rows whose listing is not in listings"] = int((~df["listing_id"].isin(listing_ids)).sum())
    days_per_listing = df.groupby("listing_id").size()
    checks["Listings without exactly 365 days"] = int((days_per_listing != 365).sum())
    return checks


def reviews_checks(df, listing_ids):
    id_col = "review_id" if "review_id" in df.columns else "id"
    checks = {}
    checks["Rows"] = len(df)
    checks["Same review repeated (same listing, reviewer, date, text)"] = int(
        df.duplicated(["listing_id", "reviewer_id", "date", "comments"]).sum())
    checks["Rows whose review id appears on more than one listing"] = int(df[id_col].duplicated(keep=False).sum())
    if "is_review_copy" in df.columns:
        checks["Rows flagged as an extra copy of a review (is_review_copy = Yes)"] = int(
            (df["is_review_copy"] == "Yes").sum())
    else:
        checks["Rows flagged as an extra copy of a review (is_review_copy = Yes)"] = 0
    checks["Comments containing HTML tags"] = int(df["comments"].str.contains(HAS_TAG_PATTERN, na=False).sum())
    checks["Comments with leading/trailing/double spaces"] = int(df["comments"].str.contains(r"^\s|\s$|\s\s", na=False).sum())
    checks["Comments that are only '.' or '-'"] = int(df["comments"].str.strip().isin([".", "-", "..", "..."]).sum())
    checks["Missing comments"] = int(df["comments"].isna().sum())
    checks["Rows whose listing is not in listings"] = int((~df["listing_id"].isin(listing_ids)).sum())
    return checks


# Clean calender
def clean_calendar(df, listing_ids):
    df = df.copy()
    name = "calendar.csv"

    # 1. Dates must be real dates
    parsed = pd.to_datetime(df["date"], errors="coerce")
    bad_dates = int(parsed.isna().sum())
    df = df[parsed.notna()]
    add_log(name, "Dates that are not valid dates", "Checked. Would drop them (none found)", bad_dates)

    # 2. Duplicate rows for the same listing and day
    dups = int(df.duplicated(["listing_id", "date"]).sum())
    df = df.drop_duplicates(["listing_id", "date"])
    add_log(name, "Same listing and date appears twice", "Checked. Would keep the first (none found)", dups)

    # 3. Rows for listings that do not exist in listings.csv
    orphans = int((~df["listing_id"].isin(listing_ids)).sum())
    df = df[df["listing_id"].isin(listing_ids)]
    add_log(name, "Calendar rows with a listing_id missing from listings.csv", "Checked. Would drop them (none found)", orphans)

    # 4. available is the text 'Yes' or 'No'.
    rows = int(df["available"].isin(["t", "f"]).sum())
    df["available"] = df["available"].map({"t": "Yes", "f": "No"})
    add_log(name, "`available` stored as text 't'/'f' (unclear to a reader)",
    "Converted to 'Yes' (available) / 'No' (not available) so the column is readable without a code book", rows)

    # 5. maximum_nights = 2,147,483,647 is a "no limit" placeholder, not a real number
    rows = int((df["maximum_nights"] > MAX_NIGHTS_LIMIT).sum())
    df.loc[df["maximum_nights"] > MAX_NIGHTS_LIMIT, "maximum_nights"] = np.nan
    df["maximum_nights"] = df["maximum_nights"].astype("Int64")
    add_log(name, "`maximum_nights` = 2,147,483,647 (a 'no limit' placeholder; it wrecks averages)", "Set to NULL", rows)

    # Notes: things I found but did not change
    n_not_available = int((df["available"] == "No").sum())
    add_log(name, "`available` = 'No' mixes 'booked by a guest' and 'blocked by the host'",
            "Not fixable with this data. Do NOT treat 'No' as 'occupied' (it would overstate occupancy). Documented in README",
            n_not_available)

    return df.reset_index(drop=True)


# Clean reviews
def clean_reviews(df, listing_ids):
    df = df.copy()
    name = "reviews.csv"

    # Rename: the column "id" is the review id. A clear name avoids mix-ups in joins.
    df = df.rename(columns={"id": "review_id"})
    add_log(name, "Column `id` is ambiguous (review id? listing id?)", "Renamed to `review_id`", "column")

    # 1. Dates
    parsed = pd.to_datetime(df["date"], errors="coerce")
    bad_dates = int(parsed.isna().sum())
    df = df[parsed.notna()]
    add_log(name, "Dates that are not valid dates", "Checked. Would drop them (none found)", bad_dates)

    # 2. Orphans
    orphans = int((~df["listing_id"].isin(listing_ids)).sum())
    df = df[df["listing_id"].isin(listing_ids)]
    add_log(name, "Reviews whose listing_id is missing from listings.csv", "Checked. Would drop them (none found)", orphans)

    # 3. HTML tags, extra spaces and line breaks inside comments
    before = df["comments"]
    df["comments"] = clean_text(df["comments"])
    html_rows = int(before.str.contains(HAS_TAG_PATTERN, na=False).sum())
    space_rows = int(before.str.contains(r"^\s|\s$|\s\s", na=False).sum())
    add_log(name, "`<br/>` HTML tags inside comments", "Replaced with a space (also converted codes like &amp;)", html_rows)
    add_log(name, "Leading/trailing/double spaces in comments", "Trimmed, and repeated spaces collapsed to one", space_rows)

    # 4. The same review saved twice (same listing, reviewer, date and text; only the id differs)
    key = ["listing_id", "reviewer_id", "date", "comments"]
    is_duplicate = df.duplicated(key, keep="first") & df["comments"].notna()
    n_dups = int(is_duplicate.sum())
    df = df[~is_duplicate]
    add_log(name, "Same review saved twice (same listing, reviewer, date and text, different review id)", "Dropped the repeats, kept the first", n_dups)

    # 5. The same review id on several listings
    on_many = df["review_id"].duplicated(keep=False)  # every row of a repeated review
    is_copy = df["review_id"].duplicated(keep="first")  # only the extra copies
    df["is_review_copy"] = yes_no(is_copy)
    n_ids = int(df.loc[on_many, "review_id"].nunique())
    n_rows = int(on_many.sum())
    n_copies = int(is_copy.sum())
    add_log(name,
            f"{n_ids:,} review ids appear on more than one listing ({n_rows:,} rows in total). It is always listings of the SAME host, so the host re-listed the property and the reviews were carried over",
            "KEPT all rows, because each listing really shows that review and the counts match listings.number_of_reviews. Added `is_review_copy` = 'Yes' on the extra copies, so `WHERE is_review_copy = 'No'` gives exactly one row per review for review-level analysis (sentiment, reviewer counts, reviews per year)",
            n_copies)

    # 6. Comments that are just a dot or a dash
    placeholder = df["comments"].isin([".", "-", "..", "..."])
    n_placeholder = int(placeholder.sum())
    df.loc[placeholder, "comments"] = np.nan
    add_log(name, "Comments that are only '.' or '-' (no content)", "Set to NULL. Emoji-only comments are kept because they carry sentiment", n_placeholder)

    # Notes about items found but not changed
    add_log(name, "Missing comments (includes the ones set to NULL above)", "Kept as NULL, not filled in. The review (date, reviewer) still counts as a stay", int(df["comments"].isna().sum()))
    add_log(name, "Missing reviewer_name", "Kept as NULL (reviewer_id is still there)", int(df["reviewer_name"].isna().sum()))
    repeat = int(df.duplicated(["listing_id", "reviewer_id"]).sum())
    add_log(name, "Same reviewer reviewing the same listing on different dates", "Kept. These are genuine repeat guests, not errors", repeat)
    add_log(name, "Comments are in many languages (English, Dutch, French, ...)", "Not changed. Needs language detection before any text/sentiment analysis. Documented in README", len(df))

    return df.reset_index(drop=True)


# Clean listings
def clean_listings(df, calendar_days_available):
    df = df.copy()
    name = "listings.csv"

    # 1. Drop columns that are 100% empty
    df = df.drop(columns=EMPTY_COLUMNS)
    add_log(name, f"{len(EMPTY_COLUMNS)} columns are 100% empty: " + ", ".join(EMPTY_COLUMNS), "Dropped. (This also means host_since, host response/acceptance rate and instant_bookable cannot be analysed from this scrape)", f"{len(EMPTY_COLUMNS)} columns")

    # 2. Drop constant / useless columns
    df = df.drop(columns=USELESS_COLUMNS)
    add_log(name, "Columns with the same value in every row (scrape_id, calendar_last_scraped, source) and `price_quote_raw`, a JSON text blob that repeats other columns", "Dropped. (`last_scraped` is kept so the scrape date, 2026-09-17, stays in the data)", f"{len(USELESS_COLUMNS)} columns")

    # 3. Rename id so it matches calendar.listing_id and reviews.listing_id
    df = df.rename(columns={"id": "listing_id"})
    add_log(name, "Key column is called `id` here but `listing_id` in the other two files", "Renamed to `listing_id` so joins are obvious", "column")

    # 4. Duplicate listing ids
    dups = int(df["listing_id"].duplicated().sum())
    df = df.drop_duplicates("listing_id")
    add_log(name, "Duplicate listing ids", "Checked. Would keep the first (none found)", dups)

    # 5. Price is text like "$1,234.00" (the currency is actually EUR)
    rows = int(df["price"].notna().sum())
    df["price"] = df["price"].str.replace("$", "", regex=False).str.replace(",", "", regex=False).astype(float)
    add_log(name, "`price` stored as text with a '$' sign and commas. The currency is actually EUR (the price quote data says currency = EUR for every quoted listing)", "Converted to a number. Treat it as EUR per night", rows)

    # 6. Missing prices
    n_no_price = int(df["price"].isna().sum())
    n_no_price_unavailable = int((df["price"].isna() & (df["availability_365"] == 0)).sum())
    add_log(name, f"`price` is missing for {pct(n_no_price, len(df))}% of listings. {n_no_price_unavailable:,} of them have availability_365 = 0, so the price is only shown for listings that can be booked", "Left as NULL, NOT filled in with an average. Price analysis only describes bookable listings. `estimated_revenue_l365d` is missing for the same rows", n_no_price)

    # 7. Extreme prices
    is_outlier = df["price"] > PRICE_OUTLIER_LIMIT
    df["flag_price_outlier"] = yes_no(is_outlier)
    n = int(is_outlier.sum())
    add_log(name,
            f"Extreme prices: {n} listings above EUR {PRICE_OUTLIER_LIMIT:,} a night, up to EUR 11,681 (for 4 guests). Most have 0-1 reviews",
            "Kept the row, added `flag_price_outlier` = 'Yes' so analysts can filter them. I cannot prove they are errors",
            n)

    # 8. maximum_nights placeholder 2,147,483,647
    max_cols = [c for c in df.columns if "maximum_nights" in c]
    rows = int((df[max_cols] > MAX_NIGHTS_LIMIT).any(axis=1).sum())
    for c in max_cols:
        df.loc[df[c] > MAX_NIGHTS_LIMIT, c] = np.nan
    add_log(name, "`maximum_nights` (and its min/max/avg versions) = 2,147,483,647, a 'no limit' placeholder", "Set to NULL", rows)

    # 9. Whole-number columns loaded as decimals
    for c in WHOLE_NUMBER_COLUMNS:
        df[c] = df[c].astype("Int64")
    add_log(name, "Whole-number columns (bedrooms, beds, minimum_nights, ...) loaded as decimals like 2.0", "Converted to integers", f"{len(WHOLE_NUMBER_COLUMNS)} columns")

    # 10. Long stays
    # (rows with a missing minimum_nights compare as NA, so fillna(False) makes them 0)
    is_long_stay = (df["minimum_nights"] >= LONG_STAY_NIGHTS).fillna(False).astype(bool)
    df["flag_long_stay"] = yes_no(is_long_stay)
    n = int(is_long_stay.sum())
    add_log(name,
            f"Listings with a minimum stay of {LONG_STAY_NIGHTS}+ nights (up to 800). These are long-term rentals, not short-term stays",
            "Kept, added `flag_long_stay` = 'Yes' so short-term analysis can exclude them", n)

    # 11. Bathrooms: the numeric column is empty but bathrooms_text has the information
    n_text = int(df["bathrooms_text"].notna().sum())
    df["bathrooms"] = df["bathrooms_text"].apply(bathrooms_from_text)
    add_log(name, "`bathrooms` is 100% empty but `bathrooms_text` ('1.5 shared baths', 'Half-bath') has the data", "Rebuilt `bathrooms` as a number from the text ('Half-bath' = 0.5). 8 listings have no text, so they stay NULL", n_text)
    n_big = int((df["bathrooms"] >= 10).sum())
    add_log(name, "Implausible bathroom counts (12 baths for a 2-guest listing, 17 for a boat)", "Kept as they are, only 2 rows. Not changed because I cannot verify the true value", n_big)

    # 12. Yes/No columns
    for c in TRUE_FALSE_COLUMNS:
        df[c] = df[c].map({"t": "Yes", "f": "No"})
    add_log(name, "True/false columns stored as text 't'/'f': " + ", ".join(TRUE_FALSE_COLUMNS),
            "Converted to 'Yes'/'No'. `has_availability` has 127 missing values that stay NULL",
            f"{len(TRUE_FALSE_COLUMNS)} columns")

    # 13. Text columns: HTML, extra spaces, line breaks
    for c in ["name", "host_name", "description", "host_about"]:
        before = df[c]
        df[c] = clean_text(df[c])
        add_log(name, f"`{c}`: HTML tags (`<br />`), double spaces, line breaks or leading/trailing spaces", "Cleaned: tags removed, spaces collapsed, trimmed", count_changed(before, df[c]))

    # 14. host_location spelling
    before = df["host_location"]
    df["host_location"] = df["host_location"].str.replace(", The Netherlands", ", Netherlands", regex=False)
    df["host_location"] = df["host_location"].replace("The Netherlands", "Netherlands")
    add_log(name, "`host_location` has two spellings of the same place: 'Amsterdam, Netherlands' and 'Amsterdam, The Netherlands' (also 'The Netherlands' vs 'Netherlands')", "Standardised to the spelling without 'The'", count_changed(before, df["host_location"]))
    n_vague = int((df["host_location"] == "Netherlands").sum())
    add_log(name, "`host_location` is just 'Netherlands' (too vague to know if the host lives in Amsterdam)", "Not changed. Do not use host_location to decide if a host is local", n_vague)

    # 15. Placeholder license number
    placeholder = df["license"].str.contains("ABCD 1234", na=False)
    n = int(placeholder.sum())
    df.loc[placeholder, "license"] = np.nan
    add_log(name, "License = 'ABCD 1234 AB12 89EF A0F9', the example number from the registration form, not a real license", "Set to NULL", n)
    real_licenses = df[df["license"].notna() & (df["license"] != "Exempt")]
    hosts_per_license = real_licenses.groupby("license")["host_id"].nunique()
    n_shared = int((hosts_per_license > 1).sum())
    add_log(name, "License numbers that are used by more than one host (counted in licenses, not rows)", "Not changed. Cannot tell which host is right. Do not use license as a unique ID", n_shared)

    # 16. Dates: check they are real dates (kept as YYYY-MM-DD text, which SQLite sorts correctly)
    for c in ["last_scraped", "first_review", "last_review"]:
        parsed = pd.to_datetime(df[c], errors="coerce")
        bad = int((parsed.isna() & df[c].notna()).sum())
        df.loc[parsed.isna(), c] = np.nan
        add_log(name, f"`{c}`: values that are not valid dates", "Checked. Would set to NULL (none found)", bad)

    # 17. Missing review data
    n_no_reviews = int((df["number_of_reviews"] == 0).sum())
    add_log(name, "Review scores, first_review, last_review and reviews_per_month are missing for listings with 0 reviews", "Kept as NULL. This is correct, not an error. Never fill with 0 (it would drag averages down)", n_no_reviews)

    # 18. reviews_per_month outliers
    is_rpm_outlier = df["reviews_per_month"] > MAX_REVIEWS_PER_MONTH
    df["flag_reviews_per_month_outlier"] = yes_no(is_rpm_outlier)
    n = int(is_rpm_outlier.sum())
    add_log(name, f"reviews_per_month above {MAX_REVIEWS_PER_MONTH} (up to 90, i.e. 3 reviews a day)",
            "Kept, added `flag_reviews_per_month_outlier` = 'Yes'", n)

    # 19. Listing availability vs calendar.csv
    df["calendar_days_available"] = df["listing_id"].map(calendar_days_available).fillna(0).astype(int)
    mismatch = df["availability_365"] != df["calendar_days_available"]
    df["flag_availability_mismatch"] = yes_no(mismatch)
    n = int(mismatch.sum())
    n_more = int((df["calendar_days_available"] > df["availability_365"]).sum())
    add_log(name,
            f"`availability_365` does not match the number of available days in calendar.csv (the calendar shows MORE available days in {n_more} of them)",
            "Kept both. Added `calendar_days_available` (counted from calendar.csv) and `flag_availability_mismatch` = 'Yes'. Pick one source and stay consistent",
            n)
    n = int(((df["has_availability"] == "No") & (df["calendar_days_available"] > 0)).sum())
    add_log(name, "`has_availability` = 'No' but the calendar shows available days",
            "Not changed, but this is another sign the availability fields disagree. Documented in README", n)

    # Notes: found but not changed
    n_bedrooms = int(df["bedrooms"].isna().sum())
    n_beds = int(df["beds"].isna().sum())
    add_log(name, f"Missing bedrooms ({n_bedrooms}) and beds ({n_beds})", "Left as NULL. Guessing would add made-up numbers", n_bedrooms + n_beds)
    n = int((df["bedrooms"] == 0).sum())
    add_log(name, "bedrooms = 0", "Kept. Mostly studios, a real value, not missing", n)
    n = int((df["accommodates"] < df["bedrooms"]).sum())
    add_log(name, "Listings with more bedrooms than guests accommodated (e.g. 17 bedrooms, 16 guests)", "Kept. Odd but possible, not provably wrong", n)
    n = int((df["host_listings_count"] != df["calculated_host_listings_count"]).sum())
    add_log(name, "`host_listings_count` (host's listings worldwide, up to 1,192) differs from `calculated_host_listings_count` (listings in this file)", "Kept both. Use `calculated_host_listings_count` for Amsterdam analysis", n)
    total = (df["calculated_host_listings_count_entire_homes"] + df["calculated_host_listings_count_private_rooms"] + df["calculated_host_listings_count_shared_rooms"])
    n = int((total != df["calculated_host_listings_count"]).sum())
    add_log(name, "Entire + private + shared host counts do not add up to the host total. These are hosts with a hotel room, which has no column of its own", "Kept. Explained, not an error", n)
    n = int(df.duplicated(["host_id", "latitude", "longitude", "name"]).sum())
    add_log(name, "Possible duplicate listings: same host, same coordinates, same name, different listing_id", "Kept. Each has its own calendar and reviews and I cannot prove they are the same property. Documented in README", n)
    cap = int(df["estimated_occupancy_l365d"].max())
    n = int((df["estimated_occupancy_l365d"] == cap).sum())
    add_log(name, f"`estimated_occupancy_l365d` sits exactly at {cap} nights for many listings (looks like a model cap, not a real measurement)", "Kept. Treat estimated occupancy/revenue as rough estimates", n)
    add_log(name, "Listing ids and review ids are up to 19 digits long", "Stored as INTEGER in SQLite (safe). Do NOT open the CSVs in Excel: it rounds numbers this long and corrupts the ids", "all rows")

    return df.reset_index(drop=True)


# Write the markdown files
def write_cleaning_log(path):
    lines = []
    lines.append("# Cleaning log\n")
    lines.append("Created automatically by `clean.py`. The numbers are counted on the data, so they stay correct every time the script is re-run.\n")
    lines.append("Raw data: Inside Airbnb, Amsterdam, scraped 2026-09-17.\n")
    for file in ["listings.csv", "calendar.csv", "reviews.csv"]:
        lines.append(f"\n## {file}\n")
        lines.append("| # | Issue | Decision | Rows affected |")
        lines.append("|---|-------|----------|---------------|")
        number = 1
        for item in log:
            if item["file"] != file:
                continue
            rows = item["rows"]
            if isinstance(rows, (int, np.integer)):
                rows = f"{rows:,}"
            lines.append(f"| {number} | {item['issue']} | {item['decision']} | {rows} |")
            number += 1
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def write_quality_table(path, before_after):
    lines = []
    lines.append("# Data quality: before vs after\n")
    lines.append("The same checks were run on the raw CSVs and on the clean tables.\n")
    for file, rows in before_after.items():
        lines.append(f"\n## {file}\n")
        lines.append("| Check | Before | After |")
        lines.append("|-------|-------:|------:|")
        for check, before, after in rows:
            lines.append(f"| {check} | {before:,} | {after:,} |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# Main program
def main():
    # Step 1: read the raw files
    print("Step 1: reading raw files...")
    listings_raw = pd.read_csv(os.path.join(RAW_FOLDER, "listings.csv"))
    calendar_raw = pd.read_csv(os.path.join(RAW_FOLDER, "calendar.csv"))
    reviews_raw = pd.read_csv(os.path.join(RAW_FOLDER, "reviews.csv"))
    print(f"  listings {len(listings_raw):,} | calendar {len(calendar_raw):,} | reviews {len(reviews_raw):,}")

    # Step 2: quality checks on the RAW data
    print("Step 2: checking raw data quality...")
    raw_ids = set(listings_raw["id"])
    before = {
        "listings": listings_checks(listings_raw),
        "calendar": calendar_checks(calendar_raw, raw_ids),
        "reviews": reviews_checks(reviews_raw, raw_ids),
    }

    # Step 3: clean
    print("Step 3: cleaning...")
    calendar = clean_calendar(calendar_raw, raw_ids)
    reviews = clean_reviews(reviews_raw, raw_ids)
    days_available = calendar[calendar["available"] == "Yes"].groupby("listing_id").size()
    listings = clean_listings(listings_raw, days_available)

    #Step 4: quality checks on the clean data
    print("Step 4: checking clean data quality...")
    clean_ids = set(listings["listing_id"])
    after = {
        "listings": listings_checks(listings),
        "calendar": calendar_checks(calendar, clean_ids),
        "reviews": reviews_checks(reviews, clean_ids),
    }
    before_after = {}
    for table in ["listings", "calendar", "reviews"]:
        rows = []
        for check in before[table]:
            rows.append((check, before[table][check], after[table][check]))
        before_after[f"{table}.csv"] = rows

    # Step 5: load into SQLite
    print("Step 5: loading into SQLite (the calendar table is big, this takes a little while)...")
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)               # start fresh so the script is re-runnable
    connection = sqlite3.connect(DB_FILE)
    listings.to_sql("listings", connection, index=False)
    reviews.to_sql("reviews", connection, index=False, chunksize=100000)

    # The calendar is the biggest table, so I create it by hand with a primary key.
    # without ROWID stores the data in key order, which keeps the file much smaller.
    connection.execute("""
        CREATE TABLE calendar (
            listing_id      INTEGER NOT NULL,
            date            TEXT    NOT NULL,
            available       TEXT    NOT NULL CHECK (available IN ('Yes', 'No')),   -- 1 = available, 0 = not available
            minimum_nights  INTEGER,
            maximum_nights  INTEGER,            -- NULL where the raw file had the 'no limit' placeholder
            PRIMARY KEY (listing_id, date)
        ) WITHOUT ROWID
    """)
    calendar.to_sql("calendar", connection, if_exists="append", index=False, chunksize=100000)

    # Unique indexes act like primary keys. If a duplicate slipped through, this fails.
    connection.execute("CREATE UNIQUE INDEX idx_listings_id ON listings (listing_id)")
    connection.execute("CREATE UNIQUE INDEX idx_reviews_key ON reviews (listing_id, review_id)")
    connection.execute("CREATE INDEX idx_reviews_date ON reviews (date)")
    connection.commit()

    # Step 6: check the database itself
    print("Step 6: checking the database...")
    for table in ["listings", "calendar", "reviews"]:
        count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count:,} rows")
    orphan_reviews = connection.execute(
        "SELECT COUNT(*) FROM reviews r LEFT JOIN listings l ON r.listing_id = l.listing_id WHERE l.listing_id IS NULL"
    ).fetchone()[0]
    orphan_days = connection.execute(
        "SELECT COUNT(*) FROM calendar c LEFT JOIN listings l ON c.listing_id = l.listing_id WHERE l.listing_id IS NULL"
    ).fetchone()[0]
    print(f"  reviews without a listing: {orphan_reviews} | calendar rows without a listing: {orphan_days}")
    connection.close()

    # Step 7: write the documents
    write_cleaning_log(LOG_FILE)
    write_quality_table(QUALITY_FILE, before_after)
    print(f"Done. Created {DB_FILE}, {LOG_FILE} and {QUALITY_FILE}")

# run the program
if __name__ == "__main__":
    main()

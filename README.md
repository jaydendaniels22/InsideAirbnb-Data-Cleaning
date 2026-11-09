# Cleaning the Inside Airbnb Amsterdam, North Holland, The Netherlands data

Raw CSV files in, one clean SQLite database out. Everything is done by one python script called cleaner.py.

## 1. Problems I identified

Inside Airbnb publishes three files for Amsterdam, North Holland, The Netherlands which was scraped on 2026-09-17:

| File | Rows | What it is |
|------|-----:|------------|
| `listings.csv` | 10,612 | one row per listing, 90 columns |
| `calendar.csv` | 3,873,380 | one row per listing per day (10,612 listings x 365 days, 2026-09-17 to 2027-09-16) |
| `reviews.csv` | 571,927 | one row per review (2010-08-22 to 2026-09-17) |

The files present tidy, but used as they are they give wrong answers. Prices are text, an "unlimited" placeholder of 2,147,483,647 nights wrecks averages, nearly a quarter of review comments contain HTML tags, and 43% of listings have no price at all. The goal: find every issue, decide what to do about each one, and leave a clean, documented dataset that is safe to analyse.

## 2. What I found

All counts are measured by the script. The full list (36 issues in listings, 7 in calendar, 12 in reviews) is in [`cleaning_log.md`](cleaning_log.md). These are the ones that matter most for analysis:

| # | Finding | Why it matters |
|---|---------|----------------|
| 1 | **Price is text** like `$1,234.00`, and the `$` is wrong: the currency is **EUR** | Cannot average or sort it; wrong currency symbol |
| 2 | **43.1% of listings (4,573) have no price.** 4,200 of them have `availability_365 = 0` | Price is only shown for listings that can be booked, so any price average describes bookable listings only |
| 3 | **`maximum_nights` = 2,147,483,647** (a "no limit" placeholder): 2 listings, 730 calendar rows | Raw calendar average was 405,058 nights (over 1,100 years). After cleaning it is 331 |
| 4 | **7 extreme prices** (EUR 3,104 to 11,681 a night, mostly 0-1 reviews) | These 7 listings (0.1%) move the average price from 337 to 345 |
| 5 | **14 columns are 100% empty**, including `host_since`, response and acceptance rate, `instant_bookable` | Those topics cannot be analysed from this scrape |
| 6 | **`bathrooms` is empty** but `bathrooms_text` ("1.5 shared baths") has the data | Recoverable |
| 7 | **16,954 review rows are extra copies**: 6,552 review ids appear on several listings of the same host (the host re-listed the property and the reviews came along) | Counting review rows overstates real reviews by 3.0% (571,918 rows vs 554,964 distinct reviews) |
| 8 | **9 reviews saved twice** (same listing, reviewer, date, text, different id) | Plain duplicates |
| 9 | **HTML and messy spaces**: `<br/>` in 129,453 comments, 5,581 descriptions; extra spaces in 86,337 comments | Noise for any text analysis |
| 10 | **`availability_365` disagrees with `calendar.csv`** for 264 listings (the calendar shows more available days), and 310 listings say `has_availability = f` while the calendar shows open days | Two sources for availability, they conflict |
| 11 | **`available = f` means "booked" OR "blocked by host"**, and 72.4% of days are `f` | Cannot be read as occupancy |
| 12 | **Smaller issues**: two spellings of "Amsterdam, (The) Netherlands" (1,882 rows), a placeholder license `ABCD 1234...` (15 rows), 111 long-term listings (28+ night minimum), 9 listings with over 31 reviews a month, `t`/`f` text instead of 1/0 | See the log |

**Also true, and not a problem:** all 10,612 listings have exactly 365 calendar days, there are no duplicate keys, no orphan rows (every calendar and review row has a listing), all dates are valid, and the number of review rows per listing matches `listings.number_of_reviews` exactly (before the 9 duplicates were dropped).

## 3. What I changed

I used three rules: **fix** what is clearly wrong, **flag** what is odd but might be real, and **never invent data**.

**Fixed**
- `price`: text to number (EUR per night).
- `available` in the calendar and four `t`/`f` columns in listings: to 1/0.
- `maximum_nights` placeholder (2,147,483,647): to NULL.
- `bathrooms`: rebuilt from `bathrooms_text`.
- HTML tags, repeated spaces and line breaks removed from names, descriptions, host text and review comments.
- `host_location` spelling standardised.
- Placeholder license number to NULL; comments that are only "." or "-" to NULL.
- 9 repeated reviews dropped.
- Key columns renamed so joins are obvious: `listings.id` is now `listing_id`, `reviews.id` is now `review_id`.

**Flagged (row kept, you decide)**

| Flag column | Meaning | Rows |
|-------------|---------|-----:|
| `listings.flag_price_outlier` | price above EUR 3,000 a night | 7 |
| `listings.flag_long_stay` | minimum stay of 28+ nights | 111 |
| `listings.flag_reviews_per_month_outlier` | more than 31 reviews a month | 9 |
| `listings.flag_availability_mismatch` | `availability_365` differs from the calendar count in `calendar_days_available` | 264 |
| `reviews.is_review_copy` | extra copy of a review already shown on another listing | 16,954 |

**Dropped:** 13 empty columns, plus `scrape_id`, `calendar_last_scraped`, `source` (same value in every row) and `price_quote_raw` (a JSON text blob that repeats other columns). `listings` goes from 90 to 78 columns (the 78 include 5 new columns: the four `listings.flag_...` columns above and `calendar_days_available`).

**Left alone on purpose:** missing prices, bedrooms (29) and beds (385) stay NULL. Missing review scores for the 1,002 listings with no reviews stay NULL (filling with 0 would drag averages down). Odd but possible values (12 baths for a 2-guest listing, 17 bedrooms for 16 guests) are kept, because I cannot verify the truth.

Before/after numbers are in [`data_quality_before_after.md`](data_quality_before_after.md). A few of them:

| Check | Before | After |
|-------|-------:|------:|
| Rows with a numeric price | 0 | 6,039 |
| Columns that are 100% empty | 14 | 0 |
| Calendar rows with the `maximum_nights` placeholder | 730 | 0 |
| Comments containing HTML tags | 129,453 | 0 |
| Same review repeated | 9 | 0 |

("Rows with a numeric price" is 0 before because every raw price is text like `$97.00`.)

## 4. The clean dataset

`airbnb_amsterdam.db` (SQLite, about 350 MB). Open it with Python's `sqlite3`, DB Browser for SQLite, or the `sqlite3` command line.

| Table | Rows | Key |
|-------|-----:|-----|
| `listings` | 10,612 | `listing_id` (unique) |
| `calendar` | 3,873,380 | `(listing_id, date)` (primary key) |
| `reviews` | 571,918 | `(listing_id, review_id)` (unique) |

`calendar.listing_id` and `reviews.listing_id` both join to `listings.listing_id`. I checked in SQL that there are no orphan rows.

**Suggested filters**
- Price analysis: `WHERE price IS NOT NULL AND flag_price_outlier = 0 AND flag_long_stay = 0`
- Counting reviews as reviews (not rows): `WHERE is_review_copy = 0`
- Availability: pick **either** `availability_365` **or** `calendar_days_available` and stay with it

```sql
-- Average nightly price (EUR) by neighbourhood, bookable short-term listings only
SELECT neighbourhood_cleansed, COUNT(*) AS listings, ROUND(AVG(price), 0) AS avg_price
FROM listings
WHERE price IS NOT NULL AND flag_price_outlier = 0 AND flag_long_stay = 0
GROUP BY neighbourhood_cleansed
ORDER BY avg_price DESC;

-- Reviews per year, one row per review
SELECT substr(date, 1, 4) AS year, COUNT(*) AS reviews
FROM reviews
WHERE is_review_copy = 0
GROUP BY year
ORDER BY year;
```

## 5. Limits you should know about

- **Price covers 56.9% of listings** and only the bookable ones. Do not read it as "the price of all Amsterdam listings".
- **The calendar has no price column** in this scrape, so there is no price-by-date analysis. `calendar.available = 0` can be a booking or a host block, so it is not occupancy.
- **`estimated_occupancy_l365d` and `estimated_revenue_l365d`** are model estimates (1,031 listings sit exactly at the same 255-night value, which looks like a cap). Use them as rough guides.
- **I could not check** whether the 7 extreme prices are typos or real, or whether the 13 "same host, same place, same name" listings are the same property. They are kept and logged, not deleted.
- **Review comments are in many languages** (English, Dutch, French and more). Text or sentiment analysis needs language detection first.
- **Do not open the raw CSVs in Excel and save them.** Listing and review ids are up to 19 digits and Excel rounds them, which breaks every join. SQLite stores them correctly.
- `host_listings_count` (the host's listings worldwide, up to 1,192) is not the same as `calculated_host_listings_count` (listings in this file). Use the second for Amsterdam.

## 6. How to re-run

```
airbnb_amsterdam_cleaning/
  clean.py
  raw/                      <- put calendar.csv, listings.csv, reviews.csv here
  airbnb_amsterdam.db       <- created by clean.py
  cleaning_log.md           <- created by clean.py
  data_quality_before_after.md  <- created by clean.py
```

```
pip install pandas numpy
python clean.py
```

It takes about 30 seconds. It deletes and rebuilds `airbnb_amsterdam.db` every time and never touches the raw files. I ran it twice and the log and quality table came out identical both times. The numbers in the log and the quality table are counted on the data each run, not typed in, so if you swap in a newer scrape the documents update themselves (a few wording details, such as the examples "up to EUR 11,681" and "12 baths", are written for this scrape and may need a manual touch).

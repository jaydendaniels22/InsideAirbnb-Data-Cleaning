# Cleaning log

Created automatically by `clean.py`. The numbers are counted on the data, so they stay correct every time the script is re-run.

Raw data: Inside Airbnb, Amsterdam, scraped 2026-09-17.


## listings.csv

| # | Issue | Decision | Rows affected |
|---|-------|----------|---------------|
| 1 | 13 columns are 100% empty: neighborhood_overview, host_since, host_response_time, host_response_rate, host_acceptance_rate, host_thumbnail_url, host_neighbourhood, host_total_listings_count, host_verifications, neighbourhood, neighbourhood_group_cleansed, calendar_updated, instant_bookable | Dropped. (This also means host_since, host response/acceptance rate and instant_bookable cannot be analysed from this scrape) | 13 columns |
| 2 | Columns with the same value in every row (scrape_id, calendar_last_scraped, source) and `price_quote_raw`, a JSON text blob that repeats other columns | Dropped. (`last_scraped` is kept so the scrape date, 2026-09-17, stays in the data) | 4 columns |
| 3 | Key column is called `id` here but `listing_id` in the other two files | Renamed to `listing_id` so joins are obvious | column |
| 4 | Duplicate listing ids | Checked. Would keep the first (none found) | 0 |
| 5 | `price` stored as text with a '$' sign and commas. The currency is actually EUR (the price quote data says currency = EUR for every quoted listing) | Converted to a number. Treat it as EUR per night | 6,039 |
| 6 | `price` is missing for 43.1% of listings. 4,200 of them have availability_365 = 0, so the price is only shown for listings that can be booked | Left as NULL, NOT filled in with an average. Price analysis only describes bookable listings. `estimated_revenue_l365d` is missing for the same rows | 4,573 |
| 7 | Extreme prices: 7 listings above EUR 3,000 a night, up to EUR 11,681 (for 4 guests). Most have 0-1 reviews | Kept the row, added `flag_price_outlier` = 'Yes' so analysts can filter them. I cannot prove they are errors | 7 |
| 8 | `maximum_nights` (and its min/max/avg versions) = 2,147,483,647, a 'no limit' placeholder | Set to NULL | 2 |
| 9 | Whole-number columns (bedrooms, beds, minimum_nights, ...) loaded as decimals like 2.0 | Converted to integers | 8 columns |
| 10 | Listings with a minimum stay of 28+ nights (up to 800). These are long-term rentals, not short-term stays | Kept, added `flag_long_stay` = 'Yes' so short-term analysis can exclude them | 111 |
| 11 | `bathrooms` is 100% empty but `bathrooms_text` ('1.5 shared baths', 'Half-bath') has the data | Rebuilt `bathrooms` as a number from the text ('Half-bath' = 0.5). 8 listings have no text, so they stay NULL | 10,604 |
| 12 | Implausible bathroom counts (12 baths for a 2-guest listing, 17 for a boat) | Kept as they are, only 2 rows. Not changed because I cannot verify the true value | 2 |
| 13 | True/false columns stored as text 't'/'f': host_is_superhost, host_has_profile_pic, host_identity_verified, has_availability | Converted to 'Yes'/'No'. `has_availability` has 127 missing values that stay NULL | 4 columns |
| 14 | `name`: HTML tags (`<br />`), double spaces, line breaks or leading/trailing spaces | Cleaned: tags removed, spaces collapsed, trimmed | 154 |
| 15 | `host_name`: HTML tags (`<br />`), double spaces, line breaks or leading/trailing spaces | Cleaned: tags removed, spaces collapsed, trimmed | 4 |
| 16 | `description`: HTML tags (`<br />`), double spaces, line breaks or leading/trailing spaces | Cleaned: tags removed, spaces collapsed, trimmed | 6,168 |
| 17 | `host_about`: HTML tags (`<br />`), double spaces, line breaks or leading/trailing spaces | Cleaned: tags removed, spaces collapsed, trimmed | 2,159 |
| 18 | `host_location` has two spellings of the same place: 'Amsterdam, Netherlands' and 'Amsterdam, The Netherlands' (also 'The Netherlands' vs 'Netherlands') | Standardised to the spelling without 'The' | 1,882 |
| 19 | `host_location` is just 'Netherlands' (too vague to know if the host lives in Amsterdam) | Not changed. Do not use host_location to decide if a host is local | 384 |
| 20 | License = 'ABCD 1234 AB12 89EF A0F9', the example number from the registration form, not a real license | Set to NULL | 15 |
| 21 | License numbers that are used by more than one host (counted in licenses, not rows) | Not changed. Cannot tell which host is right. Do not use license as a unique ID | 60 |
| 22 | `last_scraped`: values that are not valid dates | Checked. Would set to NULL (none found) | 0 |
| 23 | `first_review`: values that are not valid dates | Checked. Would set to NULL (none found) | 0 |
| 24 | `last_review`: values that are not valid dates | Checked. Would set to NULL (none found) | 0 |
| 25 | Review scores, first_review, last_review and reviews_per_month are missing for listings with 0 reviews | Kept as NULL. This is correct, not an error. Never fill with 0 (it would drag averages down) | 1,002 |
| 26 | reviews_per_month above 31 (up to 90, i.e. 3 reviews a day) | Kept, added `flag_reviews_per_month_outlier` = 'Yes' | 9 |
| 27 | `availability_365` does not match the number of available days in calendar.csv (the calendar shows MORE available days in 264 of them) | Kept both. Added `calendar_days_available` (counted from calendar.csv) and `flag_availability_mismatch` = 'Yes'. Pick one source and stay consistent | 264 |
| 28 | `has_availability` = 'No' but the calendar shows available days | Not changed, but this is another sign the availability fields disagree. Documented in README | 310 |
| 29 | Missing bedrooms (29) and beds (385) | Left as NULL. Guessing would add made-up numbers | 414 |
| 30 | bedrooms = 0 | Kept. Mostly studios, a real value, not missing | 222 |
| 31 | Listings with more bedrooms than guests accommodated (e.g. 17 bedrooms, 16 guests) | Kept. Odd but possible, not provably wrong | 35 |
| 32 | `host_listings_count` (host's listings worldwide, up to 1,192) differs from `calculated_host_listings_count` (listings in this file) | Kept both. Use `calculated_host_listings_count` for Amsterdam analysis | 1,020 |
| 33 | Entire + private + shared host counts do not add up to the host total. These are hosts with a hotel room, which has no column of its own | Kept. Explained, not an error | 49 |
| 34 | Possible duplicate listings: same host, same coordinates, same name, different listing_id | Kept. Each has its own calendar and reviews and I cannot prove they are the same property. Documented in README | 13 |
| 35 | `estimated_occupancy_l365d` sits exactly at 255 nights for many listings (looks like a model cap, not a real measurement) | Kept. Treat estimated occupancy/revenue as rough estimates | 1,031 |
| 36 | Listing ids and review ids are up to 19 digits long | Stored as INTEGER in SQLite (safe). Do NOT open the CSVs in Excel: it rounds numbers this long and corrupts the ids | all rows |

## calendar.csv

| # | Issue | Decision | Rows affected |
|---|-------|----------|---------------|
| 1 | Dates that are not valid dates | Checked. Would drop them (none found) | 0 |
| 2 | Same listing and date appears twice | Checked. Would keep the first (none found) | 0 |
| 3 | Calendar rows with a listing_id missing from listings.csv | Checked. Would drop them (none found) | 0 |
| 4 | `available` stored as text 't'/'f' (unclear to a reader) | Converted to 'Yes' (available) / 'No' (not available) so the column is readable without a code book | 3,873,380 |
| 5 | `maximum_nights` = 2,147,483,647 (a 'no limit' placeholder; it wrecks averages) | Set to NULL | 730 |
| 6 | `available` = 'No' mixes 'booked by a guest' and 'blocked by the host' | Not fixable with this data. Do NOT treat 'No' as 'occupied' (it would overstate occupancy). Documented in README | 2,806,070 |

## reviews.csv

| # | Issue | Decision | Rows affected |
|---|-------|----------|---------------|
| 1 | Column `id` is ambiguous (review id? listing id?) | Renamed to `review_id` | column |
| 2 | Dates that are not valid dates | Checked. Would drop them (none found) | 0 |
| 3 | Reviews whose listing_id is missing from listings.csv | Checked. Would drop them (none found) | 0 |
| 4 | `<br/>` HTML tags inside comments | Replaced with a space (also converted codes like &amp;) | 129,453 |
| 5 | Leading/trailing/double spaces in comments | Trimmed, and repeated spaces collapsed to one | 86,337 |
| 6 | Same review saved twice (same listing, reviewer, date and text, different review id) | Dropped the repeats, kept the first | 9 |
| 7 | 6,552 review ids appear on more than one listing (23,506 rows in total). It is always listings of the SAME host, so the host re-listed the property and the reviews were carried over | KEPT all rows, because each listing really shows that review and the counts match listings.number_of_reviews. Added `is_review_copy` = 'Yes' on the extra copies, so `WHERE is_review_copy = 'No'` gives exactly one row per review for review-level analysis (sentiment, reviewer counts, reviews per year) | 16,954 |
| 8 | Comments that are only '.' or '-' (no content) | Set to NULL. Emoji-only comments are kept because they carry sentiment | 1,177 |
| 9 | Missing comments (includes the ones set to NULL above) | Kept as NULL, not filled in. The review (date, reviewer) still counts as a stay | 1,210 |
| 10 | Missing reviewer_name | Kept as NULL (reviewer_id is still there) | 1 |
| 11 | Same reviewer reviewing the same listing on different dates | Kept. These are genuine repeat guests, not errors | 2,659 |
| 12 | Comments are in many languages (English, Dutch, French, ...) | Not changed. Needs language detection before any text/sentiment analysis. Documented in README | 571,918 |

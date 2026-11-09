# Data quality: before vs after

The same checks were run on the raw CSVs and on the clean tables.


## listings.csv

| Check | Before | After |
|-------|-------:|------:|
| Rows | 10,612 | 10,612 |
| Columns | 90 | 78 |
| Columns that are 100% empty | 14 | 0 |
| Duplicate listing ids | 0 | 0 |
| Rows with a numeric price | 0 | 6,039 |
| Rows with bathrooms filled in | 0 | 10,604 |
| Columns stored as 't'/'f' text | 4 | 0 |
| maximum_nights above 3650 (placeholder) | 2 | 0 |
| Placeholder license numbers | 15 | 0 |
| Descriptions containing HTML tags | 5,581 | 0 |
| Names / host names with extra spaces | 156 | 0 |
| host_location spelled 'The Netherlands' | 1,882 | 0 |
| Rows flagged as extreme price | 0 | 7 |

## calendar.csv

| Check | Before | After |
|-------|-------:|------:|
| Rows | 3,873,380 | 3,873,380 |
| Duplicate (listing, date) rows | 0 | 0 |
| Rows where available is 't'/'f' text | 3,873,380 | 0 |
| maximum_nights above 3650 (placeholder) | 730 | 0 |
| Rows whose listing is not in listings | 0 | 0 |
| Listings without exactly 365 days | 0 | 0 |

## reviews.csv

| Check | Before | After |
|-------|-------:|------:|
| Rows | 571,927 | 571,918 |
| Same review repeated (same listing, reviewer, date, text) | 9 | 0 |
| Rows whose review id appears on more than one listing | 23,506 | 23,506 |
| Rows flagged as an extra copy of a review (is_review_copy = Yes) | 0 | 16,954 |
| Comments containing HTML tags | 129,453 | 0 |
| Comments with leading/trailing/double spaces | 86,337 | 0 |
| Comments that are only '.' or '-' | 1,176 | 0 |
| Missing comments | 33 | 1,210 |
| Rows whose listing is not in listings | 0 | 0 |

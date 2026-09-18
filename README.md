# Dwell

Run the first interactive Google Flights input flow with:

```sh
python main.py
```

It collects the route, dates, cabin, and passenger counts, creates a
`FlightSearch`, and prints the generated Google Flights link.

The interactive flow can also encode result filters: maximum stops, included
or excluded airlines, local departure and arrival-hour windows, maximum flight
duration, connecting airports, lower-emission flights, maximum price, and bag
counts. Leave a filter blank (or keep its count at `0`) to omit it.

These values are serialized into Google's undocumented, reverse-engineered
`tfs` protobuf payload. They are not ordinary readable URL parameters, and
Google may change the format. In the importable API, use `LegFilters` for
per-leg filters and the `FlightSearch` fields `max_price`, `carry_on_bags`,
and `checked_bags` for search-wide filters. A round trip applies
`leg_filters` to both legs unless `return_leg_filters` is supplied.

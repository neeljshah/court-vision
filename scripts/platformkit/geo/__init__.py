"""scripts.platformkit.geo -- zero-network static city geo lookup.

Provides a shared static city -> {lat, lon, altitude_m, country, tz} table
plus great-circle distance, for later use by soccer_intl (travel/altitude),
tennis (travel/altitude), and WNBA (travel burden) dimensions.

No network calls anywhere in this package.
"""

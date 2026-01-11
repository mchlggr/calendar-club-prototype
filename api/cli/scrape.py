#!/usr/bin/env python3
"""
CLI for manual and scheduled event scraping.

Usage:
    # Scrape a single Posh event
    python -m api.cli.scrape posh-event https://posh.vip/e/event-slug

    # Discover Posh events for a city
    python -m api.cli.scrape posh-discover columbus --limit 20

    # Scrape and cache events
    python -m api.cli.scrape posh-discover columbus --cache
"""

import argparse
import asyncio
import json
import logging
import sys

from api.services.event_cache import get_event_cache
from api.services.firecrawl import ScrapedEvent, get_posh_extractor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def event_to_dict(event: ScrapedEvent) -> dict:
    """Convert ScrapedEvent to JSON-serializable dict."""
    data = event.model_dump()
    # Convert datetime to ISO format
    if data.get("start_time"):
        data["start_time"] = data["start_time"].isoformat()
    if data.get("end_time"):
        data["end_time"] = data["end_time"].isoformat()
    return data


async def scrape_posh_event(url: str, cache: bool = False) -> None:
    """Scrape a single Posh event."""
    extractor = get_posh_extractor()

    try:
        logger.info("Scraping Posh event: %s", url)
        event = await extractor.extract_event(url)

        if not event:
            logger.error("Failed to extract event from %s", url)
            sys.exit(1)

        # Output event data
        print(json.dumps(event_to_dict(event), indent=2))

        # Cache if requested
        if cache and event.start_time:
            event_cache = get_event_cache()
            event_cache.put(
                source=event.source,
                event_id=event.event_id,
                title=event.title,
                date=event.start_time.isoformat(),
                location=event.venue_address or event.venue_name or "TBD",
                category=event.category,
                description=event.description,
                is_free=event.is_free,
                price_amount=event.price_amount,
                url=event.url,
                logo_url=event.logo_url,
                raw_data=event.raw_data,
            )
            logger.info("Cached event: %s", event.event_id)

    finally:
        await extractor.close()


async def discover_posh_events(
    city: str,
    limit: int = 20,
    cache: bool = False,
    output_file: str | None = None,
) -> None:
    """Discover Posh events for a city."""
    extractor = get_posh_extractor()

    try:
        logger.info("Discovering Posh events for %s (limit: %d)", city, limit)
        events = await extractor.discover_events(city=city, limit=limit)

        if not events:
            logger.warning("No events found for %s", city)
            return

        logger.info("Found %d events", len(events))

        # Convert to dicts for output
        events_data = [event_to_dict(e) for e in events]

        # Output to file or stdout
        output = json.dumps(events_data, indent=2)
        if output_file:
            with open(output_file, "w") as f:
                f.write(output)
            logger.info("Wrote %d events to %s", len(events), output_file)
        else:
            print(output)

        # Cache if requested
        if cache:
            event_cache = get_event_cache()
            cached_count = 0
            for event in events:
                if event.start_time:
                    event_cache.put(
                        source=event.source,
                        event_id=event.event_id,
                        title=event.title,
                        date=event.start_time.isoformat(),
                        location=event.venue_address or event.venue_name or "TBD",
                        category=event.category,
                        description=event.description,
                        is_free=event.is_free,
                        price_amount=event.price_amount,
                        url=event.url,
                        logo_url=event.logo_url,
                        raw_data=event.raw_data,
                    )
                    cached_count += 1
            logger.info("Cached %d events", cached_count)

    finally:
        await extractor.close()


async def clear_cache(source: str | None = None) -> None:
    """Clear the event cache."""
    event_cache = get_event_cache()

    if source:
        count = event_cache.clear_source(source)
        logger.info("Cleared %d events from source: %s", count, source)
    else:
        count = event_cache.clear_all()
        logger.info("Cleared %d events from cache", count)


async def cache_stats() -> None:
    """Show cache statistics."""
    event_cache = get_event_cache()

    total = event_cache.count()
    posh = event_cache.count("posh")
    firecrawl = event_cache.count("firecrawl")
    eventbrite = event_cache.count("eventbrite")
    exa = event_cache.count("exa")

    print("Cache Statistics:")
    print(f"  Total events: {total}")
    print("  By source:")
    print(f"    posh: {posh}")
    print(f"    firecrawl: {firecrawl}")
    print(f"    eventbrite: {eventbrite}")
    print(f"    exa: {exa}")

    # Clear expired
    expired = event_cache.clear_expired()
    if expired > 0:
        print(f"  Expired entries cleared: {expired}")


def main() -> None:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Event scraping CLI for Calendar Club",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # posh-event command
    posh_event = subparsers.add_parser(
        "posh-event",
        help="Scrape a single Posh event",
    )
    posh_event.add_argument("url", help="Posh event URL")
    posh_event.add_argument(
        "--cache",
        action="store_true",
        help="Cache the scraped event",
    )

    # posh-discover command
    posh_discover = subparsers.add_parser(
        "posh-discover",
        help="Discover Posh events for a city",
    )
    posh_discover.add_argument("city", help="City slug (e.g., columbus, new-york)")
    posh_discover.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of events (default: 20)",
    )
    posh_discover.add_argument(
        "--cache",
        action="store_true",
        help="Cache discovered events",
    )
    posh_discover.add_argument(
        "-o", "--output",
        help="Output file path (default: stdout)",
    )

    # cache-clear command
    cache_clear = subparsers.add_parser(
        "cache-clear",
        help="Clear the event cache",
    )
    cache_clear.add_argument(
        "--source",
        help="Only clear events from this source",
    )

    # cache-stats command
    subparsers.add_parser(
        "cache-stats",
        help="Show cache statistics",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Run the appropriate command
    if args.command == "posh-event":
        asyncio.run(scrape_posh_event(args.url, cache=args.cache))
    elif args.command == "posh-discover":
        asyncio.run(
            discover_posh_events(
                city=args.city,
                limit=args.limit,
                cache=args.cache,
                output_file=args.output,
            )
        )
    elif args.command == "cache-clear":
        asyncio.run(clear_cache(source=args.source))
    elif args.command == "cache-stats":
        asyncio.run(cache_stats())


if __name__ == "__main__":
    main()

"""
Admin utility for TechRadar AI database.

Usage:
  python -m app.manage list              # show all published records
  python -m app.manage clear             # delete ALL published records (re-publish everything)
  python -m app.manage clear --date 2026-06-21   # delete records from specific date
  python -m app.manage stats             # DB stats
"""

import argparse
import sqlite3
import sys
from pathlib import Path


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def cmd_list(db_path: str, limit: int = 50):
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, source, score, published_at, channels, item_url FROM published_items ORDER BY published_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    if not rows:
        print("No published records.")
        return
    print(f"{'ID':>4}  {'Date':<20}  {'Score':>5}  {'Source':<18}  URL")
    print("-" * 90)
    for r in rows:
        print(f"{r['id']:>4}  {r['published_at'][:19]:<20}  {r['score']:>5}  {r['source']:<18}  {r['item_url'][:50]}")
    print(f"\nTotal: {len(rows)} record(s)")


def cmd_clear(db_path: str, date_filter: str | None = None):
    with _connect(db_path) as conn:
        if date_filter:
            n = conn.execute(
                "DELETE FROM published_items WHERE published_at LIKE ?", (f"{date_filter}%",)
            ).rowcount
            conn.execute(
                "DELETE FROM daily_count WHERE date = ?", (date_filter,)
            )
            print(f"Deleted {n} record(s) from {date_filter}")
        else:
            n = conn.execute("DELETE FROM published_items").rowcount
            conn.execute("DELETE FROM daily_count")
            print(f"Deleted all {n} published record(s) and reset daily counts")
    print("Done. Next pipeline run will re-publish these items.")


def cmd_stats(db_path: str):
    with _connect(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM published_items").fetchone()[0]
        by_source = conn.execute(
            "SELECT source, COUNT(*) as n FROM published_items GROUP BY source ORDER BY n DESC"
        ).fetchall()
        by_date = conn.execute(
            "SELECT date, count FROM daily_count ORDER BY date DESC LIMIT 7"
        ).fetchall()
        pending = conn.execute(
            "SELECT status, COUNT(*) as n FROM pending_items GROUP BY status"
        ).fetchall()

    print(f"Published items: {total}")
    print("\nBy source:")
    for r in by_source:
        print(f"  {r['source']:<20} {r['n']}")
    print("\nDaily counts (last 7 days):")
    for r in by_date:
        print(f"  {r['date']}  {r['count']} post(s)")
    if pending:
        print("\nPending items:")
        for r in pending:
            print(f"  {r['status']:<12} {r['n']}")


def main():
    parser = argparse.ArgumentParser(description="TechRadar AI — Database Admin")
    parser.add_argument("command", choices=["list", "clear", "stats"])
    parser.add_argument("--date", help="Filter by date YYYY-MM-DD (used with clear)")
    parser.add_argument("--db", default="./data/techradar.db", help="Path to SQLite DB")
    parser.add_argument("--limit", type=int, default=50, help="Max rows for list command")
    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"DB not found: {args.db}")
        sys.exit(1)

    if args.command == "list":
        cmd_list(args.db, args.limit)
    elif args.command == "clear":
        if not args.date:
            confirm = input("Delete ALL published records? This cannot be undone. [y/N] ")
            if confirm.lower() != "y":
                print("Cancelled.")
                return
        cmd_clear(args.db, args.date)
    elif args.command == "stats":
        cmd_stats(args.db)


if __name__ == "__main__":
    main()

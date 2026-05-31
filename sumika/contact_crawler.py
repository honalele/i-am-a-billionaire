#!/usr/bin/env python3
"""
Public business contact crawler for Sumika ai outreach.

This script only crawls public pages from seed company websites. It respects
robots.txt, rate limits requests, and does not bypass login walls, CAPTCHAs,
or search-engine restrictions.
"""

from __future__ import annotations

import argparse
import csv
import html
import re
import time
from collections import deque
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib import robotparser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


USER_AGENT = "SumikaAIContactResearch/0.1 (+https://sumika-ai.vercel.app)"
CONTACT_KEYWORDS = (
    "contact",
    "inquiry",
    "mail",
    "toiawase",
    "otoiawase",
    "お問い合わせ",
    "問合せ",
    "お問合せ",
    "相談",
    "会社概要",
)
SNS_DOMAINS = (
    "x.com",
    "twitter.com",
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "line.me",
    "page.line.me",
    "youtube.com",
)
EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+81[-\s]?\d{1,4}[-\s]\d{1,4}[-\s]\d{3,4}|0\d{1,4}-\d{1,4}-\d{3,4})(?!\d)"
)
BAD_EMAIL_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")
BAD_EMAIL_PARTS = (
    "example",
    "sample",
    "xxxxx",
    "dummy",
    "test",
    "noreply",
    "no-reply",
    "email@domain.com",
    "info@mail.com",
)


@dataclass
class PageData:
    title: str = ""
    text: str = ""
    links: list[tuple[str, str]] = field(default_factory=list)


class ContactHTMLParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.data = PageData()
        self._current_href: str | None = None
        self._current_text: list[str] = []
        self._in_title = False
        self._title_parts: list[str] = []
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "title":
            self._in_title = True
        if tag.lower() == "a":
            self._current_href = attrs_dict.get("href")
            self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
        if self._current_href is not None:
            self._current_text.append(data)
        self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False
        if tag.lower() == "a" and self._current_href:
            text = " ".join(part.strip() for part in self._current_text if part.strip())
            href = urljoin(self.base_url, html.unescape(self._current_href))
            self.data.links.append((href, html.unescape(text)))
            self._current_href = None
            self._current_text = []

    def close(self) -> None:
        super().close()
        self.data.title = " ".join(part.strip() for part in self._title_parts if part.strip())
        self.data.text = " ".join(part.strip() for part in self._text_parts if part.strip())


class RobotsCache:
    def __init__(self) -> None:
        self._cache: dict[str, robotparser.RobotFileParser] = {}

    def allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False

        root = f"{parsed.scheme}://{parsed.netloc}"
        if root not in self._cache:
            rp = robotparser.RobotFileParser()
            rp.set_url(urljoin(root, "/robots.txt"))
            try:
                rp.read()
            except Exception:
                # If robots.txt cannot be fetched, stay conservative but useful.
                return True
            self._cache[root] = rp

        return self._cache[root].can_fetch(USER_AGENT, url)


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl()


def same_site(url: str, root_host: str) -> bool:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return host == root_host or host.endswith("." + root_host)


def fetch_page(url: str, timeout: int) -> str | None:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            if "text/html" not in content_type and "application/xhtml" not in content_type:
                return None
            charset = response.headers.get_content_charset() or "utf-8"
            content = response.read(1_500_000)
            try:
                return content.decode(charset, errors="replace")
            except LookupError:
                return content.decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError, ValueError):
        return None


def parse_page(url: str, markup: str) -> PageData:
    parser = ContactHTMLParser(url)
    parser.feed(markup)
    parser.close()
    return parser.data


def clean_emails(text: str) -> set[str]:
    emails = {email.strip(".,;:()[]{}<>\"'").lower() for email in EMAIL_RE.findall(text)}
    return {
        email
        for email in emails
        if not email.endswith(BAD_EMAIL_SUFFIXES)
        and not any(bad in email for bad in BAD_EMAIL_PARTS)
    }


def clean_phones(text: str) -> set[str]:
    phones = {phone.strip() for phone in PHONE_RE.findall(text)}
    clean: set[str] = set()
    for phone in phones:
        digits = re.sub(r"\D", "", phone)
        has_separator = "-" in phone or " " in phone or phone.startswith("+81")
        plausible_length = 9 <= len(digits) <= 11 or (
            phone.startswith("+81") and 11 <= len(digits) <= 13
        )
        if plausible_length and has_separator:
            clean.add(phone)
    return clean


def is_sns_url(url: str) -> bool:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return any(host == domain or host.endswith("." + domain) for domain in SNS_DOMAINS)


def looks_like_contact_link(url: str, label: str) -> bool:
    haystack = (url + " " + label).lower()
    return any(keyword.lower() in haystack for keyword in CONTACT_KEYWORDS)


def rank_links(links: Iterable[tuple[str, str]], root_host: str) -> list[str]:
    internal: list[str] = []
    contact: list[str] = []
    seen: set[str] = set()

    for url, label in links:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            continue
        clean = parsed._replace(fragment="").geturl()
        if clean in seen or not same_site(clean, root_host):
            continue
        seen.add(clean)
        if looks_like_contact_link(clean, label):
            contact.append(clean)
        else:
            internal.append(clean)

    return contact + internal


def crawl_site(
    seed_url: str,
    robots: RobotsCache,
    max_pages: int,
    delay: float,
    timeout: int,
) -> dict[str, str]:
    seed_url = normalize_url(seed_url)
    parsed = urlparse(seed_url)
    root_host = parsed.netloc.lower().removeprefix("www.")

    queue: deque[str] = deque([seed_url])
    seen: set[str] = set()
    emails: set[str] = set()
    phones: set[str] = set()
    sns_links: set[str] = set()
    contact_urls: set[str] = set()
    source_pages: set[str] = set()
    title = ""

    while queue and len(seen) < max_pages:
        url = queue.popleft()
        if url in seen:
            continue
        seen.add(url)

        if not robots.allowed(url):
            continue

        markup = fetch_page(url, timeout=timeout)
        time.sleep(delay)
        if not markup:
            continue

        page = parse_page(url, markup)
        title = title or page.title
        page_text = html.unescape(markup + " " + page.text)

        found_emails = clean_emails(page_text)
        found_phones = clean_phones(page_text)
        if found_emails or found_phones:
            source_pages.add(url)

        emails.update(found_emails)
        phones.update(found_phones)

        for href, label in page.links:
            if href.startswith("mailto:"):
                emails.update(clean_emails(href.replace("mailto:", "")))
            elif is_sns_url(href):
                sns_links.add(href)
            elif looks_like_contact_link(href, label):
                contact_urls.add(href)

        for next_url in rank_links(page.links, root_host):
            if next_url not in seen and len(seen) + len(queue) < max_pages * 3:
                queue.append(next_url)

    return {
        "会社名": title,
        "都市": "",
        "セグメント": "",
        "Webサイト": seed_url,
        "問い合わせURL": " | ".join(sorted(contact_urls)),
        "メールアドレス": " | ".join(sorted(emails)),
        "電話番号": " | ".join(sorted(phones)),
        "意思決定者": "",
        "流入元": "company website",
        "課題シグナル": "",
        "優先度": "",
        "ステータス": "未連絡",
        "最終連絡日": "",
        "次回フォロー日": "",
        "メモ": "SNS: " + " | ".join(sorted(sns_links)) if sns_links else "",
        "取得元ページ": " | ".join(sorted(source_pages)),
    }


def read_seed_urls(path: Path, url_column: str) -> list[str]:
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            urls = [row.get(url_column, "") for row in reader]
    else:
        urls = [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    return [url for url in (normalize_url(url) for url in urls) if url]


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    columns = [
        "会社名",
        "都市",
        "セグメント",
        "Webサイト",
        "問い合わせURL",
        "メールアドレス",
        "電話番号",
        "意思決定者",
        "流入元",
        "課題シグナル",
        "優先度",
        "ステータス",
        "最終連絡日",
        "次回フォロー日",
        "メモ",
        "取得元ページ",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Crawl public company websites for contact info.")
    parser.add_argument("--seeds", default="seed_urls.txt", help="Text file or CSV containing company website URLs.")
    parser.add_argument("--url-column", default="Webサイト", help="CSV column name to read URLs from.")
    parser.add_argument("--output", default="sumika_contacts.csv", help="Output CSV path.")
    parser.add_argument("--limit", type=int, default=50, help="Stop after this many rows with email or SNS.")
    parser.add_argument("--max-pages-per-site", type=int, default=6, help="Maximum pages to crawl per company site.")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests in seconds.")
    parser.add_argument("--timeout", type=int, default=10, help="Request timeout in seconds.")
    args = parser.parse_args()

    seed_path = Path(args.seeds)
    if not seed_path.exists():
        raise SystemExit(f"Seed file not found: {seed_path}")

    seed_urls = read_seed_urls(seed_path, args.url_column)
    robots = RobotsCache()
    rows: list[dict[str, str]] = []

    for index, seed_url in enumerate(seed_urls, start=1):
        print(f"[{index}/{len(seed_urls)}] Crawling {seed_url}")
        row = crawl_site(
            seed_url,
            robots=robots,
            max_pages=args.max_pages_per_site,
            delay=args.delay,
            timeout=args.timeout,
        )
        has_contact = bool(row["メールアドレス"] or row["メモ"])
        if has_contact:
            rows.append(row)
            print(f"  found contact ({len(rows)}/{args.limit})")
        else:
            print("  no email or SNS found")

        if len(rows) >= args.limit:
            break

    write_rows(Path(args.output), rows)
    print(f"Wrote {len(rows)} rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import logging
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

LOGGER = logging.getLogger("realtor_agents_scraper.realtor_parser")

@dataclass
class AgentProfile:
    first_year: Optional[int] = None
    description: Optional[str] = None
    phones: Optional[List[Dict[str, Any]]] = None
    review_count: Optional[int] = None
    office: Optional[Dict[str, Any]] = None
    agent_rating: Optional[float] = None
    address: Optional[Dict[str, Any]] = None
    specializations: Optional[List[str]] = None
    broker: Optional[Dict[str, Any]] = None
    recommendations: Optional[List[Dict[str, Any]]] = None
    reviews: Optional[List[Dict[str, Any]]] = None
    for_sale_price: Optional[Dict[str, Any]] = None
    recently_sold: Optional[Dict[str, Any]] = None
    experience: Optional[str] = None
    web_url: Optional[str] = None
    advertiser_id: Optional[str] = None
    title: Optional[str] = None
    photo: Optional[str] = None

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

class RealtorAgentScraper:
    def __init__(
        self,
        base_url: str = "https://www.realtor.com",
        full_agent_details: bool = False,
        monitoring_mode: bool = False,
        timeout: int = 15,
        max_retries: int = 3,
        backoff_factor: float = 0.8,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.full_agent_details = full_agent_details
        self.monitoring_mode = monitoring_mode
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            }
        )

    # ------------- Public API -------------

    def scrape_from_urls(self, urls: Iterable[str], limit: Optional[int] = None) -> List[Dict[str, Any]]:
        all_agents: List[Dict[str, Any]] = []
        count = 0

        for url in urls:
            if limit is not None and count >= limit:
                break

            url = url.strip()
            if not url:
                continue

            LOGGER.info("Processing URL: %s", url)
            if self._looks_like_agent_profile(url):
                agent = self._scrape_agent_profile(url)
                if agent:
                    all_agents.append(agent)
                    count += 1
            else:
                agents_from_listing = self._scrape_listing(url, limit=limit, current_count=count)
                all_agents.extend(agents_from_listing)
                count = len(all_agents)
                if limit is not None and count >= limit:
                    break

        return all_agents

    # ------------- Core scraping logic -------------

    def _get_with_retries(self, url: str) -> Optional[requests.Response]:
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                LOGGER.debug("GET %s (attempt %d)", url, attempt)
                resp = self.session.get(url, timeout=self.timeout)
                if resp.status_code >= 400:
                    LOGGER.warning("Received HTTP %s for %s", resp.status_code, url)
                else:
                    return resp
            except Exception as exc:
                last_exc = exc
                LOGGER.warning("Request error for %s: %s", url, exc)

            sleep_time = self.backoff_factor * attempt
            LOGGER.debug("Sleeping %.2fs before retry", sleep_time)
            time.sleep(sleep_time)

        LOGGER.error("Failed to fetch %s after %d attempts: %s", url, self.max_retries, last_exc)
        return None

    def _scrape_listing(
        self,
        url: str,
        limit: Optional[int],
        current_count: int,
    ) -> List[Dict[str, Any]]:
        resp = self._get_with_retries(url)
        if resp is None:
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        agent_links = self._extract_agent_links_from_listing(soup)
        LOGGER.info("Found %d potential agent links on listing page", len(agent_links))

        agents: List[Dict[str, Any]] = []
        for agent_url in agent_links:
            if limit is not None and current_count + len(agents) >= limit:
                break
            agent_data = self._scrape_agent_profile(agent_url)
            if agent_data:
                agents.append(agent_data)

        return agents

    def _scrape_agent_profile(self, url: str) -> Optional[Dict[str, Any]]:
        resp = self._get_with_retries(url)
        if resp is None:
            return None

        soup = BeautifulSoup(resp.text, "lxml")

        profile = AgentProfile()
        profile.web_url = url

        try:
            self._parse_basic_info(soup, profile)
            self._parse_office_and_address(soup, profile)
            self._parse_reviews_and_ratings(soup, profile)
            self._parse_activity_blocks(soup, profile)

            if self.full_agent_details:
                self._parse_detailed_sections(soup, profile)
        except Exception as exc:
            LOGGER.warning("Error parsing agent profile %s: %s", url, exc, exc_info=False)

        data = {k: v for k, v in asdict(profile).items() if v not in (None, [], {})}
        if not data:
            LOGGER.warning("Parsed empty agent profile from %s", url)
            return None

        return data

    # ------------- HTML parsing helpers -------------

    def _parse_basic_info(self, soup: BeautifulSoup, profile: AgentProfile) -> None:
        # Name / title
        name_el = soup.select_one("h1, h1[data-testid='profile-name']")
        if name_el:
            profile.title = name_el.get_text(strip=True)

        # Description / bio
        desc_el = soup.select_one("[data-testid='agent-description'], .agent-description, .bio")
        if desc_el:
            profile.description = " ".join(desc_el.get_text(" ", strip=True).split())

        # Photo
        photo_el = soup.select_one("img[src*='ap.rdcpix.com'], img[alt*='agent photo']")
        if photo_el and photo_el.get("src"):
            profile.photo = photo_el["src"]

        # First year / experience
        exp_el = soup.find(string=lambda s: isinstance(s, str) and "Years in Business" in s)
        if exp_el and exp_el.parent:
            # Very rough heuristic around content structure
            parent_text = exp_el.parent.get_text(" ", strip=True)
            profile.experience = parent_text

        # Phones
        phones: List[Dict[str, Any]] = []
        for node in soup.select("[data-testid='phone'], .agent-phone, a[href^='tel:']"):
            text = node.get_text(" ", strip=True)
            number = text
            phone_type = None
            if "mobile" in text.lower():
                phone_type = "Mobile"
            elif "office" in text.lower():
                phone_type = "Office"
            elif "fax" in text.lower():
                phone_type = "Fax"
            phones.append(
                {
                    "number": number,
                    "type": phone_type,
                }
            )
        if phones:
            profile.phones = phones

    def _parse_office_and_address(self, soup: BeautifulSoup, profile: AgentProfile) -> None:
        # Office info block
        office_block = soup.select_one("[data-testid='office-info'], .office-info, .brokerage")
        office: Dict[str, Any] = {}
        if office_block:
            name_el = office_block.find("h2") or office_block.find("h3")
            if name_el:
                office["name"] = name_el.get_text(strip=True)

            website_el = office_block.find("a", href=True)
            if website_el:
                office["website"] = website_el["href"]

            address_text = office_block.get_text(" ", strip=True)
            if address_text:
                office["raw_address"] = " ".join(address_text.split())

        # Address
        addr_el = soup.select_one("[data-testid='address'], .agent-address, address")
        if addr_el:
            addr_text = " ".join(addr_el.get_text(" ", strip=True).split())
            profile.address = {"raw": addr_text}

        if office:
            profile.office = office

    def _parse_reviews_and_ratings(self, soup: BeautifulSoup, profile: AgentProfile) -> None:
        # Rating score
        rating_el = soup.select_one("[data-testid='rating'], .rating-value, .review-rating")
        if rating_el:
            rating_text = rating_el.get_text(strip=True)
            try:
                profile.agent_rating = float(rating_text.split()[0])
            except ValueError:
                pass

        # Review count
        review_count_el = soup.find(string=lambda s: isinstance(s, str) and "review" in s.lower())
        if review_count_el:
            text = review_count_el.strip()
            digits = "".join(ch for ch in text if ch.isdigit())
            if digits:
                try:
                    profile.review_count = int(digits)
                except ValueError:
                    pass

    def _parse_activity_blocks(self, soup: BeautifulSoup, profile: AgentProfile) -> None:
        # Recently sold summary (heuristic)
        sold_el = soup.find(string=lambda s: isinstance(s, str) and "recently sold" in s.lower())
        if sold_el:
            text = sold_el.strip()
            digits = "".join(ch for ch in text if ch.isdigit())
            if digits:
                try:
                    profile.recently_sold = {"count": int(digits)}
                except ValueError:
                    pass

        # For sale price range (very heuristic)
        for_sale_el = soup.find(string=lambda s: isinstance(s, str) and "for sale" in s.lower())
        if for_sale_el:
            text = for_sale_el.strip()
            # We just keep raw text; cleaning module can refine this
            profile.for_sale_price = {"raw": text}

    def _parse_detailed_sections(self, soup: BeautifulSoup, profile: AgentProfile) -> None:
        # Specializations
        specs: List[str] = []
        for label in soup.select("[data-testid='specialties'] li, .specialties li"):
            val = label.get_text(strip=True)
            if val:
                specs.append(val)
        if specs:
            profile.specializations = specs

        # Reviews and recommendations listing (simplified)
        reviews: List[Dict[str, Any]] = []
        for rev_el in soup.select("[data-testid='review'], .review-card"):
            rating_el = rev_el.select_one(".rating, [data-testid='rating']")
            comment_el = rev_el.select_one("p, .comment, .review-text")
            rating_val: Optional[float] = None
            if rating_el:
                text = rating_el.get_text(strip=True)
                try:
                    rating_val = float(text.split()[0])
                except ValueError:
                    rating_val = None
            comment_text = comment_el.get_text(" ", strip=True) if comment_el else None
            reviews.append(
                {
                    "rating": rating_val,
                    "comment": comment_text,
                }
            )
        if reviews:
            profile.reviews = reviews

    # ------------- URL / link helpers -------------

    def _looks_like_agent_profile(self, url: str) -> bool:
        parsed = urlparse(url.lower())
        path = parsed.path
        return "realestateagents" in path or "/agents/" in path

    def _extract_agent_links_from_listing(self, soup: BeautifulSoup) -> List[str]:
        links: List[str] = []
        candidates = soup.select("a[href*='realestateagents'], a[href*='/agents/']")
        for a in candidates:
            href = a.get("href")
            if not href:
                continue
            full_url = urljoin(self.base_url, href)
            if full_url not in links:
                links.append(full_url)
        return links

def quick_scrape(urls: Iterable[str], limit: Optional[int] = None) -> List[Dict[str, Any]]:
    scraper = RealtorAgentScraper()
    return scraper.scrape_from_urls(urls, limit=limit)
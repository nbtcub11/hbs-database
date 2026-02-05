"""Web scraper for HBS faculty and executive fellows data."""

import requests
from bs4 import BeautifulSoup
import json
import re
import time
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

# HBS Unit URLs
UNIT_URLS = {
    "Accounting & Management": "https://www.hbs.edu/faculty/units/am/Pages/default.aspx",
    "Business, Government & International Economy": "https://www.hbs.edu/faculty/units/bgie/Pages/default.aspx",
    "Entrepreneurial Management": "https://www.hbs.edu/faculty/units/em/Pages/default.aspx",
    "Finance": "https://www.hbs.edu/faculty/units/finance/Pages/default.aspx",
    "General Management": "https://www.hbs.edu/faculty/units/gmp/Pages/default.aspx",
    "Marketing": "https://www.hbs.edu/faculty/units/marketing/Pages/default.aspx",
    "Negotiation, Organizations & Markets": "https://www.hbs.edu/faculty/units/nom/Pages/default.aspx",
    "Organizational Behavior": "https://www.hbs.edu/faculty/units/ob/Pages/default.aspx",
    "Strategy": "https://www.hbs.edu/faculty/units/strategy/Pages/default.aspx",
    "Technology & Operations Management": "https://www.hbs.edu/faculty/units/tom/Pages/default.aspx",
}

FELLOWS_URL = "https://www.hbs.edu/news/releases/Pages/2025-2026-executive-fellows.aspx"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}


def generate_email(name):
    """Generate likely HBS email from name."""
    # Clean and split name
    name = name.strip()
    # Remove titles
    name = re.sub(r'^(Dr\.|Prof\.|Professor)\s+', '', name)
    # Handle suffixes
    name = re.sub(r',?\s+(Jr\.|Sr\.|III|II|IV|PhD|DBA)$', '', name)

    parts = name.lower().split()
    if len(parts) >= 2:
        first = parts[0]
        last = parts[-1]
        return f"{first}_{last}@hbs.edu"
    return None


def construct_linkedin_url(name):
    """Construct a LinkedIn search URL from a name."""
    if not name:
        return None
    # Clean name
    name = name.strip()
    name = re.sub(r'^(Dr\.|Prof\.|Professor)\s+', '', name)
    name = re.sub(r',?\s+(Jr\.|Sr\.|III|II|IV|PhD|DBA)$', '', name)

    # Use LinkedIn search URL which always works
    from urllib.parse import quote
    return f"https://www.linkedin.com/search/results/all/?keywords={quote(name)}"


def generate_fellow_bio(fellow_data):
    """Generate a 2-sentence bio for a fellow based on available data."""
    name = fellow_data.get('name', '')
    title = fellow_data.get('title', '')
    organization = fellow_data.get('organization', '')
    mba_year = fellow_data.get('mba_year', '')
    tags = fellow_data.get('tags', [])

    # First sentence: role and organization
    if organization:
        sentence1 = f"{name} is {title} at {organization}."
    else:
        sentence1 = f"{name} is {title}."

    # Second sentence: MBA year and/or expertise
    expertise_tags = [t['name'] for t in tags if t.get('category') == 'expertise']
    industry_tags = [t['name'] for t in tags if t.get('category') == 'industry']

    if mba_year and expertise_tags:
        sentence2 = f"A {mba_year} HBS graduate, they bring expertise in {', '.join(expertise_tags[:3])}."
    elif mba_year:
        sentence2 = f"They are a {mba_year} HBS graduate."
    elif expertise_tags and industry_tags:
        sentence2 = f"They bring expertise in {', '.join(expertise_tags[:2])} within the {industry_tags[0].lower()} sector."
    elif expertise_tags:
        sentence2 = f"They bring expertise in {', '.join(expertise_tags[:3])}."
    elif industry_tags:
        sentence2 = f"They have extensive experience in the {industry_tags[0].lower()} industry."
    else:
        sentence2 = "They serve as an HBS Executive Fellow."

    return f"{sentence1} {sentence2}"


def scrape_faculty_bio(profile_url):
    """Scrape the bio/about section from a faculty profile page."""
    if not profile_url:
        return None

    try:
        response = requests.get(profile_url, headers=HEADERS, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"  Error fetching profile {profile_url}: {e}")
        return None

    soup = BeautifulSoup(response.text, 'lxml')

    # Try to find the bio/about section
    # HBS profile pages typically have an "About" section
    bio_text = None

    # Look for About section
    about_section = soup.find(['div', 'section'], class_=re.compile(r'about|bio|overview', re.I))
    if about_section:
        bio_text = about_section.get_text(separator=' ', strip=True)

    # Try finding by heading
    if not bio_text:
        for heading in soup.find_all(['h2', 'h3', 'h4']):
            if heading.get_text(strip=True).lower() in ['about', 'biography', 'bio', 'overview']:
                # Get the content after this heading
                next_elem = heading.find_next_sibling(['p', 'div'])
                if next_elem:
                    bio_text = next_elem.get_text(separator=' ', strip=True)
                    break

    # Try finding in page content area
    if not bio_text:
        content_area = soup.find('div', class_=re.compile(r'content|main|body', re.I))
        if content_area:
            # Find first substantial paragraph
            paragraphs = content_area.find_all('p')
            for p in paragraphs:
                text = p.get_text(strip=True)
                if len(text) > 100:  # Substantial paragraph
                    bio_text = text
                    break

    # Truncate to 2 sentences if we found something
    if bio_text:
        # Clean up the text
        bio_text = re.sub(r'\s+', ' ', bio_text).strip()
        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', bio_text)
        if len(sentences) > 2:
            bio_text = ' '.join(sentences[:2])
        # Limit length
        if len(bio_text) > 500:
            bio_text = bio_text[:497] + '...'

    return bio_text


def extract_keywords(text):
    """Extract keywords from text for tagging."""
    if not text:
        return []

    keywords = []
    text_lower = text.lower()

    # Industry keywords
    industry_keywords = {
        'technology': ['technology', 'tech', 'software', 'digital', 'ai', 'artificial intelligence', 'machine learning'],
        'finance': ['finance', 'financial', 'banking', 'investment', 'private equity', 'venture capital', 'fintech'],
        'healthcare': ['healthcare', 'health', 'medical', 'pharmaceutical', 'biotech', 'life sciences'],
        'retail': ['retail', 'consumer', 'e-commerce', 'cpg', 'consumer goods'],
        'manufacturing': ['manufacturing', 'industrial', 'supply chain', 'operations'],
        'energy': ['energy', 'oil', 'gas', 'renewable', 'sustainability', 'clean energy'],
        'media': ['media', 'entertainment', 'publishing', 'content', 'streaming'],
        'real estate': ['real estate', 'property', 'construction'],
    }

    # Expertise keywords
    expertise_keywords = {
        'leadership': ['leadership', 'leader', 'ceo', 'executive', 'management'],
        'strategy': ['strategy', 'strategic', 'corporate strategy'],
        'entrepreneurship': ['entrepreneur', 'startup', 'founder', 'venture'],
        'marketing': ['marketing', 'brand', 'advertising', 'customer'],
        'operations': ['operations', 'supply chain', 'logistics', 'manufacturing'],
        'innovation': ['innovation', 'r&d', 'research', 'development', 'product'],
        'international': ['international', 'global', 'emerging markets', 'china', 'asia', 'europe'],
        'governance': ['governance', 'board', 'corporate governance', 'compliance'],
        'transformation': ['transformation', 'turnaround', 'restructuring', 'change management'],
        'sustainability': ['sustainability', 'esg', 'climate', 'environmental', 'social impact'],
    }

    for category, terms in industry_keywords.items():
        for term in terms:
            if term in text_lower:
                keywords.append({'name': category.title(), 'category': 'industry'})
                break

    for category, terms in expertise_keywords.items():
        for term in terms:
            if term in text_lower:
                keywords.append({'name': category.title(), 'category': 'expertise'})
                break

    return keywords


def scrape_fellows():
    """Scrape executive fellows from the HBS news page."""
    print(f"Fetching executive fellows from {FELLOWS_URL}")

    try:
        response = requests.get(FELLOWS_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching fellows page: {e}")
        return []

    soup = BeautifulSoup(response.text, 'lxml')
    fellows = []

    # Find the main content area
    content = soup.find('div', class_='page-content') or soup.find('article') or soup.find('main')
    if not content:
        content = soup

    # Look for fellow entries - they typically have names in bold or headings
    # followed by their details

    # Try to find structured data first
    fellow_entries = content.find_all(['p', 'div', 'li'])

    current_fellow = None

    for entry in fellow_entries:
        text = entry.get_text(strip=True)

        # Skip empty or very short entries
        if len(text) < 10:
            continue

        # Look for patterns like "Name, Title at Company" or "Name (MBA Year)"
        # Common patterns:
        # "John Smith, CEO of Company (MBA 1995)"
        # "Jane Doe (MBA 2000), President at Firm"

        # Check if this looks like a fellow entry
        mba_match = re.search(r'\(MBA\s*\'?(\d{2,4})\)', text)

        if mba_match:
            # This looks like a fellow entry
            mba_year = mba_match.group(1)
            if len(mba_year) == 2:
                mba_year = '19' + mba_year if int(mba_year) > 50 else '20' + mba_year

            # Try to extract name (usually at the beginning)
            # Remove the MBA part first
            clean_text = re.sub(r'\s*\(MBA\s*\'?\d{2,4}\)\s*', ' ', text)

            # Split by common delimiters
            parts = re.split(r',\s*|\s+at\s+|\s+of\s+|\s+–\s+|\s+-\s+', clean_text)

            if parts:
                name = parts[0].strip()
                # Clean up name
                name = re.sub(r'^[\d\.\)\s]+', '', name)  # Remove leading numbers/bullets
                name = name.strip()

                if len(name) > 3 and len(name) < 50:  # Reasonable name length
                    # Extract title and organization
                    title = ''
                    organization = ''

                    if len(parts) > 1:
                        # Second part is usually title or organization
                        remaining = ', '.join(parts[1:])
                        # Try to split title from organization
                        if ' at ' in remaining.lower():
                            title_org = remaining.lower().split(' at ', 1)
                            title = title_org[0].strip()
                            organization = title_org[1].strip() if len(title_org) > 1 else ''
                        elif ' of ' in remaining.lower():
                            title_org = remaining.lower().split(' of ', 1)
                            title = title_org[0].strip()
                            organization = title_org[1].strip() if len(title_org) > 1 else ''
                        else:
                            # Assume first part is title, rest is organization
                            title = parts[1].strip() if len(parts) > 1 else ''
                            organization = parts[2].strip() if len(parts) > 2 else ''

                    fellow = {
                        'name': name,
                        'title': title.title() if title else 'Executive Fellow',
                        'organization': organization.title() if organization else '',
                        'mba_year': mba_year,
                        'type': 'fellow',
                        'profile_url': FELLOWS_URL,
                        'tags': extract_keywords(text)
                    }

                    # Add Executive Fellow tag
                    fellow['tags'].append({'name': 'Executive Fellow', 'category': 'role'})

                    # Generate bio
                    fellow['bio'] = generate_fellow_bio(fellow)

                    # Construct LinkedIn URL
                    fellow['linkedin_url'] = construct_linkedin_url(name)

                    fellows.append(fellow)

    print(f"Found {len(fellows)} executive fellows")
    return fellows


def scrape_faculty_unit(unit_name, unit_url):
    """Scrape faculty from a specific unit page."""
    print(f"Fetching {unit_name} faculty from {unit_url}")

    try:
        response = requests.get(unit_url, headers=HEADERS, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching {unit_name}: {e}")
        return []

    soup = BeautifulSoup(response.text, 'lxml')
    faculty = []

    # Look for faculty profile links - HBS uses consistent URL patterns
    # Faculty profiles are at /faculty/Pages/profile.aspx?facId=XXX
    profile_links = soup.find_all('a', href=re.compile(r'/faculty/Pages/profile\.aspx'))

    seen_urls = set()

    for link in profile_links:
        href = link.get('href', '')
        if href in seen_urls:
            continue
        seen_urls.add(href)

        # Make absolute URL
        if href.startswith('/'):
            profile_url = f"https://www.hbs.edu{href}"
        else:
            profile_url = href

        # Get name from link text
        name = link.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Try to find associated image
        image_url = None
        parent = link.find_parent(['div', 'li', 'td'])
        if parent:
            img = parent.find('img')
            if img and img.get('src'):
                img_src = img.get('src')
                if img_src.startswith('/'):
                    image_url = f"https://www.hbs.edu{img_src}"
                else:
                    image_url = img_src

        # Try to find title
        title = ''
        if parent:
            # Look for title text near the name
            text = parent.get_text(separator=' ', strip=True)
            # Remove the name from the text
            title_text = text.replace(name, '').strip()
            # Common title patterns
            title_match = re.search(r'(Professor|Associate Professor|Assistant Professor|Senior Lecturer|Lecturer|Visiting|Emeritus)[^,]*', title_text, re.IGNORECASE)
            if title_match:
                title = title_match.group(0).strip()

        faculty_member = {
            'name': name,
            'title': title or 'Faculty',
            'unit': unit_name,
            'type': 'faculty',
            'profile_url': profile_url,
            'image_url': image_url,
            'email': generate_email(name),
            'tags': [{'name': unit_name, 'category': 'unit'}]
        }

        faculty.append(faculty_member)

    # Also try to find faculty from the directory/listing sections
    # Sometimes they're in tables or lists
    faculty_sections = soup.find_all(['table', 'ul', 'div'], class_=re.compile(r'faculty|directory|listing|people', re.I))

    for section in faculty_sections:
        rows = section.find_all(['tr', 'li', 'div'], recursive=True)
        for row in rows:
            links = row.find_all('a', href=re.compile(r'profile|faculty', re.I))
            for link in links:
                href = link.get('href', '')
                if href in seen_urls or not href:
                    continue
                seen_urls.add(href)

                name = link.get_text(strip=True)
                if not name or len(name) < 3 or len(name) > 100:
                    continue

                if href.startswith('/'):
                    profile_url = f"https://www.hbs.edu{href}"
                else:
                    profile_url = href

                faculty_member = {
                    'name': name,
                    'title': 'Faculty',
                    'unit': unit_name,
                    'type': 'faculty',
                    'profile_url': profile_url,
                    'email': generate_email(name),
                    'tags': [{'name': unit_name, 'category': 'unit'}]
                }
                faculty.append(faculty_member)

    print(f"Found {len(faculty)} faculty in {unit_name}")
    return faculty


def scrape_faculty_directory():
    """Scrape the main faculty directory."""
    directory_url = "https://www.hbs.edu/faculty/Pages/browse.aspx"
    print(f"Fetching faculty directory from {directory_url}")

    try:
        response = requests.get(directory_url, headers=HEADERS, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching faculty directory: {e}")
        return []

    soup = BeautifulSoup(response.text, 'lxml')
    faculty = []
    seen_names = set()

    # Find all faculty links
    profile_links = soup.find_all('a', href=re.compile(r'/faculty/Pages/profile\.aspx|facId='))

    for link in profile_links:
        name = link.get_text(strip=True)
        if not name or len(name) < 3 or name in seen_names:
            continue

        seen_names.add(name)
        href = link.get('href', '')

        if href.startswith('/'):
            profile_url = f"https://www.hbs.edu{href}"
        else:
            profile_url = href

        # Try to get more info from parent element
        title = ''
        unit = ''
        parent = link.find_parent(['div', 'li', 'tr'])
        if parent:
            text = parent.get_text(separator='|', strip=True)
            parts = text.split('|')
            for part in parts:
                part = part.strip()
                if part == name:
                    continue
                if any(t in part.lower() for t in ['professor', 'lecturer', 'emeritus']):
                    title = part
                elif part in UNIT_URLS.keys():
                    unit = part

        faculty_member = {
            'name': name,
            'title': title or 'Faculty',
            'unit': unit,
            'type': 'faculty',
            'profile_url': profile_url,
            'email': generate_email(name),
            'tags': []
        }

        if unit:
            faculty_member['tags'].append({'name': unit, 'category': 'unit'})

        faculty.append(faculty_member)

    print(f"Found {len(faculty)} faculty in directory")
    return faculty


def scrape_all_faculty(fetch_bios=True):
    """Scrape faculty from all unit pages."""
    all_faculty = []
    seen_names = set()

    # First try the main directory
    directory_faculty = scrape_faculty_directory()
    for f in directory_faculty:
        if f['name'] not in seen_names:
            seen_names.add(f['name'])
            all_faculty.append(f)

    time.sleep(1)  # Be nice to the server

    # Then scrape each unit for additional details
    for unit_name, unit_url in UNIT_URLS.items():
        unit_faculty = scrape_faculty_unit(unit_name, unit_url)
        for f in unit_faculty:
            if f['name'] not in seen_names:
                seen_names.add(f['name'])
                all_faculty.append(f)
            else:
                # Update existing entry with unit info if missing
                for existing in all_faculty:
                    if existing['name'] == f['name'] and not existing.get('unit'):
                        existing['unit'] = unit_name
                        if not any(t.get('name') == unit_name for t in existing.get('tags', [])):
                            existing.setdefault('tags', []).append({'name': unit_name, 'category': 'unit'})

        time.sleep(1)  # Be nice to the server

    # Fetch bios for each faculty member
    if fetch_bios:
        print(f"\n📝 Fetching bios for {len(all_faculty)} faculty members...")
        for i, faculty in enumerate(all_faculty):
            if faculty.get('profile_url') and not faculty.get('bio'):
                print(f"  [{i+1}/{len(all_faculty)}] Fetching bio for {faculty['name']}...")
                bio = scrape_faculty_bio(faculty['profile_url'])
                if bio:
                    faculty['bio'] = bio
                time.sleep(1)  # Rate limit

    return all_faculty


def save_data(faculty, fellows):
    """Save scraped data to JSON files."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    faculty_path = DATA_DIR / "faculty.json"
    with open(faculty_path, 'w') as f:
        json.dump(faculty, f, indent=2)
    print(f"Saved {len(faculty)} faculty to {faculty_path}")

    fellows_path = DATA_DIR / "fellows.json"
    with open(fellows_path, 'w') as f:
        json.dump(fellows, f, indent=2)
    print(f"Saved {len(fellows)} fellows to {fellows_path}")


def load_data():
    """Load data from JSON files."""
    faculty = []
    fellows = []

    faculty_path = DATA_DIR / "faculty.json"
    if faculty_path.exists():
        with open(faculty_path) as f:
            faculty = json.load(f)

    fellows_path = DATA_DIR / "fellows.json"
    if fellows_path.exists():
        with open(fellows_path) as f:
            fellows = json.load(f)

    return faculty, fellows


def main():
    """Main scraping function."""
    print("Starting HBS data collection...")
    print("=" * 50)

    # Scrape faculty
    print("\n📚 Scraping faculty...")
    faculty = scrape_all_faculty()

    # Scrape fellows
    print("\n👥 Scraping executive fellows...")
    fellows = scrape_fellows()

    # Save raw data
    print("\n💾 Saving data...")
    save_data(faculty, fellows)

    print("\n" + "=" * 50)
    print(f"✅ Collection complete!")
    print(f"   - Faculty: {len(faculty)}")
    print(f"   - Fellows: {len(fellows)}")
    print(f"   - Total: {len(faculty) + len(fellows)}")


if __name__ == "__main__":
    main()

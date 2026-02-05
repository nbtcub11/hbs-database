"""Database setup and query functions for HBS database."""

import sqlite3
import json
from pathlib import Path

DATABASE_PATH = Path(__file__).parent / "data" / "hbs.db"


def get_connection():
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the database schema."""
    conn = get_connection()
    cursor = conn.cursor()

    # People table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS people (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            title TEXT,
            email TEXT,
            phone TEXT,
            bio TEXT,
            image_url TEXT,
            type TEXT CHECK(type IN ('faculty', 'fellow')),
            unit TEXT,
            organization TEXT,
            mba_year TEXT,
            profile_url TEXT,
            linkedin_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Tags table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            category TEXT
        )
    """)

    # Person-tags relationship
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS person_tags (
            person_id INTEGER,
            tag_id INTEGER,
            PRIMARY KEY (person_id, tag_id),
            FOREIGN KEY (person_id) REFERENCES people(id),
            FOREIGN KEY (tag_id) REFERENCES tags(id)
        )
    """)

    # Full-text search virtual table
    cursor.execute("DROP TABLE IF EXISTS people_fts")
    cursor.execute("""
        CREATE VIRTUAL TABLE people_fts USING fts5(
            name, title, bio, organization, unit,
            content='people',
            content_rowid='id'
        )
    """)

    # Create triggers to keep FTS in sync
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS people_ai AFTER INSERT ON people BEGIN
            INSERT INTO people_fts(rowid, name, title, bio, organization, unit)
            VALUES (new.id, new.name, new.title, new.bio, new.organization, new.unit);
        END
    """)

    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS people_ad AFTER DELETE ON people BEGIN
            INSERT INTO people_fts(people_fts, rowid, name, title, bio, organization, unit)
            VALUES('delete', old.id, old.name, old.title, old.bio, old.organization, old.unit);
        END
    """)

    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS people_au AFTER UPDATE ON people BEGIN
            INSERT INTO people_fts(people_fts, rowid, name, title, bio, organization, unit)
            VALUES('delete', old.id, old.name, old.title, old.bio, old.organization, old.unit);
            INSERT INTO people_fts(rowid, name, title, bio, organization, unit)
            VALUES (new.id, new.name, new.title, new.bio, new.organization, new.unit);
        END
    """)

    conn.commit()
    conn.close()
    print("Database initialized successfully.")


def rebuild_fts():
    """Rebuild the FTS index."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO people_fts(people_fts) VALUES('rebuild')")
    conn.commit()
    conn.close()


def clear_db():
    """Clear all data from the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM person_tags")
    cursor.execute("DELETE FROM tags")
    cursor.execute("DELETE FROM people")
    cursor.execute("DELETE FROM people_fts")
    conn.commit()
    conn.close()


def insert_person(person_data):
    """Insert a person into the database."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO people (name, title, email, phone, bio, image_url, type, unit, organization, mba_year, profile_url, linkedin_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        person_data.get('name'),
        person_data.get('title'),
        person_data.get('email'),
        person_data.get('phone'),
        person_data.get('bio'),
        person_data.get('image_url'),
        person_data.get('type'),
        person_data.get('unit'),
        person_data.get('organization'),
        person_data.get('mba_year'),
        person_data.get('profile_url'),
        person_data.get('linkedin_url')
    ))

    person_id = cursor.lastrowid

    # Insert tags
    for tag in person_data.get('tags', []):
        cursor.execute("INSERT OR IGNORE INTO tags (name, category) VALUES (?, ?)",
                      (tag.get('name'), tag.get('category')))
        cursor.execute("SELECT id FROM tags WHERE name = ?", (tag.get('name'),))
        tag_id = cursor.fetchone()[0]
        cursor.execute("INSERT OR IGNORE INTO person_tags (person_id, tag_id) VALUES (?, ?)",
                      (person_id, tag_id))

    conn.commit()
    conn.close()
    return person_id


def search_people(query=None, person_type=None, unit=None, tags=None, limit=100):
    """Search for people with optional filters."""
    conn = get_connection()
    cursor = conn.cursor()

    params = []
    conditions = []

    if query:
        # Use FTS5 for text search OR tag name match
        safe_query = query.replace('"', '').replace("'", "").strip()
        conditions.append("""(
            p.id IN (SELECT rowid FROM people_fts WHERE people_fts MATCH ?)
            OR p.id IN (
                SELECT pt.person_id FROM person_tags pt
                JOIN tags t ON pt.tag_id = t.id
                WHERE LOWER(t.name) LIKE LOWER(?)
            )
        )""")
        # Use prefix search with * for partial matches
        params.append(f'{safe_query}*')
        params.append(f'%{safe_query}%')

    if person_type:
        conditions.append("p.type = ?")
        params.append(person_type)

    if unit:
        conditions.append("p.unit = ?")
        params.append(unit)

    if tags:
        tag_list = [t.strip() for t in tags.split(',')]
        placeholders = ','.join(['?' for _ in tag_list])
        conditions.append(f"""
            p.id IN (
                SELECT pt.person_id FROM person_tags pt
                JOIN tags t ON pt.tag_id = t.id
                WHERE t.name IN ({placeholders})
            )
        """)
        params.extend(tag_list)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    sql = f"""
        SELECT DISTINCT p.*, GROUP_CONCAT(t.name) as tag_names
        FROM people p
        LEFT JOIN person_tags pt ON p.id = pt.person_id
        LEFT JOIN tags t ON pt.tag_id = t.id
        WHERE {where_clause}
        GROUP BY p.id
        ORDER BY p.name
        LIMIT ?
    """
    params.append(limit)

    cursor.execute(sql, params)
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def get_person(person_id):
    """Get a single person by ID with their tags."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT p.*, GROUP_CONCAT(t.name) as tag_names
        FROM people p
        LEFT JOIN person_tags pt ON p.id = pt.person_id
        LEFT JOIN tags t ON pt.tag_id = t.id
        WHERE p.id = ?
        GROUP BY p.id
    """, (person_id,))

    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_tags():
    """Get all tags grouped by category."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT t.name, t.category, COUNT(pt.person_id) as count
        FROM tags t
        LEFT JOIN person_tags pt ON t.id = pt.tag_id
        GROUP BY t.id
        ORDER BY t.category, count DESC
    """)

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def get_all_units():
    """Get all unique units."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT unit, COUNT(*) as count
        FROM people
        WHERE unit IS NOT NULL AND unit != ''
        GROUP BY unit
        ORDER BY unit
    """)

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def get_stats():
    """Get database statistics."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM people WHERE type = 'faculty'")
    faculty_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM people WHERE type = 'fellow'")
    fellow_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM tags")
    tag_count = cursor.fetchone()[0]

    conn.close()
    return {
        'faculty': faculty_count,
        'fellows': fellow_count,
        'tags': tag_count,
        'total': faculty_count + fellow_count
    }


if __name__ == "__main__":
    init_db()
    print("Database setup complete.")

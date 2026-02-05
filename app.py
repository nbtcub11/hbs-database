"""Flask application for HBS Faculty & Fellows Database."""

from flask import Flask, render_template, request, jsonify
import database
import json
from pathlib import Path

app = Flask(__name__)

DATA_DIR = Path(__file__).parent / "data"


def load_data_to_db():
    """Load scraped data into the database."""
    faculty_path = DATA_DIR / "faculty.json"
    fellows_path = DATA_DIR / "fellows.json"

    if not faculty_path.exists() and not fellows_path.exists():
        print("No data files found. Run scraper.py first.")
        return

    # Initialize and clear database
    database.init_db()
    database.clear_db()

    # Load faculty
    if faculty_path.exists():
        with open(faculty_path) as f:
            faculty = json.load(f)
        for person in faculty:
            database.insert_person(person)
        print(f"Loaded {len(faculty)} faculty members")

    # Load fellows
    if fellows_path.exists():
        with open(fellows_path) as f:
            fellows = json.load(f)
        for person in fellows:
            database.insert_person(person)
        print(f"Loaded {len(fellows)} executive fellows")

    # Rebuild FTS index
    database.rebuild_fts()
    print("FTS index rebuilt")


@app.route('/')
def index():
    """Render the main search interface."""
    stats = database.get_stats()
    units = database.get_all_units()
    tags = database.get_all_tags()
    return render_template('index.html', stats=stats, units=units, tags=tags)


@app.route('/api/search')
def search():
    """Search API endpoint."""
    query = request.args.get('q', '').strip()
    person_type = request.args.get('type', '').strip() or None
    unit = request.args.get('unit', '').strip() or None
    tags = request.args.get('tags', '').strip() or None

    results = database.search_people(
        query=query if query else None,
        person_type=person_type,
        unit=unit,
        tags=tags
    )

    return jsonify({
        'results': results,
        'count': len(results)
    })


@app.route('/api/person/<int:person_id>')
def get_person(person_id):
    """Get a single person's details."""
    person = database.get_person(person_id)
    if person:
        return jsonify(person)
    return jsonify({'error': 'Person not found'}), 404


@app.route('/api/tags')
def get_tags():
    """Get all available tags."""
    tags = database.get_all_tags()
    return jsonify(tags)


@app.route('/api/units')
def get_units():
    """Get all available units."""
    units = database.get_all_units()
    return jsonify(units)


@app.route('/api/stats')
def get_stats():
    """Get database statistics."""
    stats = database.get_stats()
    return jsonify(stats)


@app.route('/profile/<int:person_id>')
def profile(person_id):
    """Render a person's profile page."""
    person = database.get_person(person_id)
    if not person:
        return "Person not found", 404
    return render_template('profile.html', person=person)


if __name__ == '__main__':
    # Ensure database exists
    database.init_db()

    # Check if we need to load data
    stats = database.get_stats()
    if stats['total'] == 0:
        print("Database is empty. Loading data from JSON files...")
        load_data_to_db()

    print("\n🚀 Starting HBS Faculty & Fellows Database")
    print("   Open http://localhost:5001 in your browser")
    print("-" * 50)

    app.run(debug=True, port=5001)

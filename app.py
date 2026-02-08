"""Flask application for HBS Faculty & Fellows Database."""

from flask import Flask, render_template, request, jsonify
import database
import json
from pathlib import Path

# Import semantic search modules (graceful fallback if not available)
try:
    import embeddings
    import llm_search
    SEMANTIC_SEARCH_AVAILABLE = True
except ImportError as e:
    print(f"Semantic search modules not available: {e}")
    SEMANTIC_SEARCH_AVAILABLE = False
    embeddings = None
    llm_search = None

app = Flask(__name__)

DATA_DIR = Path(__file__).parent / "data"


def load_data_to_db():
    """Load scraped data into the database."""
    faculty_path = DATA_DIR / "faculty.json"
    fellows_path = DATA_DIR / "fellows.json"
    advisors_path = DATA_DIR / "rock_center_advisors.json"

    if not faculty_path.exists() and not fellows_path.exists() and not advisors_path.exists():
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

    # Load Rock Center advisors
    if advisors_path.exists():
        with open(advisors_path) as f:
            advisors = json.load(f)
        for person in advisors:
            database.insert_person(person)
        print(f"Loaded {len(advisors)} Rock Center advisors")

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


@app.route('/api/semantic-search')
def semantic_search():
    """Semantic search API endpoint using embeddings and LLM."""
    query = request.args.get('q', '').strip()
    k = request.args.get('k', 10, type=int)
    include_summary = request.args.get('summary', 'true').lower() == 'true'

    if not query:
        return jsonify({
            'results': [],
            'count': 0,
            'ai_summary': None,
            'error': 'No query provided'
        })

    if not SEMANTIC_SEARCH_AVAILABLE or not embeddings:
        return jsonify({
            'results': [],
            'count': 0,
            'ai_summary': None,
            'error': 'Semantic search not available'
        }), 503

    if not embeddings.is_available():
        return jsonify({
            'results': [],
            'count': 0,
            'ai_summary': None,
            'error': 'Embedding API not configured'
        }), 503

    # Perform semantic search
    try:
        similar_results = embeddings.search_similar(query, k=k)
    except Exception as e:
        print(f"Semantic search error: {e}")
        return jsonify({
            'results': [],
            'count': 0,
            'ai_summary': None,
            'error': f'Search failed: {str(e)}'
        }), 500

    if not similar_results:
        return jsonify({
            'results': [],
            'count': 0,
            'ai_summary': None
        })

    # Fetch full person details for each result
    results = []
    for person_id, score in similar_results:
        person = database.get_person(person_id)
        if person:
            person['similarity_score'] = round(score, 4)
            results.append(person)

    # Generate AI summary if requested and available
    ai_summary = None
    if include_summary and llm_search and llm_search.is_available() and results:
        try:
            ai_summary = llm_search.generate_summary(query, results[:5])  # Limit to top 5 for summary
        except Exception as e:
            print(f"LLM summary error: {e}")
            ai_summary = None

    return jsonify({
        'results': results,
        'count': len(results),
        'ai_summary': ai_summary
    })


@app.route('/api/ai-status')
def ai_status():
    """Check the status of AI search features."""
    status = {
        'semantic_search_available': SEMANTIC_SEARCH_AVAILABLE,
        'embeddings_configured': False,
        'llm_configured': False,
        'index_loaded': False,
        'index_count': 0
    }

    if SEMANTIC_SEARCH_AVAILABLE and embeddings:
        status['embeddings_configured'] = embeddings.is_available()
        index_stats = embeddings.get_index_stats()
        status['index_loaded'] = index_stats.get('loaded', False)
        status['index_count'] = index_stats.get('count', 0)

    if SEMANTIC_SEARCH_AVAILABLE and llm_search:
        status['llm_configured'] = llm_search.is_available()

    return jsonify(status)


@app.route('/profile/<int:person_id>')
def profile(person_id):
    """Render a person's profile page."""
    person = database.get_person(person_id)
    if not person:
        return "Person not found", 404
    return render_template('profile.html', person=person)


def initialize_app():
    """Initialize database and semantic search on startup."""
    # Ensure database exists
    database.init_db()

    # Check if we need to load data
    stats = database.get_stats()
    if stats['total'] == 0:
        print("Database is empty. Loading data from JSON files...")
        load_data_to_db()

    # Initialize semantic search if available
    if SEMANTIC_SEARCH_AVAILABLE and embeddings:
        if embeddings.is_available():
            # Try to load existing index or build it
            index_stats = embeddings.get_index_stats()
            if index_stats.get('loaded'):
                print(f"Semantic search index loaded with {index_stats['count']} entries")
            else:
                # Try to build the index if we have data
                stats = database.get_stats()
                if stats['total'] > 0:
                    print("Building semantic search index...")
                    embeddings.rebuild_from_database()
                else:
                    print("No semantic search index found. Build with: python embeddings.py")
        else:
            print("Semantic search: API keys not configured")
    else:
        print("Semantic search: modules not available")

    # Check LLM status
    if SEMANTIC_SEARCH_AVAILABLE and llm_search:
        if llm_search.is_available():
            print("LLM summaries: enabled (Arcee AI)")
        else:
            print("LLM summaries: ARCEE_API_KEY not configured")


# Initialize on import (for gunicorn)
initialize_app()


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    debug = os.environ.get("RAILWAY_ENVIRONMENT") is None  # Debug only in local dev

    print("\n🚀 Starting HBS Faculty & Fellows Database")
    print(f"   Open http://localhost:{port} in your browser")
    print("-" * 50)

    app.run(debug=debug, host="0.0.0.0", port=port)

// HBS Faculty & Fellows Database - JavaScript

document.addEventListener('DOMContentLoaded', function() {
    const searchInput = document.getElementById('search-input');
    const searchBtn = document.getElementById('search-btn');
    const resultsList = document.getElementById('results-list');
    const resultsCount = document.getElementById('results-count');
    const clearFiltersBtn = document.getElementById('clear-filters');
    const sortSelect = document.getElementById('sort-select');
    const modal = document.getElementById('profile-modal');
    const modalContent = document.getElementById('profile-content');
    const modalClose = document.querySelector('.modal-close');
    const aiSearchToggle = document.getElementById('ai-search-toggle');
    const aiSummaryBox = document.getElementById('ai-summary');
    const aiSummaryText = document.getElementById('ai-summary-text');

    let currentResults = [];
    let debounceTimer;
    let aiSearchEnabled = false;
    let aiSearchAvailable = false;

    // Check AI search availability
    checkAIStatus();

    // Initial load
    performSearch();

    // Event listeners
    searchInput.addEventListener('input', function() {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(performSearch, 300);
    });

    searchBtn.addEventListener('click', performSearch);

    searchInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            performSearch();
        }
    });

    // Filter change listeners
    document.querySelectorAll('input[name="type"]').forEach(radio => {
        radio.addEventListener('change', function() {
            // Clear unit filter when type changes to prevent "no results" issues
            document.querySelector('input[name="unit"][value=""]').checked = true;
            performSearch();
        });
    });

    document.querySelectorAll('input[name="unit"]').forEach(radio => {
        radio.addEventListener('change', performSearch);
    });

    document.querySelectorAll('input[name="tags"]').forEach(checkbox => {
        checkbox.addEventListener('change', performSearch);
    });

    clearFiltersBtn.addEventListener('click', clearFilters);

    sortSelect.addEventListener('change', function() {
        sortResults();
        renderResults();
    });

    // AI Search toggle
    if (aiSearchToggle) {
        aiSearchToggle.addEventListener('change', function() {
            aiSearchEnabled = this.checked;
            if (aiSearchEnabled && !aiSearchAvailable) {
                this.checked = false;
                aiSearchEnabled = false;
                alert('AI Search is not available. Please configure API keys.');
                return;
            }
            // Hide AI summary when toggling off
            if (!aiSearchEnabled && aiSummaryBox) {
                aiSummaryBox.classList.add('hidden');
            }
            performSearch();
        });
    }

    // Modal close
    modalClose.addEventListener('click', closeModal);
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            closeModal();
        }
    });

    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && modal.classList.contains('active')) {
            closeModal();
        }
    });

    function checkAIStatus() {
        fetch('/api/ai-status')
            .then(response => response.json())
            .then(status => {
                aiSearchAvailable = status.semantic_search_available &&
                                   status.embeddings_configured &&
                                   status.index_loaded;

                // Update toggle appearance based on availability
                const toggleLabel = document.querySelector('.ai-toggle');
                if (toggleLabel) {
                    if (!aiSearchAvailable) {
                        toggleLabel.classList.add('disabled');
                        toggleLabel.title = 'AI Search not available - configure API keys and build index';
                    } else {
                        toggleLabel.classList.remove('disabled');
                        toggleLabel.title = 'Enable AI-powered semantic search';
                    }
                }
            })
            .catch(error => {
                console.error('Failed to check AI status:', error);
                aiSearchAvailable = false;
            });
    }

    function performSearch() {
        const query = searchInput.value.trim();
        const type = document.querySelector('input[name="type"]:checked')?.value || '';
        const unit = document.querySelector('input[name="unit"]:checked')?.value || '';
        const selectedTags = Array.from(document.querySelectorAll('input[name="tags"]:checked'))
            .map(cb => cb.value)
            .join(',');

        // Hide AI summary by default
        if (aiSummaryBox) {
            aiSummaryBox.classList.add('hidden');
        }

        // Use semantic search if AI is enabled and there's a query
        if (aiSearchEnabled && query) {
            performSemanticSearch(query);
            return;
        }

        const params = new URLSearchParams();
        if (query) params.append('q', query);
        if (type) params.append('type', type);
        if (unit) params.append('unit', unit);
        if (selectedTags) params.append('tags', selectedTags);

        resultsList.innerHTML = '<div class="loading">Searching...</div>';

        fetch(`/api/search?${params.toString()}`)
            .then(response => response.json())
            .then(data => {
                currentResults = data.results;
                sortResults();
                renderResults();
            })
            .catch(error => {
                console.error('Search error:', error);
                resultsList.innerHTML = '<div class="loading">Error loading results. Please try again.</div>';
            });
    }

    function performSemanticSearch(query) {
        resultsList.innerHTML = '<div class="loading"><span class="ai-icon">✨</span> AI is searching...</div>';

        const params = new URLSearchParams();
        params.append('q', query);
        params.append('k', 20);
        params.append('summary', 'true');

        fetch(`/api/semantic-search?${params.toString()}`)
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    console.error('Semantic search error:', data.error);
                    resultsList.innerHTML = `<div class="loading">AI Search error: ${data.error}</div>`;
                    return;
                }

                currentResults = data.results;

                // Display AI summary if available
                if (data.ai_summary && aiSummaryBox && aiSummaryText) {
                    aiSummaryText.textContent = data.ai_summary;
                    aiSummaryBox.classList.remove('hidden');
                }

                // Don't sort semantic results - they're already ranked by relevance
                renderResults();
            })
            .catch(error => {
                console.error('Semantic search error:', error);
                resultsList.innerHTML = '<div class="loading">Error with AI search. Please try again.</div>';
            });
    }

    function sortResults() {
        const sortValue = sortSelect.value;
        currentResults.sort((a, b) => {
            if (sortValue === 'name') {
                return a.name.localeCompare(b.name);
            } else if (sortValue === 'name-desc') {
                return b.name.localeCompare(a.name);
            }
            return 0;
        });
    }

    function renderResults() {
        resultsCount.textContent = `${currentResults.length} result${currentResults.length !== 1 ? 's' : ''}`;

        if (currentResults.length === 0) {
            resultsList.innerHTML = `
                <div class="no-results">
                    <h3>No results found</h3>
                    <p>Try adjusting your search terms or filters</p>
                </div>
            `;
            return;
        }

        resultsList.innerHTML = currentResults.map(person => createResultCard(person)).join('');

        // Add click listeners to cards
        document.querySelectorAll('.result-card').forEach(card => {
            card.addEventListener('click', function() {
                const personId = this.dataset.id;
                openProfile(personId);
            });
        });
    }

    function getInitials(name) {
        if (!name) return '?';
        const parts = name.replace(/[^\w\s]/g, '').trim().split(/\s+/);
        if (parts.length >= 2) {
            return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
        }
        return parts[0].substring(0, 2).toUpperCase();
    }

    function createResultCard(person) {
        const badgeClass = person.type === 'faculty' ? 'badge-faculty' : 'badge-fellow';
        const badgeText = person.type === 'faculty' ? 'Faculty' : 'Executive Fellow';
        const avatarClass = person.type === 'faculty' ? 'faculty' : 'fellow';
        const initials = getInitials(person.name);

        const tags = person.tag_names ? person.tag_names.split(',').slice(0, 4) : [];
        const tagsHtml = tags.length > 0
            ? `<div class="card-tags">${tags.map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('')}</div>`
            : '';

        const unitHtml = person.unit
            ? `<span class="card-unit">${escapeHtml(person.unit)}</span>`
            : '';

        const orgHtml = person.organization
            ? `<span class="card-unit">${escapeHtml(person.organization)}</span>`
            : '';

        const bioHtml = person.bio
            ? `<div class="card-bio">${escapeHtml(person.bio)}</div>`
            : '';

        return `
            <div class="result-card" data-id="${person.id}">
                <div class="card-avatar ${avatarClass}">${initials}</div>
                <div class="card-content">
                    <div class="card-name">${escapeHtml(person.name)}</div>
                    <div class="card-title">${escapeHtml(person.title || '')}</div>
                    ${bioHtml}
                    <div class="card-meta">
                        <span class="badge ${badgeClass}">${badgeText}</span>
                        ${unitHtml}
                        ${orgHtml}
                    </div>
                    ${tagsHtml}
                </div>
            </div>
        `;
    }

    function openProfile(personId) {
        fetch(`/api/person/${personId}`)
            .then(response => response.json())
            .then(person => {
                renderProfileModal(person);
                modal.classList.add('active');
                document.body.style.overflow = 'hidden';
            })
            .catch(error => {
                console.error('Error loading profile:', error);
            });
    }

    function renderProfileModal(person) {
        const badgeClass = person.type === 'faculty' ? 'badge-faculty' : 'badge-fellow';
        const badgeText = person.type === 'faculty' ? 'Faculty' : 'Executive Fellow';
        const avatarClass = person.type === 'faculty' ? 'faculty' : 'fellow';
        const initials = getInitials(person.name);

        const tags = person.tag_names ? person.tag_names.split(',') : [];
        const tagsHtml = tags.length > 0
            ? `
                <div class="profile-section">
                    <h2>Keywords</h2>
                    <div class="profile-tags">
                        ${tags.map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('')}
                    </div>
                </div>
            `
            : '';

        const bioHtml = person.bio
            ? `
                <div class="profile-section">
                    <h2>About</h2>
                    <p class="profile-bio">${escapeHtml(person.bio)}</p>
                </div>
            `
            : '';

        const profileUrlHtml = person.profile_url && person.type === 'faculty'
            ? `<p><strong>HBS Profile:</strong> <a href="${escapeHtml(person.profile_url)}" target="_blank">View on HBS.edu</a></p>`
            : '';

        const linkedinHtml = person.linkedin_url
            ? `<p><strong>LinkedIn:</strong> <a href="${escapeHtml(person.linkedin_url)}" target="_blank">Search on LinkedIn</a></p>`
            : '';

        modalContent.innerHTML = `
            <div class="profile-header">
                <div class="profile-avatar ${avatarClass}">${initials}</div>
                <div class="profile-info">
                    <h1>${escapeHtml(person.name)}</h1>
                    <p class="profile-title">${escapeHtml(person.title || '')}</p>
                    <span class="badge ${badgeClass}">${badgeText}</span>
                    ${person.unit ? `<p class="profile-unit">${escapeHtml(person.unit)}</p>` : ''}
                    ${person.organization ? `<p class="profile-org">${escapeHtml(person.organization)}</p>` : ''}
                    ${person.mba_year ? `<p class="profile-mba">MBA ${escapeHtml(person.mba_year)}</p>` : ''}
                </div>
            </div>
            <div class="profile-body">
                ${bioHtml}
                <div class="profile-section">
                    <h2>Contact & Links</h2>
                    <div class="contact-info">
                        ${profileUrlHtml}
                        ${linkedinHtml}
                    </div>
                </div>
                ${tagsHtml}
            </div>
        `;
    }

    function closeModal() {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }

    function clearFilters() {
        searchInput.value = '';
        document.querySelector('input[name="type"][value=""]').checked = true;
        document.querySelector('input[name="unit"][value=""]').checked = true;
        document.querySelectorAll('input[name="tags"]').forEach(cb => cb.checked = false);
        performSearch();
    }

    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
});

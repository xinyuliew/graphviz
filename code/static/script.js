let cy = cytoscape({
    container: document.getElementById('cy'),
    style: [
        { selector: 'node', style: { 'label': 'data(id)', 'background-color': '#0074D9', 'color': '#0f0' } },
        { selector: 'edge', style: { 'label': 'data(predicate)', 'curve-style': 'bezier', 'target-arrow-shape': 'triangle' } }
    ],
    layout: { name: 'cose' }
});

let allFactsData = [];
let currentPage = 1;
const itemsPerPage = 10;

function escapeString(str) {
    return String(str || '').replace(/'/g, "\\'").replace(/"/g, '\\"');
}

// Time formatting function
function formatDateTime(timestamp) {
    const date = new Date(timestamp);
    if (isNaN(date)) return 'Unknown';
    const now = new Date();
    const diffMs = now - date;
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    
    if (diffHours < 24) {
        const diffMinutes = Math.floor(diffMs / (1000 * 60));
        if (diffMinutes < 60) return `${diffMinutes} minutes ago`;
        return `${diffHours} hours ago`;
    } else if (diffHours < 48) {
        return 'Yesterday';
    } else {
        return date.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        });
    }
}

function renderFactsPage(page) {
    const start = (page - 1) * itemsPerPage;
    const end = start + itemsPerPage;
    const pageData = allFactsData.slice(start, end);
    document.getElementById('facts-list').innerHTML = pageData.map(f => `
        <li ondblclick="showUpdateModal('${escapeString(f.subject)}', '${escapeString(f.predicate)}', '${escapeString(f.object)}', '${escapeString(f.id)}')">
            <span class="triple">${f.subject} ${f.predicate} ${f.object}</span>
            <span class="fact-buttons">
                <button class="details" onclick="showDetailsModal('${escapeString(f.subject)}', '${escapeString(f.predicate)}', '${escapeString(f.object)}', '${escapeString(f.created_at)}', '${escapeString(f.src)}', '${escapeString(f.original_message)}', '${escapeString(f.version)}', '${escapeString(f.id)}')">Details</button>
                <button class="update" onclick="showUpdateModal('${escapeString(f.subject)}', '${escapeString(f.predicate)}', '${escapeString(f.object)}', '${escapeString(f.id)}')">Update</button>
                <button class="delete" onclick="deleteTriple('${escapeString(f.subject)}', '${escapeString(f.predicate)}', '${escapeString(f.object)}', '${escapeString(f.id)}')">Delete</button>
            </span>
        </li>
    `).join('');
    renderPagination();
}

// Fetch all facts from backend with optional limit and render
function fetchFacts() {
    fetch('http://localhost:5000/api/facts')
        .then(response => {
            if (!response.ok) {
                return response.text().then(text => {
                    throw new Error(`HTTP ${response.status}: ${text.slice(0, 100)}...`);
                });
            }
            return response.json();
        })
        .then(data => {
            console.log('Fetch facts data:', data);
            allFactsData = data
                .filter(f => {
                    const isValid = f && f.subject && f.object && f.predicate &&
                        typeof f.subject === 'string' && typeof f.object === 'string' && typeof f.predicate === 'string' &&
                        f.subject.trim().length > 0 && f.object.trim().length > 0 && f.predicate.trim().length > 0;
                    if (!isValid) {
                        console.warn('Invalid fact filtered:', {
                            fact: f,
                            subject: f?.subject,
                            object: f?.object,
                            predicate: f?.predicate,
                            id: f?.id,
                            rawSubject: JSON.stringify(f?.subject),
                            rawObject: JSON.stringify(f?.object),
                            rawPredicate: JSON.stringify(f?.predicate)
                        });
                    }
                    return isValid;
                })
                .map(fact => ({
                    id: String(fact.id || ''),
                    subject: String(fact.subject || ''),
                    predicate: String(fact.predicate || ''),
                    object: String(fact.object || ''),
                    created_at: String(fact.created_at || 'Unknown'),
                    src: String(fact.src || 'Unknown'),
                    original_message: String(fact.original_message || 'N/A'),
                    version: String(fact.version || '1')
                }));
            currentPage = 1;
            renderFactsPage(currentPage);
            updateCytoscape(allFactsData);
        })
        .catch(error => {
            console.error('Fetch facts error:', error);
            alert('Failed to fetch facts: ' + error.message);
        });
}

function showAllFacts() {
    fetchFacts();
}

function renderPagination() {
    const totalPages = Math.ceil(allFactsData.length / itemsPerPage);
    const pagination = document.getElementById('pagination');
    pagination.innerHTML = '';
    if (totalPages > 1) {
        const prevButton = document.createElement('button');
        prevButton.textContent = 'Previous';
        prevButton.disabled = currentPage === 1;
        prevButton.onclick = () => {
            if (currentPage > 1) {
                currentPage--;
                renderFactsPage(currentPage);
            }
        };
        pagination.appendChild(prevButton);

        const pageInfo = document.createElement('span');
        pageInfo.id = 'page-info';
        pageInfo.textContent = `${currentPage} / ${totalPages}`;
        pagination.appendChild(pageInfo);

        const nextButton = document.createElement('button');
        nextButton.textContent = 'Next';
        nextButton.disabled = currentPage === totalPages;
        nextButton.onclick = () => {
            if (currentPage < totalPages) {
                currentPage++;
                renderFactsPage(currentPage);
            }
        };
        pagination.appendChild(nextButton);
    }
}

function fillSearchExample() {
    document.getElementById('search-input').value = 'Alice';
    updateSearchHint();
}

function updateSearchHint() {
    const searchInput = document.getElementById('search-input').value.trim();
    const hint = document.getElementById('search-hint');
    if (!searchInput) {
        hint.textContent = 'Enter an entity (e.g., Alice) or predicate (e.g., loves) to search';
    } else {
        hint.textContent = 'Click "Search Entity" or "Search Predicate" to find related triples!';
    }
}

function updateChatHint() {
    const chatInput = document.getElementById('chat-input').value.trim();
    const hint = document.getElementById('chat-hint');
    if (!chatInput) {
        hint.textContent = 'Ask a question about your memories, e.g., "What does Alice like?"';
    } else {
        hint.textContent = 'Click "Send" to get an answer!';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    ['subject', 'predicate', 'object'].forEach(id => {
        document.getElementById(id).addEventListener('input', updateFormHint);
    });
    document.getElementById('search-input').addEventListener('input', updateSearchHint);
    document.getElementById('chat-input').addEventListener('input', updateChatHint);
    updateFormHint();
    updateSearchHint();
    updateChatHint();
    document.getElementById('chat-input').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            sendChat();
        }
    });
});

function updateCytoscape(data) {
    cy.elements().remove();
    let nodes = new Set();
    let elements = [];

    // Get max edges limit from input
    const maxEdgesInputEl = document.getElementById('node-limit');
    const MAX_EDGES = maxEdgesInputEl ? parseInt(maxEdgesInputEl.value, 10) : 100;

    // Slice the data to limit edges
    const limitedData = data.slice(0, MAX_EDGES);

    // Update warning if needed
    const warningEl = document.getElementById('graph-warning');
    if (warningEl) {
        if (data.length > MAX_EDGES) {
            warningEl.textContent = `Displaying only the first ${MAX_EDGES} relations for performance.`;
        } else {
            warningEl.textContent = '';
        }
    }

    // Add nodes and edges
    limitedData.forEach(fact => {
        if (fact.subject && fact.object && fact.subject.trim() && fact.object.trim()) {
            if (!nodes.has(fact.subject)) {
                nodes.add(fact.subject);
                elements.push({ data: { id: fact.subject } });
            }
            if (!nodes.has(fact.object)) {
                nodes.add(fact.object);
                elements.push({ data: { id: fact.object } });
            }
            elements.push({
                data: {
                    source: fact.subject,
                    target: fact.object,
                    predicate: fact.predicate
                }
            });
        }
    });

    cy.add(elements);
    cy.layout({ name: 'breadthfirst', animate: true }).run();
}

function showDetailsModal(subject, predicate, object, createdAt, source, originalMessage, version, id) {
    document.getElementById('details-created-at').innerHTML = createdAt && createdAt !== 'Unknown' 
        ? `<span class="time-display">🕒 ${formatDateTime(createdAt)}</span>` 
        : 'Unknown';
    document.getElementById('details-source').textContent = source || 'Unknown';
    document.getElementById('details-original-message').textContent = originalMessage || 'N/A';
    document.getElementById('details-version').textContent = version || '1';
    
    fetch(`http://localhost:5000/api/update_timeline?subject=${encodeURIComponent(subject)}&object=${encodeURIComponent(object)}&id=${encodeURIComponent(id)}`)
        .then(response => {
            if (!response.ok) {
                return response.text().then(text => {
                    throw new Error(`HTTP ${response.status}: ${text}`);
                });
            }
            return response.json();
        })
        .then(timeline => {
            console.log('Timeline data:', timeline);
            let timelineList = document.getElementById('timeline-list');
            if (timeline.length === 0) {
                timelineList.innerHTML = '<p class="no-timeline">No update history found</p>';
            } else {
                timelineList.innerHTML = '<ul>' + timeline.map(entry => `
                    <li>
                        <div class="triple">${subject} ${entry.old_predicate} ${object}</div>
                        <div class="timeline-info">src: ${entry.src || 'Unknown'}, time: <span class="time-display">🕒 ${formatDateTime(entry.timestamp)}</span></div>
                    </li>
                `).join('') + '</ul>';
            }
            document.getElementById('details-modal').style.display = 'flex';
        })
        .catch(error => {
            console.error('Timeline fetch error:', error);
            document.getElementById('timeline-list').innerHTML = '<p class="no-timeline">Failed to load timeline</p>';
            document.getElementById('details-modal').style.display = 'flex';
        });
}

function closeDetailsModal() {
    document.getElementById('details-modal').style.display = 'none';
}

function deleteTriple(subject, predicate, object, id) {
    if (!confirm(`Are you sure you want to delete the triple ${subject} ${predicate} ${object} (ID: ${id})?`)) return;
    fetch('http://localhost:5000/api/delete_fact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject, predicate, object, id })
    })
    .then(response => {
        if (!response.ok) {
            return response.text().then(text => {
                throw new Error(`HTTP ${response.status}: ${text}`);
            });
        }
        return response.json();
    })
    .then(data => {
        alert(data.message || data.error);
        if (data.message && data.refresh) {
            fetchFacts();
        }
    })
    .catch(error => {
        console.error('Delete triple error:', error);
        alert('Failed to delete: ' + error.message);
    });
}

function showUpdateModal(subject, predicate, object, id) {
    console.log('Showing update modal with:', { subject, predicate, object, id });
    const modal = document.getElementById('update-modal');
    if (!modal) {
        console.error('Error: #update-modal not found in DOM');
        alert('Error: Update modal not found');
        return;
    }
    document.getElementById('modal-id').value = id;
    document.getElementById('modal-subject').value = subject;
    document.getElementById('modal-old-predicate').value = predicate;
    document.getElementById('modal-old-object').value = object;
    document.getElementById('modal-new-predicate').value = '';
    modal.style.display = 'flex';
}

function closeModal() {
    const modal = document.getElementById('update-modal');
    if (modal) {
        modal.style.display = 'none';
    }
}

function submitUpdate() {
    console.log('Update button clicked');
    let subject = document.getElementById('modal-subject').value.trim();
    let old_predicate = document.getElementById('modal-old-predicate').value.trim();
    let old_object = document.getElementById('modal-old-object').value.trim();
    let new_predicate = document.getElementById('modal-new-predicate').value.trim();
    let id = document.getElementById('modal-id').value.trim();
    if (!new_predicate) {
        alert('Please enter a new predicate');
        return;
    }
    console.log('Sending update request:', { subject, old_predicate, old_object, new_predicate, id });
    fetch('http://localhost:5000/api/update_fact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject, old_predicate, old_object, new_predicate, id })
    })
    .then(response => {
        console.log('Update response:', response);
        if (!response.ok) {
            return response.json().then(data => {
                throw new Error(data.error || `HTTP ${response.status}`);
            });
        }
        return response.json();
    })
    .then(data => {
        alert(data.message || data.error);
        if (data.message && data.refresh) {
            fetchFacts();
        }
        closeModal();
    })
    .catch(error => {
        console.error('Update fact error:', error);
        alert(`Update failed: ${error.message}`);
    });
}

function addFact() {
    let subject = document.getElementById('subject').value.trim();
    let predicate = document.getElementById('predicate').value.trim();
    let object = document.getElementById('object').value.trim();
    if (!subject || !predicate || !object) {
        alert('Please fill in all fields (subject, predicate, object)');
        return;
    }
    fetch('http://localhost:5000/api/add_fact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject, predicate, object })
    })
    .then(response => {
        if (!response.ok) {
            return response.text().then(text => {
                throw new Error(`HTTP ${response.status}: ${text}`);
            });
        }
        return response.json();
    })
    .then(data => {
        alert(data.message || data.error);
        if (data.message && !data.error) {
            fetchFacts();
        }
    })
    .catch(error => {
        console.error('Add fact error:', error);
        alert('Failed to add fact: ' + error.message);
    });
}

function fillExample() {
    document.getElementById('subject').value = 'Alice';
    document.getElementById('predicate').value = 'loves';
    document.getElementById('object').value = 'Bob';
    updateFormHint();
}

function updateFormHint() {
    const subject = document.getElementById('subject').value.trim();
    const predicate = document.getElementById('predicate').value.trim();
    const object = document.getElementById('object').value.trim();
    const hint = document.getElementById('form-hint');
    if (!subject && !predicate && !object) {
        hint.textContent = 'Please enter subject, predicate, and object, e.g., Alice loves Bob';
    } else if (!subject) {
        hint.textContent = 'Please enter a subject, e.g., Alice';
    } else if (!predicate) {
        hint.textContent = 'Please enter a predicate, e.g., loves';
    } else if (!object) {
        hint.textContent = 'Please enter an object, e.g., Bob';
    } else {
        hint.textContent = 'Click “Create” to save the memory!';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    ['subject', 'predicate', 'object'].forEach(id => {
        document.getElementById(id).addEventListener('input', updateFormHint);
    });
    updateFormHint();
});

function deleteAllFacts() {
    if (!confirm('Are you sure you want to delete all facts? This action is irreversible!')) return;
    fetch('http://localhost:5000/api/delete_all_facts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
    })
    .then(response => {
        if (!response.ok) {
            return response.text().then(text => {
                throw new Error(`HTTP ${response.status}: ${text}`);
            });
        }
        return response.json();
    })
    .then(data => {
        alert(data.message || data.error);
        if (data.message && data.refresh) {
            fetchFacts();
        }
    })
    .catch(error => {
        console.error('Delete all facts error:', error);
        alert('Failed to delete all facts: ' + error.message);
    });
}

function queryEntity() {
    const entity = document.getElementById('search-input').value.trim();
    const limit = parseInt(document.getElementById('node-limit').value, 10) || 100;

    if (!entity) return alert('Please enter an entity name');

    fetch(`http://localhost:5000/api/query_entity?entity=${encodeURIComponent(entity)}&limit=${limit}`)
        .then(res => res.ok ? res.json() : res.text().then(text => Promise.reject(`HTTP ${res.status}: ${text}`)))
        .then(data => handleQueryResults(data))
        .catch(err => {
            console.error('queryEntity error:', err);
            document.getElementById('facts-list').innerHTML = '<li>Query failed</li>';
            document.getElementById('pagination').innerHTML = '';
        });
}

function queryPredicate() {
    const predicate = document.getElementById('search-input').value.trim();
    const limit = parseInt(document.getElementById('node-limit').value, 10) || 100;

    if (!predicate) return alert('Please enter a predicate');

    fetch(`http://localhost:5000/api/query_predicate?predicate=${encodeURIComponent(predicate)}&limit=${limit}`)
        .then(res => res.ok ? res.json() : res.text().then(text => Promise.reject(`HTTP ${res.status}: ${text}`)))
        .then(data => handleQueryResults(data))
        .catch(err => {
            console.error('queryPredicate error:', err);
            document.getElementById('facts-list').innerHTML = '<li>Query failed</li>';
            document.getElementById('pagination').innerHTML = '';
        });
}

function queryObject() {
    const obj = document.getElementById('search-input').value.trim();
    const limit = parseInt(document.getElementById('node-limit').value, 10) || 100;

    if (!obj) return alert('Please enter an object name');

    fetch(`http://localhost:5000/api/query_object?object=${encodeURIComponent(obj)}&limit=${limit}`)
        .then(res => res.ok ? res.json() : res.text().then(text => Promise.reject(`HTTP ${res.status}: ${text}`)))
        .then(data => handleQueryResults(data))
        .catch(err => {
            console.error('queryObject error:', err);
            document.getElementById('facts-list').innerHTML = '<li>Query failed</li>';
            document.getElementById('pagination').innerHTML = '';
        });
}

// Shared handler for query results
function handleQueryResults(data) {
    if (!Array.isArray(data) || data.length === 0) {
        document.getElementById('facts-list').innerHTML = '<li>No related facts found</li>';
        document.getElementById('pagination').innerHTML = '';
        updateCytoscape([]);
        return;
    }
    allFactsData = data
        .filter(f => f && f.subject && f.object && f.predicate)
        .map((f, idx) => ({
            id: String(f.id ?? idx),
            subject: String(f.subject).trim(),
            predicate: String(f.predicate).trim(),
            object: String(f.object).trim(),
            created_at: f.created_at ?? 'Unknown',
            src: f.src ?? 'Unknown',
            original_message: f.original_message ?? 'N/A',
            version: String(f.version ?? '1')
        }));

    currentPage = 1;
    renderFactsPage(currentPage);
    updateCytoscape(allFactsData);
}

// Helper: called when user sets a node limit
function fetchFactsWithLimit() {
    const limitInput = document.getElementById('node-limit').value;
    const limit = parseInt(limitInput, 10) || 50; // default 50
    fetchFacts(limit);
}

function sendChat() {
    let userInput = document.getElementById('chat-input').value.trim();
    if (!userInput) return;
    
    // Add user message
    appendChatMessage(userInput, true);
    document.getElementById('chat-input').value = '';
    
    // Show loading indicator
    document.getElementById('loading-indicator').style.display = 'block';
    
    fetch('http://localhost:5000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userInput })
    })
    .then(response => {
        if (!response.ok) {
            return response.text().then(text => {
                throw new Error(`HTTP ${response.status}: ${text}`);
            });
        }
        return response.json();
    })
    .then(data => {
        // Hide loading indicator
        document.getElementById('loading-indicator').style.display = 'none';
        appendChatMessage(data.response || data.error);
        if (data.refresh) {
            fetchFacts();
        }
    })
    .catch(error => {
        console.error('Chat error:', error);
        alert('Chat failed: ' + error.message);
        document.getElementById('loading-indicator').style.display = 'none';
        appendChatMessage('Chat failed: ' + error.message);
    });
}

// Simulate backend intent analysis
function llmAnalyzeIntent(message) {
    const lowerMessage = message.toLowerCase();
    let intent = 'query';
    let subject = null, predicate = null, object = null;

    if (lowerMessage.includes('update') || lowerMessage.includes('change to')) {
        intent = 'update';
    } else if (lowerMessage.includes('delete') || lowerMessage.includes('remove') || lowerMessage.includes('forget')) {
        intent = 'delete';
    } else if (lowerMessage.includes('add') || lowerMessage.includes('create')) {
        intent = 'add';
    }

    const words = message.split(' ');
    if (intent === 'add' || intent === 'update' || intent === 'delete') {
        subject = words.find(w => w.match(/^[A-Z][a-z]*$/));
        predicate = words.find(w => w.match(/^(loves|likes|knows)$/));
        object = words.find((w, i) => i > words.indexOf(predicate) && w.match(/^[A-Z][a-z]*$/));
    }

    return { intent, subject, predicate, object };
}

// Modified appendChatMessage function
function appendChatMessage(message, isUser = false) {
    let chatContainer = document.getElementById('chat-container');
    let messageDiv = document.createElement('div');
    messageDiv.classList.add('message');
    if (isUser) {
        messageDiv.classList.add('user-message');
    } else {
        messageDiv.classList.add('model-message');
    }
    // Add message content
    messageDiv.textContent = message;
    // Optional: Add timestamp
    let timestamp = document.createElement('span');
    timestamp.classList.add('timestamp');
    timestamp.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    timestamp.style.fontSize = '0.8em';
    timestamp.style.color = '#aaa';
    timestamp.style.display = 'block';
    timestamp.style.textAlign = isUser ? 'right' : 'left';
    messageDiv.appendChild(timestamp);
    
    chatContainer.appendChild(messageDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

// Initial load
fetchFacts();

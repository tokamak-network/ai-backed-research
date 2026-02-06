#!/usr/bin/env python3
"""Export research results to web directory for automatic loading."""

import json
import shutil
import re
from pathlib import Path
from datetime import datetime


def extract_headings(markdown_text):
    """Extract H2 headings for table of contents."""
    headings = []
    for line in markdown_text.split('\n'):
        match = re.match(r'^##\s+(.+)', line)
        if match:
            title = match.group(1).strip()
            # Remove numbering like "1. " or "1.1 "
            title = re.sub(r'^\d+(\.\d+)*\.?\s*', '', title)
            # Create slug from title
            slug = title.lower()
            slug = re.sub(r'[:\.]', '', slug)
            slug = re.sub(r'&', 'and', slug)
            slug = re.sub(r'\s+', '-', slug)
            slug = re.sub(r'[^a-z0-9-]', '', slug)
            headings.append({'title': title, 'slug': slug})
    return headings


def generate_article_html(project_id, workflow_data, manuscript_text):
    """Generate static HTML article matching l2-fee-structures.html format."""
    topic = workflow_data.get("topic", project_id.replace("-", " ").title())
    rounds = workflow_data.get("rounds", [])
    final_round = rounds[-1] if rounds else {}
    final_score = final_round.get("overall_average", 0)
    final_decision = final_round.get("moderator_decision", {}).get("decision", "PENDING")
    version = len(rounds)

    # Get expert team if available
    expert_team = workflow_data.get("expert_team", [])
    expert_names = [e.get("name", "Expert") for e in expert_team] if expert_team else []

    # Extract headings for TOC
    headings = extract_headings(manuscript_text)
    toc_items = '\n'.join([f'                        <li><a href="#{h["slug"]}">{h["title"]}</a></li>' for h in headings[:10]])  # Limit to 10

    # Escape for JavaScript
    escaped_markdown = manuscript_text.replace('\\', '\\\\').replace('`', '\\`').replace('$', '\\$')

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{topic} | AI-Backed Research</title>
    <meta name="description" content="{topic} - Comprehensive research analysis with AI-powered peer review">

    <!-- Favicon -->
    <link rel="icon" type="image/svg+xml" href="../favicon.svg">
    <link rel="alternate icon" href="../favicon.svg">
    <link rel="mask-icon" href="../favicon.svg" color="#2563eb">

    <link rel="stylesheet" href="../styles/main.css">
    <link rel="stylesheet" href="../styles/article.css">
</head>
<body>
    <header class="site-header">
        <div class="container">
            <div class="header-nav">
                <a href="../index.html" class="back-link">
                    <svg viewBox="0 0 20 20" fill="currentColor">
                        <path fill-rule="evenodd" d="M9.707 16.707a1 1 0 01-1.414 0l-6-6a1 1 0 010-1.414l6-6a1 1 0 011.414 1.414L5.414 9H17a1 1 0 110 2H5.414l4.293 4.293a1 1 0 010 1.414z" clip-rule="evenodd"/>
                    </svg>
                    Back to Research
                </a>
                <div class="header-content">
                    <h1 class="site-title">AI-Backed Research</h1>
                    <p class="site-subtitle">Tokamak Network Research Lab</p>
                </div>
                <button class="theme-toggle" aria-label="Toggle dark mode">
                    <svg class="sun-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="5"></circle>
                        <line x1="12" y1="1" x2="12" y2="3"></line>
                        <line x1="12" y1="21" x2="12" y2="23"></line>
                        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
                        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
                        <line x1="1" y1="12" x2="3" y2="12"></line>
                        <line x1="21" y1="12" x2="23" y2="12"></line>
                        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
                        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
                    </svg>
                    <svg class="moon-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
                    </svg>
                </button>
            </div>
        </div>
    </header>

    <main class="article-layout">
        <button class="toc-toggle" aria-label="Toggle table of contents">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="3" y1="6" x2="21" y2="6"></line>
                <line x1="3" y1="12" x2="21" y2="12"></line>
                <line x1="3" y1="18" x2="21" y2="18"></line>
            </svg>
            Table of Contents
        </button>

        <aside class="toc-sidebar">
            <div class="toc-sticky">
                <h3 class="toc-title">On This Page</h3>
                <nav class="toc-nav">
                    <ul>
{toc_items}
                    </ul>
                </nav>
            </div>
        </aside>

        <article class="research-report">
            <header class="article-header">
                <div class="info-banner" style="background: linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, rgba(37, 99, 235, 0.1) 100%); border: 1px solid rgba(59, 130, 246, 0.3); border-radius: 8px; padding: 1rem 1.25rem; margin-bottom: 1.5rem; display: flex; align-items: center; gap: 0.75rem;">
                    <svg viewBox="0 0 20 20" fill="currentColor" style="width: 20px; height: 20px; color: #3b82f6; flex-shrink: 0;">
                        <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/>
                    </svg>
                    <span style="font-size: 0.9rem;">
                        This article shows the <strong>latest version</strong> of the manuscript.
                        <a href="../review-viewer.html?id={project_id}" style="color: #3b82f6; text-decoration: underline; font-weight: 600;">View full review board</a> to see all versions, reviewer feedback, and revision history.
                    </span>
                </div>
                <h1 class="article-title">{topic}</h1>
                <div class="article-meta">
                    <span class="meta-item"><strong>Version:</strong> {version}</span>
                    <span class="meta-item"><strong>Review Score:</strong> {final_score:.1f}/10</span>
                    <span class="meta-item"><strong>Status:</strong> {final_decision.replace('_', ' ')}</span>
                </div>
            </header>

            <div id="article-content">
                <!-- Content will be rendered by JavaScript -->
            </div>
        </article>
    </main>

    <footer class="site-footer">
        <div class="container">
            <p><strong>Generated by:</strong> AI-Backed Research Platform with {len(expert_names)} Expert Reviewers</p>
            <p><strong>Review Process:</strong> {version} Round(s) of Peer Review</p>
            <p><strong>Platform:</strong> Tokamak Network Research Lab</p>
            <p class="copyright">© 2026 Tokamak Network Research Lab. All rights reserved.</p>
        </div>
    </footer>

    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <script src="../js/main.js"></script>
    <script>
        // Render markdown content
        const markdownContent = `{escaped_markdown}`;

        // Parse with marked
        const htmlContent = marked.parse(markdownContent);

        // Create temporary div to process HTML
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = htmlContent;

        // Wrap sections with proper section tags and IDs
        let currentSection = null;
        const contentDiv = document.createElement('div');

        Array.from(tempDiv.children).forEach(el => {{
            if (el.tagName === 'H2') {{
                // Create new section for each H2
                if (currentSection) {{
                    contentDiv.appendChild(currentSection);
                }}
                currentSection = document.createElement('section');
                currentSection.className = 'section';

                // Generate ID from heading text
                let text = el.textContent;
                text = text.replace(/^\\d+(\\.\\d+)*\\.?\\s*/, '');
                let slug = text.toLowerCase()
                    .replace(/[:.]/, '')
                    .replace(/&/g, 'and')
                    .replace(/\\s+/g, '-')
                    .replace(/[^a-z0-9-]/g, '');
                currentSection.id = slug;
                el.id = slug;
                currentSection.appendChild(el);
            }} else if (currentSection) {{
                // Add element to current section
                currentSection.appendChild(el);
            }} else {{
                // Before first H2, add directly
                contentDiv.appendChild(el);
            }}
        }});

        // Add last section
        if (currentSection) {{
            contentDiv.appendChild(currentSection);
        }}

        // Apply styling classes to specific elements
        contentDiv.querySelectorAll('p').forEach(p => {{
            const text = p.textContent.trim();
            const html = p.innerHTML;

            // Lead paragraphs (first paragraph after Executive Summary)
            if (p.previousElementSibling?.tagName === 'H2' &&
                p.previousElementSibling.textContent.includes('Executive Summary')) {{
                p.className = 'lead';
            }}

            // Key insights and findings
            if (text.startsWith('Key findings') || text.startsWith('Key insight') ||
                text.startsWith('Key Findings') || text.startsWith('Key Insight')) {{
                p.className = 'key-insight';
            }}

            // Practical implications
            if (html.includes('<strong>Practical implications:') ||
                html.includes('<strong>Practical Implications:')) {{
                p.className = 'insight';
            }}

            // Historical context
            if (html.includes('<strong>Historical context:') ||
                html.includes('<strong>Historical Context:')) {{
                p.className = 'historical-context';
            }}

            // Impact statements
            if (html.includes('<strong>Impact on') || html.includes('<strong>The ') ||
                html.includes('<strong>This ')) {{
                if (p.className === '') p.className = 'insight';
            }}
        }});

        // Style code blocks
        contentDiv.querySelectorAll('pre').forEach(pre => {{
            const code = pre.querySelector('code');
            if (code) {{
                pre.className = 'code-block';
            }}
        }});

        // Convert certain lists into highlight boxes
        contentDiv.querySelectorAll('ul').forEach(ul => {{
            const prevEl = ul.previousElementSibling;
            if (prevEl && prevEl.tagName === 'P') {{
                const text = prevEl.textContent.trim();
                if (text.includes('Key findings') || text.includes('Key Findings') ||
                    text.includes('findings indicate') || text.includes('Key metrics')) {{
                    const box = document.createElement('div');
                    box.className = 'highlight-box';
                    const title = document.createElement('h3');
                    title.textContent = 'Key Findings:';
                    box.appendChild(title);
                    box.appendChild(ul.cloneNode(true));
                    ul.replaceWith(box);
                }}
            }}
        }});

        // Insert processed HTML
        document.getElementById('article-content').innerHTML = contentDiv.innerHTML;
    </script>
</body>
</html>'''

    return html


def export_results_to_web():
    """Export all research results to web/data directory and generate articles."""
    results_dir = Path("results")
    web_data_dir = Path("web/data")
    web_articles_dir = Path("web/articles")
    web_data_dir.mkdir(exist_ok=True)
    web_articles_dir.mkdir(exist_ok=True)

    workflows = []

    for project_dir in results_dir.iterdir():
        if not project_dir.is_dir():
            continue

        workflow_file = project_dir / "workflow_complete.json"
        if not workflow_file.exists():
            continue

        # Read workflow data
        with open(workflow_file) as f:
            workflow_data = json.load(f)

        # Generate clean ID
        project_id = project_dir.name

        # Copy workflow file to web/data
        dest_file = web_data_dir / f"{project_id}.json"
        shutil.copy(workflow_file, dest_file)

        # Copy manuscript files (all versions)
        manuscripts = {}
        for manuscript_file in project_dir.glob("manuscript_*.md"):
            manuscript_text = manuscript_file.read_text()
            version = manuscript_file.stem  # e.g., "manuscript_v1"
            manuscripts[version] = manuscript_text

        # Save manuscripts as separate JSON
        if manuscripts:
            manuscripts_file = web_data_dir / f"{project_id}_manuscripts.json"
            with open(manuscripts_file, "w") as f:
                json.dump(manuscripts, f, indent=2)

            # Generate static article HTML for latest version
            # Try to find versioned manuscripts first, then fallback to final
            versioned = [k for k in manuscripts.keys() if '_v' in k]
            if versioned:
                latest_version = max(versioned, key=lambda x: int(x.split('_v')[1]))
            else:
                # Use final or any manuscript
                latest_version = 'manuscript_final' if 'manuscript_final' in manuscripts else list(manuscripts.keys())[0]
            latest_manuscript = manuscripts[latest_version]

            try:
                article_html = generate_article_html(project_id, workflow_data, latest_manuscript)
                article_file = web_articles_dir / f"{project_id}.html"
                with open(article_file, "w", encoding='utf-8') as f:
                    f.write(article_html)
                print(f"  ✓ Generated: articles/{project_id}.html")
            except Exception as e:
                print(f"  ✗ Error generating {project_id}.html: {e}")

        # Get performance metrics
        performance = workflow_data.get("performance", {})
        total_duration = performance.get("total_duration", 0)

        # Determine status based on final round decision
        final_decision = workflow_data.get("rounds", [{}])[-1].get("moderator_decision", {}).get("decision", "PENDING")
        if final_decision == "ACCEPT":
            status = "completed"
        elif final_decision in ["MAJOR_REVISION", "MINOR_REVISION"]:
            status = "rejected"  # Didn't pass threshold
        else:
            status = "failed"

        # Add to index
        workflows.append({
            "id": project_id,
            "topic": workflow_data.get("topic", project_id.replace("-", " ").title()),
            "final_score": workflow_data.get("final_score", 0),
            "passed": workflow_data.get("passed", False),
            "status": status,
            "total_rounds": workflow_data.get("total_rounds", 0),
            "timestamp": workflow_data.get("timestamp", ""),
            "data_file": f"data/{project_id}.json",
            "elapsed_time_seconds": int(total_duration),
            "final_decision": final_decision
        })

    # Sort by timestamp (newest first)
    workflows.sort(key=lambda x: x["timestamp"], reverse=True)

    # Write index file
    index_file = web_data_dir / "index.json"
    with open(index_file, "w") as f:
        json.dump({
            "projects": workflows,
            "updated_at": datetime.now().isoformat()
        }, f, indent=2)

    print(f"\n✓ Exported {len(workflows)} research projects")
    for wf in workflows:
        status = "✓ PASS" if wf["passed"] else "⚠ REVISE"
        print(f"  - {wf['topic']}: {wf['final_score']:.1f}/10 {status}")

    return len(workflows)


if __name__ == "__main__":
    export_results_to_web()

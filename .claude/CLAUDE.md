# Autonomous Research Press - Project Rules

## Web Design Theme: IBM Carbon Design System

All web pages (`web/`) must follow the IBM Carbon Design System aesthetic:

### Geometry
- **border-radius**: `0` for buttons, badges, inline-code; `2px` for containers, cards, panels, inputs
- Never use rounded corners (`8px`, `12px`, `50%`, etc.)

### Typography
- **Font family**: IBM Plex Sans (body), IBM Plex Mono (code) — loaded via `styles/main.css`
- Use CSS variables from `main.css` for all font sizes

### Colors & Variables
- Always use CSS custom properties defined in `styles/main.css`
- Primary: `var(--primary-600)`, Surface: `var(--surface)`, Background: `var(--background)`
- Text: `var(--text)`, `var(--text-secondary)`, Border: `var(--border)`

### Shadows
- Minimal shadows: max `1-3px` blur
- Avoid large drop-shadows or glowing effects

### Transitions
- Duration: `70-110ms` (Carbon standard)
- Easing: `cubic-bezier(0.2, 0, 0.38, 0.9)` (Carbon productive motion)
- Avoid `200ms+` transitions

### Components
- Buttons: sharp rectangular (`border-radius: 0`)
- Inputs/selects: `border-radius: 2px`
- Cards/panels: `border-radius: 2px`
- Badges/tags: `border-radius: 0`
- No radio buttons for option selectors — use clickable card/box pattern instead

## Academic Categories

The platform supports 9 major academic fields defined in `research_cli/categories.py`:
1. Computer Science (6 subfields)
2. Engineering & Technology (4 subfields)
3. Natural Sciences (5 subfields)
4. Social Sciences (5 subfields)
5. Humanities (4 subfields)
6. Business & Economics (3 subfields)
7. Medicine & Health Sciences (3 subfields)
8. Law & Public Policy (2 subfields)

When adding new pages or modifying category-related code, ensure all 9 fields are represented.
The JS `ACADEMIC_CATEGORIES` in `ask-topic.html` must mirror `categories.py`.

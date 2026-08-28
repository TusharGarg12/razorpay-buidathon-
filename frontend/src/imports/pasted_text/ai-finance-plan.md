# Frontend Implementation Plan — AI Finance Controller
> **React + Vite | Premium Dark Mode | Vanilla CSS | SSE Data Streaming**

---

## 1. Goal Description
The frontend for the AI Finance Controller must be a visually stunning, responsive, and dynamic dashboard. It needs to reflect a "premium financial software" aesthetic, characterized by a dark mode palette, glassmorphism effects, smooth micro-animations, and modern typography (Inter). It will connect to the Python FastAPI backend via Server-Sent Events (SSE) to display live reconciliation progress and results.

## 2. Technical Stack
- **Framework:** React + Vite
- **Styling:** Vanilla CSS (`index.css`) — *No Tailwind (per system guidelines) to ensure absolute control over custom animations and glassmorphism.*
- **Icons & Charts:** Lucide-React (icons), Recharts or Chart.js (donut charts)
- **Deployment:** Vercel

---

## 3. Design System & Aesthetics (Vanilla CSS)
The design will heavily rely on a predefined system of CSS variables in `index.css`, inspired by high-end, cyberpunk-esque premium dark designs.

### Color Palette (CSS Variables)
```css
:root {
  --bg-dark: #000000;          /* Pitch black background */
  --bg-card: rgba(20, 20, 20, 0.6); /* Floating dark glasspill bg */
  --border-color: rgba(255, 255, 255, 0.1);
  --text-primary: #FFFFFF;
  --text-muted: #8b949e;
  
  /* Brand Accents - Neon Yellow/Green */
  --accent-neon: #E3FF37;      /* Primary striking neon yellow/green */
  --accent-neon-dim: rgba(227, 255, 55, 0.2);
  
  /* Status Colors */
  --status-success: #238636;
  --status-error: #da3633;
  --status-warning: #d29922;
}
```

### Key Visual Features
1. **Neon Cyberpunk Aesthetic:** Pitch black background with subtle glowing geometric laser lines (using CSS linear-gradients and drop-shadows).
2. **Typography:** A wide, bold, futuristic font (like `Syncopate` or `Michroma` via Google Fonts) for striking headlines, paired with `Inter` for highly readable body text.
3. **Floating Pill Glassmorphism:** Navigation and control panels will be styled as floating pill-shaped elements (high `border-radius: 50px`), using `backdrop-filter: blur(12px)` and very subtle white borders.
4. **Neon Glows:** The primary neon accent color (`#E3FF37`) will be used for buttons and key text, complete with a soft neon `box-shadow` to make elements pop off the dark background.

---

## 4. Component Architecture
The React application will be divided into modular, reusable components inside `src/components/`.

### 1. `App.jsx` (Main Layout)
- Manages global state (upload status, SSE data stream, final results).
- Layout: Top Floating Pill Navigation Bar, Main Content Area (grid layout), and subtle glowing laser-line background overlays.

### 2. `UploadZone.jsx`
- **Purpose:** Handles the drag-and-drop of `bank.csv` and `ledger.csv`.
- **UI:** A glowing dashed-border drop zone. Includes a prominent "Run Demo (60 records)" button to trigger the synthetic data pipeline instantly.

### 3. `PipelineProgress.jsx`
- **Purpose:** Visualizes the 5-step pipeline (Blocking → Normalize → Tier1 → Tier2 → Tier3/4).
- **UI:** A horizontal progress bar that lights up dynamically via SSE events as the backend processes records.

### 4. `StatsDashboard.jsx`
- **Purpose:** Displays the "Big 4" metrics: Match Rate, Precision, Recall, and F1 Score.
- **UI:** 4 glassmorphic metric cards. Values will use a custom hook to animate counting up from 0 to the final value.

### 5. `MatchTable.jsx`
- **Purpose:** Shows the reconciled pairs.
- **UI:** A sleek, filterable table. Rows will be subtly color-coded by the tier that matched them, with neon hover states to make them feel interactive and alive.

### 6. `ExceptionsPanel.jsx`
- **Purpose:** The "Honest Exceptions" display.
- **UI:** A high-contrast panel highlighting unresolved records. Displays the 6 specific reason codes clearly and includes an "Export to CSV" button.

### 7. `CategoryChart.jsx`
- **Purpose:** Shows the distribution of the 9 mismatch types.
- **UI:** An animated Donut Chart using a lightweight chart library (or SVG) styled to match the dark theme.

### 8. `QAChat.jsx`
- **Purpose:** Settlement Q&A chat interface.
- **UI:** A fixed sidebar or slide-out drawer that looks like a modern chat UI. It will send queries to the FastAPI `/api/chat` endpoint.

---

## 5. Data Flow (SSE Integration)
The frontend will use the native `EventSource` API to consume real-time updates from the backend:
1. User clicks "Run Demo".
2. React makes a `POST /api/run-demo` request, receives a `job_id`.
3. React opens `new EventSource('/api/stream/' + job_id)`.
4. As JSON chunks arrive (e.g., `{"stage": "Tier 1", "matched": 25}`), React state is updated, triggering re-renders of `PipelineProgress` and `StatsDashboard`.

---

## 6. Execution Steps (Frontend Specific)

1. **Initialize Project:** 
   `npx -y create-vite@latest frontend --template react`
2. **Setup Base Styles:** 
   Configure `index.css` with the CSS variables, Inter font, reset rules, and global dark theme.
3. **Build Core Layout:** 
   Structure `App.jsx` and create the empty component files.
4. **Implement Components (Iterative):**
   - Build `UploadZone` and wire up the basic API call.
   - Build `PipelineProgress` and test with a mocked `setInterval` before wiring to SSE.
   - Build `StatsDashboard` with counting animations.
   - Build `MatchTable` and `ExceptionsPanel` for tabular data.
5. **Implement Chat:**
   Build the `QAChat` interface and its message state management.
6. **Polish & Responsive Design:**
   Ensure CSS Grid/Flexbox handles window resizing gracefully. Add final micro-animations.

---

## User Review Required
> [!IMPORTANT]
> - Do you approve of using **Lucide-React** for icons and **Recharts** for the donut chart to save time, while keeping everything else strictly Vanilla CSS?
> - I have updated the plan to mirror the pitch-black, floating glass-pill, neon-yellow cyberpunk aesthetic from your image. Do you agree with this visual direction for the Buildathon?

Please click **Proceed** or provide your feedback!

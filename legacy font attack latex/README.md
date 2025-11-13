# Font-Based Text Manipulation System

Implementation of font manipulation techniques from arXiv:2505.16957 for creating PDFs where displayed text differs from selectable/copyable text.

## 🎯 Project Overview

This project demonstrates how font manipulation can be used to create PDFs where:
- **Visual Text**: What the user sees on screen
- **Hidden Text**: What gets copied to clipboard or extracted by text tools

**Example**: Display "hello" but copy as "world"

## 📁 Project Structure

```
real_code_glyph/
├── backend/              # Flask API server
│   ├── app.py           # Main API server
│   ├── manipulators/    # Font manipulation modules
│   │   ├── truly_selective.py          # V1 - Basic
│   │   ├── truly_selective_v3.py       # V3 - OpenType (experimental)
│   │   ├── truly_selective_v4.py       # V4 - Unicode alternates (RECOMMENDED)
│   │   ├── unicode_alternates.json     # 700+ character mappings
│   │   ├── cyrillic.py                 # Cyrillic homoglyphs
│   │   └── pua.py                      # Private Use Area
│   ├── test_v4.py       # Comprehensive test suite
│   └── README.md        # Detailed API documentation
│
├── frontend/            # React UI (Vite + React)
│   ├── src/
│   │   ├── App.jsx      # Main application
│   │   └── ...
│   └── package.json
│
├── docs/                # Documentation
│   ├── backend.md
│   ├── frontend.md
│   └── repository-overview.md
│
└── tests/               # Integration tests
    └── test_truly_selective.py
```

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Node.js 18+
- XeLaTeX (for PDF generation)

### Backend Setup

```bash
cd backend
pip install -r requirements.txt
python app.py
```

Server runs on `http://localhost:5001`

**API Endpoints:**
- `GET /api/health` - Health check
- `GET /api/modes` - Available manipulation modes
- `POST /api/manipulate` - Create manipulated PDF
- `GET /api/download/<filename>` - Download files

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

UI runs on `http://localhost:5173`

## 🎯 Manipulation Modes

### ✅ Ligature (⭐ RECOMMENDED)
**Word-level OpenType ligature substitution**

Creates a custom font where the entire hidden word is replaced by a single composite glyph that displays the visual word.

**Example:**
- Visual: "hello"
- Hidden: "world"
- Copies as: "world"

**Features:**
- ✅ Most reliable and performant (~3 seconds)
- ✅ Proper text layer for copy/paste
- ✅ No character length restrictions
- ✅ Works with any characters in base font

**Usage:**
```bash
curl -X POST http://localhost:5001/api/manipulate \
  -H "Content-Type: application/json" \
  -d '{"mode": "ligature", "visual_word": "hello", "hidden_word": "world"}'
```

### Other Modes

#### V4: Glyph Cloning
Two-font approach with pristine source copy. Works for same-length words without repeated character conflicts.

#### V1: Multi-Font Sequential
Character-level fonts (slower, text extraction issues).

#### PUA: Private Use Area
Fast but copies as garbled characters.

#### Cyrillic: Homoglyphs
Limited to characters with Cyrillic lookalikes.

## 📊 Testing

### Quick Test
```bash
# Start server
cd backend
python3 app.py

# Test ligature mode (recommended)
curl -X POST http://localhost:5001/api/manipulate \
  -H "Content-Type: application/json" \
  -d '{"mode": "ligature", "visual_word": "hello", "hidden_word": "world"}'

# Verify text extraction
pdftotext outputs/{job_id}.pdf /dev/stdout | grep "Deceptive:"
# Should show: "Deceptive: world"
```

### Visual Verification
```bash
# Open generated PDF
open outputs/{job_id}.pdf
# Visually displays: "hello"
# Copy text shows: "world"
```

## 📖 Documentation

- **Implementation Summary**: See `IMPLEMENTATION_SUMMARY.md` for complete technical details
- **Backend API**: See `backend/README.md` for API documentation
- **All Modes Comparison**: See `IMPLEMENTATION_SUMMARY.md` for performance metrics and mode analysis

## 🔬 Key Technical Achievements

This implementation demonstrates several font manipulation techniques:

1. **✅ Ligature Substitution** (RECOMMENDED): Word-level OpenType ligatures for reliable manipulation
2. **Glyph Cloning**: Copying glyph outlines with pristine source font to avoid contamination
3. **Multi-Font Approach**: Character-level font switching (experimental)
4. **OpenType Features**: GSUB table manipulation for ligature substitution
5. **PDF Generation**: LuaLaTeX compilation with custom fonts

## 🎯 Best Practices

1. **Use `ligature` mode** for all production use cases
2. **Remove spaces** from input words (e.g., "alohafriends" not "aloha friends")
3. **Use LuaLaTeX** for PDF compilation (faster than XeLaTeX)
4. **Check logs** in `outputs/logs/` for detailed debugging
5. **Test with pdftotext** to verify text extraction

## 🛠️ Development

### Current Branch Structure
- `main` - Stable version with V1, V3, V4 manipulators
- `feature_pdf_of_choice` - Clean codebase for new features

### Running in Development

**Backend:**
```bash
cd backend
python app.py  # Runs on port 5001 with hot reload
```

**Frontend:**
```bash
cd frontend
npm run dev  # Runs on port 5173 with hot reload
```

## 📝 License

For educational and research purposes only.

## 🙏 Acknowledgments

Based on research from arXiv:2505.16957 - Font Manipulation for Deceptive Documents.

## 📧 Support

For detailed technical documentation, see:
- Backend: `backend/README.md`
- Frontend: `docs/frontend.md`
- Testing: `docs/testing-and-verification.md`

# Font Manipulation Backend API

Flask API for creating deceptive PDFs using font manipulation techniques. Text displays differently from what it copies as, based on research from arXiv:2505.16957.

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- XeLaTeX (for PDF generation)
- macOS/Linux (tested on macOS)

### Installation

```bash
cd backend
pip install -r requirements.txt
```

### Run Server

```bash
python app.py
```

Server runs on `http://localhost:5001`

## 📚 API Documentation

### Health Check
```
GET /api/health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "manipulators": ["truly_selective", "truly_selective_v3", "truly_selective_v4", "cyrillic", "pua"]
}
```

### Get Available Modes
```
GET /api/modes
```

Returns detailed information about each manipulation mode with pros/cons.

### Get Example Word Pairs
```
GET /api/examples
```

Returns example word pairs for testing.

### Create Manipulation
```
POST /api/manipulate
```

**Request:**
```json
{
  "mode": "truly_selective_v4",
  "visual_word": "hello",
  "hidden_word": "anita"
}
```

**Response:**
```json
{
  "success": true,
  "pdf_file": "34451af5.pdf",
  "font_file": "34451af5_deceptive_v4.ttf",
  "message": "V4 manipulation successful (variation selectors)",
  "mode": "truly_selective_v4"
}
```

### Download File
```
GET /api/download/<filename>
```

Downloads generated PDF or font file.

## 🎯 Manipulation Modes

### V4: Truly Selective with Unicode Alternates (⭐ RECOMMENDED)

**Mode ID:** `truly_selective_v4`

**How it works:** Uses visually similar Unicode alternate codepoints to handle repeated characters with different visuals.

**Example:**
- Visual: "unidirectional"
- Hidden: "biidirectional"
- Result: Displays as "unidirectional", copies as "biıdіrectïonal" (using ı U+0131, і U+0456, ï U+00EF)

**Pros:**
- ✅ Handles repeated characters needing different visuals
- ✅ Supports all character types (letters, numbers, punctuation)
- ✅ Up to 10 occurrences of same character
- ✅ Most flexible solution

**Cons:**
- ⚠️ Uses similar-looking Unicode alternates (may be detectable under scrutiny)

**Character Support:**
- 700+ Unicode alternate mappings (see `manipulators/unicode_alternates.json`)
- Lowercase letters, uppercase letters, digits, punctuation

### V1: Truly Selective (Basic)

**Mode ID:** `truly_selective`

**How it works:** Uses two fonts - normal and deceptive. Specific word instance is manipulated.

**Pros:**
- ✅ Clean output
- ✅ No side effects
- ✅ Professional appearance

**Cons:**
- ⚠️ Cannot handle repeated characters with different visuals
- ⚠️ Will return error if character needs multiple visuals

### V3: Truly Selective with OpenType (Experimental)

**Mode ID:** `truly_selective_v3`

**How it works:** Uses OpenType GSUB contextual alternates (calt feature).

**Pros:**
- ✅ Uses standard OpenType features

**Cons:**
- ⚠️ **Not truly selective** - affects ALL instances of pattern in document
- ⚠️ Global pattern matching
- ❌ Not recommended for production

### Cyrillic Homoglyphs

**Mode ID:** `cyrillic`

**How it works:** Maps Cyrillic characters to Latin glyphs.

**Pros:**
- ✅ Single font approach
- ✅ Survives PDF text extraction

**Cons:**
- ⚠️ Copies as Cyrillic characters (detectable)

### Private Use Area (PUA)

**Mode ID:** `pua`

**How it works:** Uses Unicode Private Use Area for custom mappings.

**Pros:**
- ✅ Precise control
- ✅ No character conflicts

**Cons:**
- ⚠️ May not survive PDF encoding

## 🧪 Testing

### Run Comprehensive Test Suite

```bash
python test_v4.py
```

**Test Coverage:**
- 19 test cases covering word lengths 3-20 characters
- Repeated character patterns (2-10 occurrences)
- Edge cases (palindromes, mixed case, numbers)

**Latest Results:** 17/19 tests passing (89% success rate)

### Manual Testing

```bash
# Test basic substitution
curl -X POST http://localhost:5001/api/manipulate \
  -H "Content-Type: application/json" \
  -d '{"mode": "truly_selective_v4", "visual_word": "hello", "hidden_word": "world"}'

# Test repeated characters
curl -X POST http://localhost:5001/api/manipulate \
  -H "Content-Type: application/json" \
  -d '{"mode": "truly_selective_v4", "visual_word": "hello", "hidden_word": "anita"}'
```

## 📁 Project Structure

```
backend/
├── app.py                              # Flask API server
├── test_v4.py                          # Comprehensive test suite
├── requirements.txt                    # Python dependencies
├── SOLUTION_SUMMARY.md                 # Technical documentation
├── README.md                           # This file
├── .gitignore                          # Git ignore rules
│
├── manipulators/                       # Font manipulation modules
│   ├── __init__.py
│   ├── truly_selective.py              # V1 - Basic (no repeated chars)
│   ├── truly_selective_v3.py           # V3 - OpenType (experimental)
│   ├── truly_selective_v4.py           # V4 - Unicode alternates (RECOMMENDED)
│   ├── unicode_alternates.json         # 700+ character mappings
│   ├── cyrillic.py                     # Cyrillic homoglyph technique
│   └── pua.py                          # Private Use Area technique
│
├── fonts/                              # Base fonts
│   └── Roboto.ttf                      # Base font with Unicode support
│
├── outputs/                            # Generated files (gitignored)
│   ├── {job_id}.pdf                    # Generated PDFs
│   ├── {job_id}_normal.ttf             # Normal fonts
│   ├── {job_id}_deceptive_v4.ttf       # Deceptive fonts
│   └── logs/{timestamp}_{job_id}/      # Detailed manipulation logs
│       └── steps.log
│
└── uploads/                            # Upload directory (future use)
```

## 🔍 How It Works

### V4 Algorithm (Recommended)

1. **Character Occurrence Tracking**
   - Track how many times each character appears in the hidden word

2. **Unicode Alternate Selection**
   - First occurrence: Use base character (e.g., 'a' U+0061)
   - Second occurrence: Use first alternate (e.g., 'ɑ' U+0251)
   - Third occurrence: Use second alternate (e.g., 'α' U+03B1)
   - Up to 10 occurrences supported

3. **Glyph Cloning**
   - Clone visual character's glyph outline to hidden character
   - Copy horizontal metrics (advance width, side bearings)
   - Update cmap (character to glyph mapping)

4. **PDF Generation**
   - Create LaTeX document with two fonts (normal and deceptive)
   - Compile with XeLaTeX
   - Result: Text displays as visual_word, copies as modified_hidden_word

### Example Flow

```python
visual_word = "hello"
hidden_word = "anita"

# Character mapping:
# Position 0: 'a' (first occurrence) → 'h'
# Position 1: 'n' → 'e'
# Position 2: 'i' → 'l'
# Position 3: 't' → 'l'
# Position 4: 'ɑ' U+0251 (second 'a' occurrence) → 'o'

# Modified hidden word: "anɑtɑ" (with Unicode alternate for second 'a')
# Displays as: "hello"
# Copies as: "anita" (with alternate Unicode character)
```

## 📊 Logging

Each manipulation creates detailed logs in `outputs/logs/{timestamp}_{job_id}/steps.log`

**Log Contents:**
- Job ID and timestamp
- Visual and hidden words
- Manipulation method
- Character-by-character mapping with Unicode codepoints
- Modified hidden word (with alternates)
- Font file paths

**Example Log:**
```
Job ID: 34451af5
Timestamp: 20251003_223155
Visual word: unidirectional
Hidden word: biidirectional
Method: Alternate Unicode Codepoints (V4) - Using JSON mappings
Creating character mappings:
  Pos 0: 'b' → 'u' (occurrence 1/1)
  Pos 1: 'i' → 'n' (occurrence 1/4)
  Pos 2: 'ı' (U+0131) → 'i' (occurrence 2/4)
  Pos 4: 'і' (U+0456) → 'i' (occurrence 3/4)
  Pos 9: 'ï' (U+00EF) → 'i' (occurrence 4/4)
Modified hidden word: 'biıdіrectïonal'
```

## ⚠️ Limitations

1. **Word Length**: Both words must be exactly the same length
2. **Character Occurrences**: Maximum 10 occurrences of same character
3. **XeLaTeX Required**: PDF generation requires XeLaTeX installed
4. **Base Font**: Requires font with comprehensive Unicode coverage (Roboto.ttf included)
5. **Visual Detection**: Unicode alternates are visually similar but may be detectable under close inspection

## 🛠️ Troubleshooting

### "Words must be same length" error
Ensure `visual_word` and `hidden_word` have identical character counts.

### "Character not in font" error
The base font (Roboto.ttf) doesn't contain the requested character. Try a different character.

### "no more alternates" warning in logs
Character appears more than 10 times. Solution only supports up to 10 occurrences.

### PDF generation fails
Ensure XeLaTeX is installed:
```bash
# macOS
brew install --cask mactex

# Ubuntu/Debian
sudo apt-get install texlive-xetex
```

## 📖 References

- arXiv:2505.16957 - Font Manipulation for Deceptive Documents
- Unicode Standard - https://unicode.org/
- OpenType Specification - https://docs.microsoft.com/en-us/typography/opentype/spec/

## 📝 License

For educational and research purposes only.

## 🤝 Contributing

See `SOLUTION_SUMMARY.md` for detailed technical documentation.

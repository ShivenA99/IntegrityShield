# Malicious Font Injection Attack Demonstration

This demonstration implements the malicious font injection attack described in the research paper: **"Invisible Prompts, Visible Threats: Malicious Font Injection in External Resources for Large Language Models"**.

## Overview

This attack creates a visual-semantic mismatch where:
- **Visual appearance**: Shows "Canada", "Ottawa", "Trudeau"
- **Actual text content**: Contains "Russia", "Moscow", "Putin"
- **AI systems**: Process the actual text content
- **Humans**: See the visual appearance

## Attack Technique

The attack works by manipulating the **cmap tables** in TrueType fonts:

1. **Font Manipulation**: Modify character-to-glyph mappings
2. **Character Substitution**: Map target characters to different glyphs
3. **Visual Deception**: Create documents that look benign to humans
4. **AI Vulnerability**: AI systems process the actual encoded text

### Character Mapping Example
```
R -> C  (Russia -> Canada)
U -> A
S -> N
S -> A
I -> D
A -> A
```

## Prerequisites

### Required Files
- `DejaVuSans.ttf` - Source font file (download from [DejaVu Fonts](https://dejavu-fonts.github.io/))

### Required Packages
```bash
pip install -r requirements.txt
# or:
pip install fonttools PyMuPDF
```

## Usage

### Quick Start
```bash
cd demo
python main.py
```

This will run the complete demonstration:
1. Create malicious font with manipulated cmap tables
2. Verify the font mappings are working correctly
3. Generate PDF documents with visual-semantic mismatch
4. Demonstrate the attack technique

### Prebuilt Pair-Font Mode (New)

You can now build a library of prebuilt pair-mapping fonts for a v1 charset (letters, digits, space), and render PDFs by selecting the appropriate pair-font per character position. This improves robustness for repeated characters and maintains copy/paste fidelity while fixing spacing.

1) Build prebuilt fonts (v1):
```bash
python demo/prebuilt_font_factory.py --charset v1 --source-font demo/DejaVuSans.ttf --out-dir demo/prebuilt_fonts/DejaVuSans/v1 --overwrite
```

2) Use prebuilt mode:
```bash
python demo/enhanced_main.py \
  --input-string "What is the capital of Russia?" \
  --input-entity "Russia" \
  --output-entity "Canada" \
  --font-mode prebuilt \
  --prebuilt-dir demo/prebuilt_fonts/DejaVuSans/v1
```

### v2 Charset (Printable ASCII, includes symbols and space)

- Build full v2 set (space to ~):
```bash
python demo/prebuilt_font_factory.py --charset v2 --source-font demo/DejaVuSans.ttf --out-dir demo/prebuilt_fonts/DejaVuSans/v2 --overwrite
```

- Build a small v2 subset quickly (recommended for tests):
```bash
python demo/prebuilt_font_factory.py \
  --charset v2 \
  --only-chars "abcXYZ012 -_/.:@#$&()[]{}!?" \
  --source-font demo/DejaVuSans.ttf \
  --out-dir demo/prebuilt_fonts/DejaVuSans/v2 --overwrite
```

Then run prebuilt mode with `--prebuilt-dir demo/prebuilt_fonts/DejaVuSans/v2`.

Notes:
- The base font `DejaVuSans.ttf` is copied into the prebuilt directory for registration.
- Spacing is measured using the base font metrics for consistent layout.
- Length mismatch support is handled via the v3 zero-width strategy (see below).

### v3 Charset (Zero-width strategy for length mismatch)

The v3 preset provides pair-fonts that map between `U+200B` (ZERO WIDTH SPACE) and printable ASCII. This enables visual-output and actual-text to have different lengths while preserving copy/paste fidelity and the surrounding layout.

- Build full v3 set:
```bash
python demo/prebuilt_font_factory.py --charset v3 --source-font demo/DejaVuSans.ttf --out-dir demo/prebuilt_fonts/DejaVuSans/v3 --overwrite
```

- Build full v3 in the background (recommended for complete library):
```bash
nohup python3 /Users/shivenagarwal/Desktop/Summer25/CG/Glyph-attack/demo/prebuilt_font_factory.py \
  --charset v3 \
  --source-font /Users/shivenagarwal/Desktop/Summer25/CG/Glyph-attack/demo/DejaVuSans.ttf \
  --out-dir /Users/shivenagarwal/Desktop/Summer25/CG/Glyph-attack/demo/prebuilt_fonts/DejaVuSans/v3 \
  --overwrite > /Users/shivenagarwal/Desktop/Summer25/CG/Glyph-attack/demo/malicious_font_pipeline.log 2>&1 &
```

- Use prebuilt v3 for rendering (handles length mismatch):
```bash
python demo/enhanced_main.py \
  --input-string "What is the capital of India?" \
  --input-entity "India" \
  --output-entity "China" \
  --font-mode prebuilt \
  --prebuilt-dir demo/prebuilt_fonts/DejaVuSans/v3
```

How it works:
- If the visual output is longer than the input entity, extra visual characters are drawn by inserting `U+200B` codepoints mapped to those glyphs.
- If the visual output is shorter than the input entity, surplus input characters are mapped to `U+200B` to hide them.
- Copy/paste fidelity is preserved because the original input codepoints remain in the text layer; only glyph selection changes.
- Spacing is measured using the base font to keep layout consistent.

### Individual Steps

#### Step 1: Create Malicious Font
```bash
python font_creator.py
```

#### Step 2: Verify Font
```bash
python font_verifier.py
```

#### Step 3: Generate PDFs
```bash
python pdf_generator.py
```

## Generated Files

After running the demonstration, you'll get:

- `malicious_font.ttf` - Font with manipulated cmap tables
- `malicious_document.pdf` - Demo document with visual-semantic mismatch
- `question_document.pdf` - Quiz document demonstrating the attack
- `malicious_font_demo.log` - Detailed execution log

Additional (enhanced prebuilt mode):
- Output is organized under `output/runs/run_<timestamp>/` with subfolders `pdfs/`, `fonts/`, and `metadata/`.
- A metadata JSON is written per run (e.g., `output/runs/<run_id>/metadata/...json`) including keys like `used_pairs`, `used_pair_counts`, `position_log`, and `length_mismatch`.

## Testing the Attack

### Method 1: PDF Viewer
1. Open any generated PDF file
2. Copy text from the document
3. Paste into a text editor or AI system
4. Observe the difference between visual and actual content

### Method 2: Font Analysis
```bash
python font_verifier.py
```

This will analyze the font structure and verify the character mappings.

## Technical Details

### Font Structure
- **cmap table**: Maps Unicode codepoints to glyph names
- **Glyph**: Visual representation of a character
- **PUA**: Private Use Area (Unicode range 0xE000-0xF000)

### Attack Implementation
1. Load source font using `fontTools`
2. Extract cmap table with `getBestCmap()`
3. Modify character mappings: `cmap[target_code] = display_glyph`
4. Save modified font with manipulated cmap

### PDF Generation
- Enhanced path uses `PyMuPDF (fitz)` to measure text widths with `fitz.Font` for consistent spacing.
- Prebuilt pair-fonts duplicate target glyphs to preserve `ToUnicode` mapping for copy/paste fidelity.

## Security Implications

### Potential Threats
- **Content Filter Bypass**: Malicious content appears benign
- **AI System Deception**: Systems process different content than humans see
- **Social Engineering**: Documents designed to deceive both humans and AI

### Mitigation Strategies
1. **Font Validation**: Verify font integrity in AI systems
2. **Character Analysis**: Process text at character level, not just visual
3. **Multiple Encoding**: Check various text encodings
4. **Font Whitelisting**: Only allow trusted fonts

## Research Context

This demonstration is based on the research paper that identified font manipulation as a novel attack vector against Large Language Models. The attack exploits the gap between visual representation and actual text content.

## Files Structure

```
demo/
├── main.py              # Main orchestration script (legacy demo)
├── enhanced_main.py     # Enhanced orchestration with prebuilt mode
├── enhanced_pdf_generator.py  # Prebuilt-mode PDF creation with spacing fix
├── prebuilt_font_factory.py   # Generates single pair-mapping fonts
├── README.md            # This file
└── requirements.txt     # Python dependencies
```

## Troubleshooting

### Common Issues

1. **Source font not found**
   - Download `DejaVuSans.ttf` from the official website
   - Place it in the demo directory

2. **Missing packages**
   - Install with: `pip install -r requirements.txt`

3. **Pair font missing or unknown file format**
   - Ensure you have built the required charset (v1/v2/v3) for your test
   - For v3, build the full set (see background command above)
   - Avoid limiting builds during tests unless you know exactly which pairs are needed

4. **Filenames with special characters**
   - Filenames are sanitized (e.g., `/` → `U+002F`, spaces may be normalized) to avoid path errors

5. **Uneven spacing when switching fonts**
   - The enhanced renderer measures widths using the base font and advances by the maximum of base vs pair width to avoid overlaps

### Debug Mode
Run individual scripts with verbose logging:
```bash
python -u demo/prebuilt_font_factory.py --help
python -u demo/enhanced_main.py --help
```

## Ethical Considerations

This demonstration is for **educational and research purposes only**. The techniques shown here should only be used to:
- Understand AI system vulnerabilities
- Develop better security measures
- Conduct legitimate security research

**Do not use these techniques for malicious purposes.**

Example of how to run using cli:

python3 demo/enhanced_main.py --input-string "What is the capital of Russia?" --input-entity "Russia" --output-entity "America" --font-mode prebuilt --prebuilt-dir demo/prebuilt_fonts/DejaVuSans/v3 | cat

## License

This demonstration is provided for educational purposes. Please use responsibly and in accordance with applicable laws and ethical guidelines. 
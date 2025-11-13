#!/usr/bin/env python3
"""
Font Manipulation Backend API
Implements multiple font manipulation techniques from arXiv:2505.16957
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from manipulators.truly_selective import TrulySelectiveManipulator
from manipulators.truly_selective_v3 import TrulySelectiveManipulatorV3
from manipulators.truly_selective_v4 import TrulySelectiveManipulatorV4
from manipulators.truly_selective_ligature import LigatureManipulator
from manipulators.cyrillic import CyrillicManipulator
from manipulators.pua import PUAManipulator

app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = Path(__file__).parent / 'uploads'
OUTPUT_FOLDER = Path(__file__).parent / 'outputs'
FONTS_FOLDER = Path(__file__).parent / 'fonts'

UPLOAD_FOLDER.mkdir(exist_ok=True)
OUTPUT_FOLDER.mkdir(exist_ok=True)

# Initialize manipulators
manipulators = {
    'truly_selective': TrulySelectiveManipulator(str(FONTS_FOLDER), str(OUTPUT_FOLDER)),
    'truly_selective_v3': TrulySelectiveManipulatorV3(str(FONTS_FOLDER), str(OUTPUT_FOLDER)),
    'truly_selective_v4': TrulySelectiveManipulatorV4(str(FONTS_FOLDER), str(OUTPUT_FOLDER)),
    'ligature': LigatureManipulator(str(FONTS_FOLDER), str(OUTPUT_FOLDER)),
    'cyrillic': CyrillicManipulator(str(FONTS_FOLDER), str(OUTPUT_FOLDER)),
    'pua': PUAManipulator(str(FONTS_FOLDER), str(OUTPUT_FOLDER))
}

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'version': '1.0.0',
        'manipulators': list(manipulators.keys())
    })

@app.route('/api/manipulate', methods=['POST'])
def manipulate():
    """
    Main manipulation endpoint.

    Request body:
    {
        "mode": "truly_selective" | "cyrillic" | "pua",
        "visual_word": "hello",
        "hidden_word": "world"
    }

    Returns:
    {
        "success": true,
        "pdf_url": "/api/download/abc123.pdf",
        "font_url": "/api/download/abc123.ttf",
        "message": "Success"
    }
    """
    try:
        data = request.json

        # Validate input
        mode = data.get('mode', 'truly_selective')
        visual_word = data.get('visual_word', '')
        hidden_word = data.get('hidden_word', '')

        if not visual_word or not hidden_word:
            return jsonify({
                'success': False,
                'error': 'Both visual_word and hidden_word are required'
            }), 400

        if len(visual_word) != len(hidden_word):
            return jsonify({
                'success': False,
                'error': 'Words must be the same length'
            }), 400

        if mode not in manipulators:
            return jsonify({
                'success': False,
                'error': f'Invalid mode. Choose from: {list(manipulators.keys())}'
            }), 400

        # Perform manipulation
        manipulator = manipulators[mode]
        result = manipulator.create_manipulation(visual_word, hidden_word)

        if result['success']:
            return jsonify({
                'success': True,
                'pdf_file': result['pdf_file'],
                'font_file': result.get('font_file'),
                'message': result.get('message', 'Manipulation successful'),
                'mode': mode
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'Manipulation failed')
            }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/download/<filename>', methods=['GET'])
def download_file(filename):
    """Download generated files."""
    file_path = OUTPUT_FOLDER / filename

    if not file_path.exists():
        return jsonify({
            'success': False,
            'error': 'File not found'
        }), 404

    return send_file(
        str(file_path),
        as_attachment=True,
        download_name=filename
    )

@app.route('/api/modes', methods=['GET'])
def get_modes():
    """Get available manipulation modes with descriptions."""
    return jsonify({
        'modes': [
            {
                'id': 'ligature',
                'name': 'Ligature (⭐ RECOMMENDED)',
                'description': 'Word-level OpenType ligature substitution. Creates a composite glyph that displays the visual word while preserving hidden word in text layer.',
                'pros': ['Most reliable', 'Fast (~3s)', 'Proper text layer', 'No length restrictions'],
                'cons': ['Requires LuaLaTeX']
            },
            {
                'id': 'truly_selective',
                'name': 'Truly Selective (Basic)',
                'description': 'Uses two fonts - only specific word instance is manipulated. Works when each character maps to one visual.',
                'pros': ['Clean output', 'No side effects', 'Professional'],
                'cons': ['Requires two fonts', 'Same character cannot have different visuals']
            },
            {
                'id': 'truly_selective_v4',
                'name': 'Truly Selective V4',
                'description': 'Two-font glyph cloning with pristine source copy. Works for same-length words.',
                'pros': ['Handles unique character mappings', 'Reliable for simple cases'],
                'cons': ['Same length required', 'Repeated character conflicts']
            },
            {
                'id': 'truly_selective_v3',
                'name': 'Truly Selective V3 (Experimental)',
                'description': 'Uses contextual alternates - affects ALL instances of pattern globally, not truly selective.',
                'pros': ['OpenType features'],
                'cons': ['Not truly selective', 'Global pattern matching']
            },
            {
                'id': 'cyrillic',
                'name': 'Cyrillic Homoglyphs',
                'description': 'Maps Cyrillic characters to Latin glyphs. Survives PDF encoding.',
                'pros': ['Single font', 'Survives extraction'],
                'cons': ['Copies as Cyrillic characters']
            },
            {
                'id': 'pua',
                'name': 'Private Use Area (PUA)',
                'description': 'Uses Unicode Private Use Area for custom mappings.',
                'pros': ['Precise control', 'No conflicts'],
                'cons': ['May not survive PDF encoding']
            }
        ]
    })

@app.route('/api/examples', methods=['GET'])
def get_examples():
    """Get example word pairs for testing."""
    return jsonify({
        'examples': [
            {'visual': 'hello', 'hidden': 'world'},
            {'visual': 'login', 'hidden': 'admin'},
            {'visual': 'click', 'hidden': 'trap!'},
            {'visual': 'safe', 'hidden': 'hack'},
            {'visual': 'read', 'hidden': 'exec'}
        ]
    })

if __name__ == '__main__':
    print("=" * 70)
    print("  FONT MANIPULATION API SERVER")
    print("=" * 70)
    print(f"  Fonts folder: {FONTS_FOLDER}")
    print(f"  Output folder: {OUTPUT_FOLDER}")
    print(f"  Available modes: {list(manipulators.keys())}")
    print("=" * 70)
    print()

    app.run(host='0.0.0.0', port=5001, debug=True)

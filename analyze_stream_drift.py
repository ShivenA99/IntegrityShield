#!/usr/bin/env python3
"""
Analyze PDF content stream drift issue in Method 2 (stream rewrite).

This script examines why the entire span text spacing gets changed when we
reconstruct TJ/Tj operators, causing overlays to misalign.
"""

import fitz
from PyPDF2 import PdfReader
from PyPDF2.generic import ContentStream, TextStringObject, ByteStringObject, NumberObject, ArrayObject
import json
from pathlib import Path

def analyze_content_stream_operators(pdf_path, page_num=0):
    """Extract and analyze TJ/Tj operators from a PDF page."""
    print(f"\n{'='*80}")
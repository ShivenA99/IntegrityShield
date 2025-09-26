#!/usr/bin/env python3
"""
Create a simple test font for demonstration purposes.
This creates a basic TTF font that can be used for testing.
"""

import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_simple_font():
    """
    Create a simple test font using fonttools.
    """
    try:
        from fontTools.ttLib import TTFont
        from fontTools.ttLib.tables import _c_m_a_p, _g_l_y_f, _h_e_a_d, _h_h_e_a, _m_a_x_p, _n_a_m_e, _p_o_s_t
        from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
        from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphCoordinates
        from fontTools.ttLib.tables._h_h_e_a import table__h_h_e_a
        from fontTools.ttLib.tables._m_a_x_p import table__m_a_x_p
        from fontTools.ttLib.tables._n_a_m_e import table__n_a_m_e
        from fontTools.ttLib.tables._p_o_s_t import table__p_o_s_t
        
        # Create a new font
        font = TTFont()
        
        # Add required tables
        font['head'] = _h_e_a_d.table__h_e_a_d()
        font['hhea'] = _h_h_e_a.table__h_h_e_a()
        font['maxp'] = _m_a_x_p.table__m_a_x_p()
        font['post'] = _p_o_s_t.table__p_o_s_t()
        font['name'] = _n_a_m_e.table__n_a_m_e()
        font['glyf'] = _g_l_y_f.table__g_l_y_f()
        font['cmap'] = _c_m_a_p.table__c_m_a_p()
        
        # Set up basic font properties
        font['head'].unitsPerEm = 1000
        font['head'].xMin = 0
        font['head'].yMin = 0
        font['head'].xMax = 1000
        font['head'].yMax = 1000
        
        # Create a simple cmap table
        cmap = font['cmap']
        subtable = CmapSubtable.newSubtable(4)
        subtable.platformID = 3
        subtable.platEncID = 1
        subtable.language = 0
        
        # Add basic character mappings
        cmap_table = {}
        for char in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789":
            cmap_table[ord(char)] = char
        
        subtable.cmap = cmap_table
        cmap.tables = [subtable]
        
        # Create basic glyphs
        glyf = font['glyf']
        for char in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789":
            glyph = Glyph()
            glyph.numberOfContours = 1
            glyph.xMin = 0
            glyph.yMin = 0
            glyph.xMax = 500
            glyph.yMax = 500
            glyf[char] = glyph
        
        # Add .notdef glyph
        notdef = Glyph()
        notdef.numberOfContours = 0
        notdef.xMin = 0
        notdef.yMin = 0
        notdef.xMax = 0
        notdef.yMax = 0
        glyf['.notdef'] = notdef
        
        # Save the font
        font_path = "DejaVuSans.ttf"
        font.save(font_path)
        logger.info(f"✓ Created test font: {font_path}")
        return True
        
    except ImportError:
        logger.error("fonttools not installed. Install with: pip install fonttools")
        return False
    except Exception as e:
        logger.error(f"Error creating test font: {e}")
        return False

if __name__ == "__main__":
    create_simple_font() 
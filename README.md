# INTEGRITY SHIELD

**A System for Ethical AI Use & Authorship Transparency in Assessments**

[![Demo Video](https://img.shields.io/badge/Demo-Video-red?logo=youtube)](https://youtu.be/77W_fWW2Agg)
[![Paper](https://img.shields.io/badge/Paper-EACL%202025-blue)](https://shivena99.github.io/IntegrityShield/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> **INTEGRITY SHIELD** is a document-layer watermarking system that embeds schema-aware, item-level watermarks into assessment PDFs while keeping their human-visible appearance unchanged. These watermarks consistently prevent MLLMs from answering shielded exam PDFs and encode stable, item-level signatures that can be reliably recovered from model or student responses.

---

## 🎯 Overview

Large language models (LLMs) can now solve entire exams directly from uploaded PDF assessments, raising urgent concerns about academic integrity and the reliability of grades and credentials. INTEGRITY SHIELD addresses this challenge through **document-layer watermarking** that:

- ✅ **Prevents AI solving**: 91–94% exam-level blocking across GPT-5, Claude Sonnet-4.5, Grok-4.1, and Gemini-2.5 Flash
- ✅ **Enables authorship detection**: 89–93% signature retrieval from model responses
- ✅ **Maintains visual integrity**: PDFs remain visually unchanged for human readers
- ✅ **Supports ethical assessment**: Provides interpretable authorship signals without invasive monitoring

### How It Works

INTEGRITY SHIELD exploits the **render-parse gap** in PDFs: what humans see often differs from what AI parsers ingest. By injecting invisible text, glyph remappings, and lightweight overlays, we influence model interpretation while leaving exams visually unchanged.

```
┌─────────────────┐
│  Upload Exam    │
│  PDF + Answers  │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  Extraction & Structure Analysis    │
│  • PyMuPDF + MLLM extraction        │
│  • Question type detection          │
│  • Answer schema identification     │
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  Schema-Aware Watermark Planning    │
│  • LLM-based tactic selection       │
│  • Per-question strategy            │
│  • Answer type logic                │
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  Watermark Engine Application       │
│  • code-glyph remapping             │
│  • Invisible text injection         │
│  • TrapDoc phantom tokens           │
│  • In-context watermarks (ICW)      │
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  Output Generation                  │
│  • Shielded PDF variants (IS-v1/v2) │
│  • Vulnerability reports            │
│  • Attribution signatures           │
└─────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.9+** (PyMuPDF compatibility)
- **Node.js 18+** and npm
- **PostgreSQL 14+** (or SQLite for local dev)
- **API Keys**: OpenAI, Anthropic, Google AI, and/or Mistral (at least one required)

### 1. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

**Configure Environment Variables:**

Create a `.env` file in the `backend/` directory:

```bash
# Environment Configuration
INTEGRITYSHIELD_ENV=development
INTEGRITYSHIELD_PORT=8000
INTEGRITYSHIELD_LOG_LEVEL=INFO

# Database Configuration
# SQLite (default for local dev):
INTEGRITYSHIELD_DATABASE_URL=sqlite:///./data/integrityshield.db
# PostgreSQL (production):
# INTEGRITYSHIELD_DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/integrityshield

# AI Provider API Keys (at least one required)
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
GOOGLE_AI_KEY=your_google_ai_key_here
MISTRAL_API_KEY=your_mistral_api_key_here

# Model Configuration
ANTHROPIC_MODEL=claude-sonnet-4-5-20250929
POST_FUSER_MODEL=gpt-5

# Development Tools
INTEGRITYSHIELD_ENABLE_DEV_TOOLS=true
INTEGRITYSHIELD_AUTO_APPLY_MIGRATIONS=true
```

**Start the Backend:**

```bash
# From the project root
bash backend/scripts/run_dev_server.sh
```

The server will start on `http://localhost:8000`. The startup script automatically:
- Loads environment variables from `backend/.env`
- Verifies required API keys
- Runs database migrations
- Starts the Flask server

### 2. Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

The frontend will be available at `http://localhost:5173`. The Vite dev server automatically proxies API requests to the backend.

---

## 📖 Usage Workflow

### Stage 1: Upload & Watermark Planning

1. **Upload Assessment**: Navigate to the dashboard and upload your exam PDF and answer key
2. **Structure Extraction**: The system automatically extracts question structure, detecting:
   - Multiple-choice questions (MCQ)
   - True/False questions
   - Long-form questions
   - Diagrams and tables
3. **Preview Strategy**: Review the planned watermark tactics for each question

### Stage 2: Watermark Embedding & AI Calibration

1. **Generate Shielded PDFs**: The system creates two watermark variants:
   - **IS-v1**: Lighter watermarking for minimal perturbation
   - **IS-v2**: Stronger multi-layer watermarking for maximum robustness
2. **AI Calibration**: Automatically evaluates watermark effectiveness across multiple MLLMs
3. **Review Reports**: Inspect prevention rates and detection reliability

### Stage 3: Authorship Analysis

1. **Deploy Assessment**: Distribute shielded PDF to students
2. **Collect Responses**: Export student answers from your LMS
3. **Analyze Authorship**: Upload responses to view:
   - Per-question watermark retrieval scores
   - Exam-level authorship degrees
   - Cohort-level distributions
4. **Human Review**: Use high authorship scores as signals for follow-up (oral checks, additional assessments)

---

## 🔬 Performance

Evaluated across 30 multi-page exams spanning STEM, humanities, and medical reasoning:

| Metric | GPT-5 | Claude Sonnet-4.5 | Grok-4.1 | Gemini-2.5 Flash |
|--------|-------|-------------------|----------|------------------|
| **Prevention (Exam-Level Blocking)** | 93.6% | 92.9% | 92.3% | 91.7% |
| **Detection (Signature Retrieval)** | 92.8% | 92.1% | 91.6% | 91.0% |

Compared to baselines:
- **ICW** (In-Context Watermarking): 3-7% prevention/detection
- **code-glyph**: 81-86% prevention/detection
- **TRAPDOC**: 40-89% prevention/detection (unstable across models)

---

## 🏗️ Architecture

### Backend (`backend/`)
- **Framework**: Flask with SQLAlchemy ORM
- **Database**: PostgreSQL (production) or SQLite (development)
- **Services**:
  - `DocumentIngestionService`: PDF parsing and structure extraction
  - `WatermarkPlanningService`: LLM-based strategy selection
  - `PdfRewritingService`: Document-layer watermark application
  - `AuthorshipService`: Response scoring and attribution

### Frontend (`frontend/`)
- **Framework**: React 18 + TypeScript
- **Build Tool**: Vite
- **UI Library**: InstUI (Instructure's Canvas design system)
- **State Management**: React Context API

### Watermarking Techniques

1. **Invisible Text Injection**: Hidden spans anchored near stems and options
2. **Glyph Remapping**: CMap-based font substitutions (visually identical, parsed differently)
3. **Off-Page Overlays**: Clipped content that influences parsing without visual changes
4. **Phantom Tokens**: TrapDoc-inspired document-layer perturbations

---

## 📚 Documentation

- **[Setup Guide](documentation/setup.md)**: Detailed installation and configuration
- **[API Reference](documentation/api.md)**: Backend endpoints and contracts
- **[Pipeline Stages](documentation/pipeline.md)**: Detailed stage descriptions
- **[Architecture](documentation/architecture.md)**: System design and data flow
- **[Troubleshooting](documentation/troubleshooting.md)**: Common issues and solutions

---

## 🤝 Contributing

We welcome contributions from the research community! To contribute:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Make your changes with clear commit messages
4. Add or update tests as appropriate
5. Update documentation
6. Submit a pull request

Please ensure your code follows the existing style and passes all tests.

---

## 📄 Citation

If you use INTEGRITY SHIELD in your research, please cite our paper:

```bibtex
@inproceedings{shekhar2025integrityshield,
  title={INTEGRITY SHIELD: A System for Ethical AI Use \& Authorship Transparency in Assessments},
  author={Shekhar, Ashish Raj and Agarwal, Shiven and Bordoloi, Priyanuj and Shah, Yash and Anvekar, Tejas and Gupta, Vivek},
  booktitle={Proceedings of the 2025 Conference of the European Chapter of the Association for Computational Linguistics (EACL)},
  year={2025}
}
```

---

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## ⚠️ Ethics & Responsible Use

INTEGRITY SHIELD is designed for **ethical and transparent AI use in educational assessment settings**. The system:

- **Does NOT monitor students**: No keystroke logging, webcam tracking, or device control
- **Respects privacy**: All data stays within institutional infrastructure
- **Requires transparency**: Institutions should communicate AI-use policies and watermarking presence to students
- **Supports human judgment**: Authorship scores are signals for review, not automatic evidence for sanctions

### Intended Use

- ✅ Formal educational assessments with clear governance
- ✅ Research on AI-assisted learning and academic integrity
- ✅ Institutional policy development for ethical AI use

### Not Intended For

- ❌ Surveillance or covert monitoring
- ❌ Automatic sanctions without human review
- ❌ Non-assessment documents without clear authorization

---

## 🙏 Acknowledgments

This work was conducted at Arizona State University. We thank the research community for valuable feedback and discussions on ethical AI use in education.

**Authors**: Ashish Raj Shekhar*, Shiven Agarwal*, Priyanuj Bordoloi, Yash Shah, Tejas Anvekar, Vivek Gupta
*Equal contribution

---

## 📞 Contact

For questions, issues, or collaboration opportunities:
- **Project Page**: [https://shivena99.github.io/IntegrityShield/](https://shivena99.github.io/IntegrityShield/)
- **Demo**: [https://shivena99.github.io/IntegrityShield/](https://shivena99.github.io/IntegrityShield/)
- **Issues**: [GitHub Issues](https://github.com/ShivenA99/IntegrityShield/issues)

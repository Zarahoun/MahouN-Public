#!/usr/bin/env python3
"""Extract content from patent Word documents."""

from docx import Document
from pathlib import Path
import json

def extract_docx(path):
    """Extract text from a Word document."""
    try:
        doc = Document(path)
        content = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                content.append(text)
        return "\n".join(content)
    except Exception as e:
        return f"Error reading {path}: {e}"

# Extract all patent documents
patent_dir = Path("patent")
docs = {}

for docx_file in sorted(patent_dir.glob("*.docx")):
    print(f"Extracting: {docx_file.name}")
    content = extract_docx(docx_file)
    docs[docx_file.stem] = content
    
    # Save individual text file
    txt_file = patent_dir / f"{docx_file.stem}.txt"
    with open(txt_file, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  Saved to: {txt_file.name}")

# Save all as JSON
json_file = patent_dir / "extracted_content.json"
with open(json_file, 'w', encoding='utf-8') as f:
    json.dump(docs, f, ensure_ascii=False, indent=2)

print(f"\nAll content saved to: {json_file}")
print(f"Total documents: {len(docs)}")

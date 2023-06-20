import os
from autoRLMU import AnnotationMakerNew

os.system('cls')
pdf_paths = []
# pdf_path: str = r"example_pdfs/new_type_old_in_reality.pdf"
# pdf_path: str = r"example_pdfs/new_type_1.pdf"
# pdf_path: str = r"example_pdfs/3000-T-01-32-D-0016-01-E#XA.pdf"
# pdf_path: str = r"example_pdfs/3000-T-01-37-D-017-01-E#XA.pdf"
pdf_path: str = r"example_pdfs/3000-T-01-32-D-0018-01-E#XA.pdf"
pdf_paths.append(pdf_path)
pdf_path: str = r"example_pdfs/3000-T-01-32-D-0017-01-E#XA.pdf"
pdf_paths.append(pdf_path)

for pdf_path in pdf_paths:
    loop_drawing = AnnotationMakerNew()
    is_redlined_successfully = loop_drawing.make_redline(pdf_path, dpi=300)


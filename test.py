import os
from autoRLMU import AnnotationMakerNew

os.system('cls')
# pdf_path: str = r"example_pdfs/new_type_old_in_reality.pdf"
pdf_path: str = r"example_pdfs/new_type_1.pdf"

loop_drawing = AnnotationMakerNew()
is_redlined_successfully = loop_drawing.make_redline(pdf_path)


import os
from autoRLMU import AnnotationMakerNew

os.system('cls')
pdf_path: str = r"example_pdfs/new_type.pdf"

loop_drawing = AnnotationMakerNew()
is_redlined_successfully = loop_drawing.make_redline(pdf_path, is_link=False)


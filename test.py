import os
from autoRLMU import AnnotationMakerNew

os.system('cls')

pdf_paths = list()

# pdf_paths.append(r"example_pdfs/new_type_old_in_reality.pdf")
# pdf_paths.append(r"example_pdfs/3000-T-01-32-D-0016-01-E#XA.pdf")
# pdf_paths.append(r"example_pdfs/3000-T-01-37-D-0120-01-E#XA.pdf")
# pdf_paths.append(r"example_pdfs/3000-T-01-32-D-0018-01-E#XA.pdf")
# pdf_paths.append(r"example_pdfs/3000-T-01-32-D-0017-01-E#XA.pdf")
# pdf_paths.append(r"example_pdfs/new_type.pdf")
# pdf_paths.append(r"example_pdfs/new_type_1.pdf")
# pdf_paths.append(r"example_pdfs/new_type_2.pdf")
pdf_paths.append(r"example_pdfs/3000-T-01-37-D-0078-01-E#XA.pdf")

for pdf_path in pdf_paths:
    loop_drawing = AnnotationMakerNew()
    # 730   12    1176    710
    # loop_drawing.set_crop_rectangle(930, 200, 240, 300)
    is_redlined_successfully = loop_drawing.make_redline(pdf_path, dpi=300)


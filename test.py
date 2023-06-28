import os
from autoRLMU import AnnotationMakerNew, AnnotationMakerOld

os.system('cls')

pdf_paths = list()

# pdf_paths.append(r"example_pdfs/new_type_old_in_reality.pdf")
# pdf_paths.append(r"example_pdfs/new_type.pdf")
# pdf_paths.append(r"example_pdfs/new_type_1.pdf")
# pdf_paths.append(r"example_pdfs/new_type_2.pdf")
# pdf_paths.append(r"example_pdfs/4000-T-61-30-D-4903-79-E#XB.pdf")
# pdf_paths.append(r"example_pdfs/4000-T-01-37-D-0015-02-E#XB.pdf")
pdf_paths.append(r"example_pdfs/2.pdf")
# pdf_paths.append(r"example_pdfs/1.pdf")


for pdf_path in pdf_paths:
    loop_drawing = AnnotationMakerOld()
    # loop_drawing.set_crop_rectangle_wh(762, 107, 157, 646)
    is_redlined_successfully = loop_drawing.make_redline(pdf_path, dpi=300, tries_to_rotate=0)


import fitz
from PIL import Image
import cv2
import numpy as np

pdf_path = 'pdfs/2.pdf'

doc = fitz.open(pdf_path)
page = doc.load_page(0)

pix = page.get_pixmap(dpi=150)

PIL_page_image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
open_cv_page_image = np.array(PIL_page_image)

grayed_page_image = cv2.cvtColor(open_cv_page_image, cv2.COLOR_BGR2GRAY)

empty_template = np.zeros([200, 400, 1], dtype=np.uint8)
empty_template.fill(254)
template_h, template_w = empty_template.shape[0:2]

print(f'empty_template type:{empty_template.dtype}')
print(f'empty_template shape:{empty_template.shape}')

match_method = cv2.TM_SQDIFF
res = cv2.matchTemplate(grayed_page_image, empty_template, match_method)
# cv2.normalize(res, res, 0, 1, cv2.NORM_MINMAX, -1) # it seems like it is not needed
min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res, None)
if match_method in (cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED):
    location = min_loc
else:
    location = max_loc

bottom_right = (location[0] + template_w, location[1] + template_h)
cv2.rectangle(open_cv_page_image, location, bottom_right, (0, 255, 0), 2)
# cv2.rectangle(open_cv_page_image, (5, 5), (205, 105), (0, 255, 0), 2) # test rectangle

cv2.imshow('test', open_cv_page_image)
cv2.imwrite('images/test_template.png', open_cv_page_image)
cv2.waitKey(0)
cv2.destroyAllWindows()
# template = cv2.

doc.close()

from paddleocr import PaddleOCR
import fitz
from PIL import Image, ImageDraw
import numpy as np
import logging

Points4 = list[list[float, float], list[float, float], list[float, float], list[float, float]]

pdf_path = 'pdfs/1.pdf'

logging.basicConfig(filename='autoRLMU.log', filemode="w", level=logging.INFO,
                    format='%(asctime)s -  %(levelname)s -  %(message)s')

dpi = 150  # change zoom_factor if change this!!!
pdf_zoom_factor = 0.48
crop_x_start = 2060  # depends on dpi
crop_y_start = 130  # depends on dpi
crop_x_bottom = 2400  # depends on dpi
crop_y_bottom = 1300  # depends on dpi


def get_points_from_cropped(p1: tuple[float, float], p2: tuple[float, float], crop_x=crop_x_start, crop_y=crop_y_start):
    return (p1[0] + crop_x, p1[1] + crop_y), (p2[0] + crop_x, p2[1] + crop_y)


def get_rect_from_xywh(top_left_x: float, top_left_y: float, rect_width: float, rect_height: float) -> fitz.Rect:
    tl_point = fitz.Point(top_left_x, top_left_y)
    if page.rotation in (90, -90, 270):
        tl_point *= page.derotation_matrix
        rect_width, rect_height = rect_height, rect_width
    if page.rotation == 180:
        tl_point *= page.derotation_matrix
        tl_point[0] -= rect_width
        tl_point[1] -= rect_height
    if page.rotation == 270:
        tl_point[0] -= rect_width
    if page.rotation == 90:
        tl_point[1] -= rect_height
    br_point = fitz.Point(tl_point[0] + rect_width, tl_point[1] + rect_height)
    return fitz.Rect(tl_point, br_point)


def get_pdfed_rect(x0: float, y0: float, x1: float, y1: float, zoom_factor: float = 1.0) -> fitz.Rect:
    width = (x1 - x0) * zoom_factor
    height = (y1 - y0) * zoom_factor
    x = x0 * zoom_factor
    y = y0 * zoom_factor
    return get_rect_from_xywh(x, y, width, height)


tries_to_rotate: int = 4

found_FCS_block: Points4 = list()
found_node_rect: Points4 = list()
found_node_number_rect: Points4 = list()
found_node_number_rects: list[Points4] = list()
node_number_text = ''
new_node_number_text = '?'  # Fieldbus has 2 nodes, the code needs to be modified accordingly
node_x0 = node_x2 = node_y2 = 0
image_cropped = page_PIL_image = draw = None

what_to_find = ('FCS07', 'FCSO7')
replaced_with_full = what_to_replace = what_to_find  # it will be changed later anyway, to get rid of warnings
replaced_with = 'FCS14'
node_texts = ('NODE', 'NCDE', 'N0DE')

pdf_path_annotated = pdf_path[:-4] + '_annotated' + pdf_path[-4:]
print(f'working with {pdf_path[5:]}...')
doc = fitz.open(pdf_path)
page = doc.load_page(0)

while tries_to_rotate > 0:
    pix = page.get_pixmap(dpi=dpi)

    page_PIL_image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    page_PIL_image.save('images/img_original.png', format='PNG')

    image_cropped: Image = page_PIL_image.crop((crop_x_start, crop_y_start, crop_x_bottom, crop_y_bottom))

    # noinspection PyTypeChecker
    image_cropped_na = np.asarray(image_cropped)

    ocr = PaddleOCR(use_angle_cls=True, lang='en',
                    show_log=False)  # need to run only once to download and load model into memory
    result = ocr.ocr(image_cropped_na, cls=True)

    data = result[0]

    logging.info(result)

    draw = ImageDraw.Draw(image_cropped)

    for block in data:
        # xy – Two points to define the bounding box.
        # Sequence of either [(x0, y0), (x1, y1)] or [x0, y0, x1, y1], where x1 >= x0 and y1 >= y0.
        # draw a rectangle for ALL texts found
        draw.rectangle((tuple(block[0][0]), tuple(block[0][2])), width=2, outline='red')
        coordinates: Points4 = block[0]
        text: str = block[1][0]
        if text[:5] in what_to_find:
            found_FCS_block = coordinates
            what_to_replace = text
            what_to_add = text[5:]
            replaced_with_full = replaced_with + what_to_add
        if text in node_texts:
            found_node_rect = coordinates
            node_x0, node_x2, node_y2 = coordinates[0][0], coordinates[2][0], coordinates[2][1]
        if found_node_rect is not None and set(text).issubset('0123456789'):
            text_x1, text_y1 = coordinates[1][0], coordinates[1][1]
            if node_x0 < text_x1 < node_x2 and text_y1 > node_y2:
                found_node_number_rect = coordinates
                found_node_number_rects.append(found_node_number_rect)
                node_number_text = text
                new_node_number_text = str(int(node_number_text) + 1)

    if not found_node_rect:
        print(f'NODE was not found')
    else:
        print(f'NODE was found in {found_node_rect}')

    if not found_FCS_block:
        print(f'{what_to_find} was not found')
        page.set_rotation(page.rotation + 90)
        tries_to_rotate -= 1
        if tries_to_rotate == 0:
            quit()
    else:
        print(f'{what_to_replace} was found in {found_FCS_block}')
        tries_to_rotate = 0

# noinspection PyTypeChecker
FCS_top_left_cropped: tuple[float, float] = tuple(found_FCS_block[0])  # top left coordinates as tuple
# noinspection PyTypeChecker
FCS_bottom_right_cropped: tuple[float, float] = tuple(found_FCS_block[2])  # bottom right coordinates as tuple

FCS_top_left, FCS_bottom_right = get_points_from_cropped(FCS_top_left_cropped, FCS_bottom_right_cropped)

FCS_new_x0: float = FCS_bottom_right[0] + 5
FCS_new_y0: float = FCS_top_left[1]
FCS_new_x1: float = FCS_new_x0 + (FCS_bottom_right[0] - FCS_top_left[0]) + 10
FCS_new_y1: float = FCS_new_y0 + (FCS_bottom_right[1] - FCS_top_left[1]) + 10

draw.rectangle((FCS_top_left_cropped, FCS_bottom_right_cropped), outline='blue', width=2)
image_cropped.save('images/img_cropped.png', format='PNG')

draw = ImageDraw.Draw(page_PIL_image)
draw.rectangle((FCS_top_left, FCS_bottom_right), outline='blue', width=2)
logging.info(f'box_top_left={FCS_top_left}, box_bottom_right={FCS_bottom_right}')
page_PIL_image.save('images/img_original_marked.png', format='PNG')

FCS_new_text_rect = get_pdfed_rect(FCS_new_x0, FCS_new_y0, FCS_new_x1, FCS_new_y1, zoom_factor=pdf_zoom_factor)
FCS_found_text_rect = get_pdfed_rect(*FCS_top_left, *FCS_bottom_right, zoom_factor=pdf_zoom_factor)

page.add_line_annot((FCS_found_text_rect[0], FCS_found_text_rect[1]),
                    (FCS_found_text_rect[2], FCS_found_text_rect[3]))
page.add_freetext_annot(FCS_new_text_rect, replaced_with_full,
                        text_color=(255, 0, 0), border_color=None,
                        rotate=page.rotation, fontsize=8)

for NN in found_node_number_rects:
    # noinspection PyTypeChecker
    NN_top_left_cropped: tuple[float, float] = (*NN[0],)  # top left coordinates as tuple
    # noinspection PyTypeChecker
    NN_bottom_right_cropped: tuple[float, float] = tuple(NN[2])  # bottom right coordinates as tuple
    NN_top_left, NN_bottom_right = get_points_from_cropped(NN_top_left_cropped, NN_bottom_right_cropped)
    NN_new_x0: float = NN_bottom_right[0] + 5
    NN_new_y0: float = NN_top_left[1]
    NN_new_x1: float = NN_new_x0 + (NN_bottom_right[0] - NN_top_left[0]) + 10
    NN_new_y1: float = NN_new_y0 + (NN_bottom_right[1] - NN_top_left[1]) + 10
    NN_new_text_rect: fitz.Rect = get_pdfed_rect(NN_new_x0, NN_new_y0, NN_new_x1, NN_new_y1,
                                                 zoom_factor=pdf_zoom_factor)
    node_number_text_rect: fitz.Rect = get_pdfed_rect(*NN_top_left, *NN_bottom_right, zoom_factor=pdf_zoom_factor)

    page.add_line_annot((node_number_text_rect[0], node_number_text_rect[1]),
                        (node_number_text_rect[2], node_number_text_rect[3]))
    page.add_freetext_annot(NN_new_text_rect, new_node_number_text,
                            text_color=(255, 0, 0), border_color=None,
                            rotate=page.rotation, fontsize=8)

stamp_rect = (1400, 1000, 1800, 1200)
stamp_rect = get_pdfed_rect(*stamp_rect, zoom_factor=pdf_zoom_factor)

# insert_image(rect, filename=None, pixmap=None, stream=None, mask=None,
# rotate=0, alpha=-1, oc=0, xref=0, keep_proportion=True, overlay=True)
page.insert_image(stamp_rect, filename='images/RLMU_Stamp.png', keep_proportion=True,
                  overlay=True, rotate=page.rotation)

print(f'page rotation: {page.rotation}')

doc.save(pdf_path_annotated)
doc.close()

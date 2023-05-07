from paddleocr import PaddleOCR
import fitz
from PIL import Image, ImageDraw
import numpy as np
import cv2
import requests

Points4 = list[list[float, float], list[float, float], list[float, float], list[float, float]]

dpi = 150  # change zoom_factor if change this!!!
pdf_zoom_factor = 0.48  # calculated from 96/150, as most loop drawings are stored in dpi=150, but showed in dpi=96
crop_x_start = 2060  # depends on dpi
crop_y_start = 130  # depends on dpi
crop_x_bottom = 2400  # depends on dpi
crop_y_bottom = 1300  # depends on dpi


def get_points_from_cropped(p1: tuple[float, float], p2: tuple[float, float], crop_x=crop_x_start, crop_y=crop_y_start):
    return (p1[0] + crop_x, p1[1] + crop_y), (p2[0] + crop_x, p2[1] + crop_y)


def get_rect_from_xywh(top_left_x: float, top_left_y: float,
                       rect_width: float, rect_height: float, page: fitz.Page) -> fitz.Rect:
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


def get_pdfed_rect(x0: float, y0: float, x1: float, y1: float, page: fitz.Page, zoom_factor: float = 1.0) -> fitz.Rect:
    width = (x1 - x0) * zoom_factor
    height = (y1 - y0) * zoom_factor
    x = x0 * zoom_factor
    y = y0 * zoom_factor
    return get_rect_from_xywh(x, y, width, height, page)


# returns True if success, otherwise False
def make_redline(pdf_path_param: str, is_link: bool = False) -> bool:
    # path or link to a pdf file
    if pdf_path_param in ('', None):
        raise ValueError('Path or link cannot be empty')
    else:
        pdf_path = pdf_path_param

    tries_to_rotate: int = 4

    # initialization
    found_FCS_block: Points4 = list()
    found_node_rect: Points4 = list()
    found_node_number_rects: list[Points4] = list()
    new_node_number_text = '?'
    node_x0 = node_x2 = node_y2 = 0
    image_cropped = PIL_page_image = draw = open_cv_page_image = None
    what_to_find = ('FCS07', 'FCSO7')
    replaced_with_full = what_to_replace = what_to_find  # it will be changed later anyway, to get rid of warnings
    replaced_with = 'FCS14'
    node_texts = ('NODE', 'NCDE', 'N0DE')

    if is_link:
        # if pdf_path_param is a link
        print(f'Loading the file from URL...')
        response = requests.get(pdf_path)
        print(f'response.status_code: {response.status_code}')
        if response.status_code != requests.codes.ok:
            print(f'File cannot be open, aborting...')
            return False
        try:
            doc = fitz.open(stream=response.content, filetype="pdf")
        except:
            print(f'File cannot be open, aborting...')
            return False
        # RECODE IN FUTURE!!!
        pdf_path_annotated = 'pdfs\link_annotated.pdf'
    else:
        # if pdf_path_param is a path, add '_annotated' to the file name
        pdf_path_annotated = pdf_path[:-4] + '_annotated' + pdf_path[-4:]
        # open the pdf file
        print(f'Opening {pdf_path[5:]}...')
        try:
            doc = fitz.open(pdf_path)
        except:
            print(f'File cannot be open, aborting...')
            return False

    # load the only page
    page = doc.load_page(0)

    # the rotation is unknown, so we try to find the text max 4 times, finishing if a success and
    # rotating the page if a failure
    while tries_to_rotate > 0:
        # extract fitz image from the page with particular dpi
        # most loop drawings are stored in dpi=150, but showed in dpi=96
        pix = page.get_pixmap(dpi=dpi)

        # converting into pillow format and saving
        PIL_page_image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
        PIL_page_image.save('images/img_original.png', format='PNG')
        open_cv_page_image = np.array(PIL_page_image)

        # cropping the right part of the image
        image_cropped: Image = PIL_page_image.crop((crop_x_start, crop_y_start, crop_x_bottom, crop_y_bottom))

        # converting the pillow image into nampy array
        # noinspection PyTypeChecker
        image_cropped_na = np.asarray(image_cropped)

        # need to run only once to download and load model into memory
        ocr = PaddleOCR(use_angle_cls=True, lang='en',
                        show_log=False)
        # OCR-ing the cropped image
        result = ocr.ocr(image_cropped_na, cls=True)

        # as there is only one page, the result contains only one element
        data = result[0]

        # preparing to draw on the cropped image
        draw = ImageDraw.Draw(image_cropped)

        # checking every block of text
        for block in data:
            # draw a RED rectangle for ALL texts found
            draw.rectangle((tuple(block[0][0]), tuple(block[0][2])), width=2, outline='red')
            # saving coordinates for later
            coordinates: Points4 = block[0]
            # saving text for later
            text: str = block[1][0]
            # checking first five symbols for the desired text ('FCS07' in our case)
            if text[:5] in what_to_find:
                # saving coordinates of the desired text ('FCS07' in our case)
                found_FCS_block = coordinates
                # forming a full text which replaces the old one
                what_to_replace = text
                what_to_add = text[5:]
                replaced_with_full = replaced_with + what_to_add
            # checking if it is the 'NODE' text
            if text in node_texts:
                # saving the 'NODE' text coordinates for later
                found_node_rect = coordinates
                node_x0, node_x2, node_y2 = coordinates[0][0], coordinates[2][0], coordinates[2][1]
            # checking the actual node number text, it makes sense only after the 'NODE' text has already been found
            if found_node_rect is not None and set(text).issubset('0123456789'):
                # checking if the coordinates of the digits are under the 'NODE' text
                text_x1, text_y1 = coordinates[1][0], coordinates[1][1]
                if node_x0 < text_x1 < node_x2 and text_y1 > node_y2:
                    # as there can be more than one node number (i.e. for Fieldbus),
                    # we need to have the list of rectangles
                    found_node_number_rects.append(coordinates)
                    # forming the new node number text
                    new_node_number_text = str(int(text) + 1)

        if not found_node_rect:
            print(f'NODE was not found')
        else:
            print(f'NODE was found in {found_node_rect}')

        # if the FCS text was not found, rotate the page and decrement the number of tries left
        if not found_FCS_block:
            print(f'{what_to_find} was not found')
            page.set_rotation(page.rotation + 90)
            tries_to_rotate -= 1
            print(f'Rotating the page, {tries_to_rotate} tries left...')
            # if no tries left - quit the script
            if tries_to_rotate == 0:
                quit()
        else:
            print(f'{what_to_replace} was found in {found_FCS_block}')
            # as we found the FCS text, there is no need to rotate the page and searching the text again
            tries_to_rotate = 0

    # getting the actual FCS text coordinates from the cropped one
    # noinspection PyTypeChecker
    FCS_top_left_cropped: tuple[float, float] = tuple(found_FCS_block[0])  # top left coordinates as tuple
    # noinspection PyTypeChecker
    FCS_bottom_right_cropped: tuple[float, float] = tuple(found_FCS_block[2])  # bottom right coordinates as tuple
    FCS_top_left, FCS_bottom_right = get_points_from_cropped(FCS_top_left_cropped, FCS_bottom_right_cropped)

    # calculating the coordinates of the new FCS text
    FCS_new_x0: float = FCS_bottom_right[0] + 5
    FCS_new_y0: float = FCS_top_left[1]
    FCS_new_x1: float = FCS_new_x0 + (FCS_bottom_right[0] - FCS_top_left[0]) + 10
    FCS_new_y1: float = FCS_new_y0 + (FCS_bottom_right[1] - FCS_top_left[1]) + 10

    # drawing FCS rectangle on the cropped image and saving it for debug purposes
    draw.rectangle((FCS_top_left_cropped, FCS_bottom_right_cropped), outline='blue', width=2)
    image_cropped.save('images/img_cropped.png', format='PNG')

    # drawing on the page image and saving it for debug purposes
    draw = ImageDraw.Draw(PIL_page_image)
    draw.rectangle((FCS_top_left, FCS_bottom_right), outline='blue', width=2)
    PIL_page_image.save('images/img_original_marked.png', format='PNG')

    # calculating pdf coordinates for FCS annotations
    FCS_new_text_rect = get_pdfed_rect(FCS_new_x0, FCS_new_y0, FCS_new_x1, FCS_new_y1, page,
                                       zoom_factor=pdf_zoom_factor)
    FCS_found_text_rect = get_pdfed_rect(*FCS_top_left, *FCS_bottom_right, page, zoom_factor=pdf_zoom_factor)

    # adding FCS annotations into pdf
    page.add_line_annot((FCS_found_text_rect[0], FCS_found_text_rect[1]),
                        (FCS_found_text_rect[2], FCS_found_text_rect[3]))
    page.add_freetext_annot(FCS_new_text_rect, replaced_with_full,
                            text_color=(255, 0, 0), border_color=None,
                            rotate=page.rotation, fontsize=8)

    # calculating Node numbers coordinates
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
        NN_new_text_rect: fitz.Rect = get_pdfed_rect(NN_new_x0, NN_new_y0, NN_new_x1, NN_new_y1, page,
                                                     zoom_factor=pdf_zoom_factor)
        node_number_text_rect: fitz.Rect = get_pdfed_rect(*NN_top_left, *NN_bottom_right, page,
                                                          zoom_factor=pdf_zoom_factor)

        # adding Node numbers annotations into pdf
        page.add_line_annot((node_number_text_rect[0], node_number_text_rect[1]),
                            (node_number_text_rect[2], node_number_text_rect[3]))
        page.add_freetext_annot(NN_new_text_rect, new_node_number_text,
                                text_color=(255, 0, 0), border_color=None,
                                rotate=page.rotation, fontsize=8)

    # defining static coordinates for the stamp is a bad idea, because the stamp may overlap with useful info
    # stamp_rect = (1400, 1000, 1800, 1200)
    # instead, we find an empty space for the stamp!
    grayed_page_image = cv2.cvtColor(open_cv_page_image, cv2.COLOR_BGR2GRAY)

    # create a grayscale image 200x400
    empty_template = np.zeros([200, 400, 1], dtype=np.uint8)
    # fill with 254 color (255 is white in grayscale), for some reason it is the prevailing color
    empty_template.fill(254)
    # getting width and height to calculate the rectangle later
    template_h, template_w = empty_template.shape[0:2]

    # finding an empty space
    match_method = cv2.TM_SQDIFF
    res = cv2.matchTemplate(grayed_page_image, empty_template, match_method)
    # cv2.normalize(res, res, 0, 1, cv2.NORM_MINMAX, -1) # it seems like it is not needed
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res, None)
    if match_method in (cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED):
        location = min_loc
    else:
        location = max_loc

    # calculating the stamp rectangle coordinates
    bottom_right = (location[0] + template_w, location[1] + template_h)
    stamp_rect = (location, bottom_right)
    stamp_rect = get_pdfed_rect(*stamp_rect[0], *stamp_rect[1], page, zoom_factor=pdf_zoom_factor)

    # adding the stamp
    page.insert_image(stamp_rect, filename='images/RLMU_Stamp.png', keep_proportion=True,
                      overlay=True, rotate=page.rotation)

    # saving the annotated pdf and closing the document
    print(f'Saving the annotated pdf and closing the document...')
    doc.save(pdf_path_annotated)
    doc.close()
    print(f'******************************************************')

    return True

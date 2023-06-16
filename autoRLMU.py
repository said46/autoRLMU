import PIL.ImageDraw
from paddleocr import PaddleOCR
import fitz
from PIL import Image, ImageDraw
import numpy as np
# import cv2
# such import resolves "Cannot find reference 'xxx' in '__init__.py | __init__.py'" issue
from cv2 import cv2
import requests

Points4 = list[list[float, float], list[float, float], list[float, float], list[float, float]]


class AnnotationMaker:
    DPI = 150  # change zoom_factor if change this!!!
    PDF_ZOOM_FACTOR = 0.48  # calculated from 96/150, as most loop drawings are stored in dpi=150, but showed in dpi=96
    CROP_X0 = 2060  # depends on dpi
    CROP_Y0 = 130  # depends on dpi
    CROP_X1 = 2400  # depends on dpi
    CROP_Y1 = 1300  # depends on dpi
    NODE_TEXTS = ('NODE', 'NCDE', 'N0DE')
    FCS_TEXT_TO_FIND = ('FCS07', 'FCSO7')
    FCS_TEXT_TO_REPLACE_WITH = 'FCS14'
    _doc: fitz.Document
    _page: fitz.Page

    def __init__(self, pdf_path_annotated='pdfs/DEFAULT_annotated.pdf'):
        self._pdf_path_annotated: str = pdf_path_annotated
        self._error_description = ''
        self._fcs_found_text_rect = None
        self._ocr_result_data = []
        self._pdf_path: str = ''
        self._is_link: bool = False
        self._tries_to_rotate: int = 4
        self._replaced_with = self._what_to_replace = ''
        self._node_number_rects: list[Points4] = list()
        self._new_node_number_text: str = '?'
        self._node_text_x0 = self._node_text_x2 = self._node_text_y2 = 0
        self._page_pillow_image_cropped: PIL.Image = None
        self._page_pillow_image: PIL.Image = None
        self._page_opencv_image: np.ndarray = None
        self._cropped_page_opencv_image: np.ndarray = None
        self._doc = None
        self._page = None
        self._log: list[str] = []
        # need to run only once to download and load model into memory
        self._ocr: PaddleOCR.ocr = PaddleOCR(use_angle_cls=True, lang='en', show_log=False)

    def __del__(self):
        if self._doc is not None:
            self._doc.close()

    @classmethod
    def _get_points_from_cropped(cls, p1: tuple[float, float], p2: tuple[float, float]):
        return (p1[0] + cls.CROP_X0, p1[1] + cls.CROP_Y0), (p2[0] + cls.CROP_X0, p2[1] + cls.CROP_Y0)

    def _get_rect_from_xywh(self, top_left_x: float, top_left_y: float,
                            rect_width: float, rect_height: float) -> fitz.Rect:
        tl_point = fitz.Point(top_left_x, top_left_y)
        if self._page.rotation in (90, -90, 270):
            tl_point *= self._page.derotation_matrix
            rect_width, rect_height = rect_height, rect_width
        if self._page.rotation == 180:
            tl_point *= self._page.derotation_matrix
            tl_point[0] -= rect_width
            tl_point[1] -= rect_height
        if self._page.rotation == 270:
            tl_point[0] -= rect_width
        if self._page.rotation == 90:
            tl_point[1] -= rect_height
        br_point = fitz.Point(tl_point[0] + rect_width, tl_point[1] + rect_height)
        return fitz.Rect(tl_point, br_point)

    def _get_pdfed_rect(self, x0: float, y0: float, x1: float, y1: float) -> fitz.Rect:
        width = (x1 - x0) * self.PDF_ZOOM_FACTOR
        height = (y1 - y0) * self.PDF_ZOOM_FACTOR
        x = x0 * self.PDF_ZOOM_FACTOR
        y = y0 * self.PDF_ZOOM_FACTOR
        return self._get_rect_from_xywh(x, y, width, height)

    def _set_error(self, error_descr):
        self._error_description = error_descr
        self._append_msg_to_log(f'{self._error_description}, aborting...')
        return

    def get_error_description(self):
        return self._error_description

    def _clear_error(self):
        self._error_description = ''
        return

    def get_log(self) -> str:
        return '\r\n'.join(self._log)

    def _append_msg_to_log(self, message: str) -> None:
        print(message)
        self._log.append(message)

    # opens the doc from file path or link, returns False if failed
    def _open_doc(self) -> bool:
        assert self._pdf_path != '' "pdf path cannot be empty"
        if self._is_link:
            # if pdf_path is a link
            self._append_msg_to_log(f'Loading the file from {self._pdf_path}...')
            response = requests.get(self._pdf_path)
            if response.status_code != requests.codes.ok:
                self._set_error(f'Bad response: {response.status_code}')
                return False
            try:
                self._doc = fitz.Document(stream=response.content, filetype="pdf")
            except Exception as e:
                self._set_error(f'{self._pdf_path} cannot be open: {str(e)}')
                return False
        else:
            # if _pdf_path is a path, add '_annotated' to the file name
            self._pdf_path_annotated = self._pdf_path[:-4] + '_annotated' + self._pdf_path[-4:]
            # open the pdf file
            self._append_msg_to_log(f'Opening {self._pdf_path[5:]}...')
            try:
                self._doc = fitz.Document(self._pdf_path)
            except Exception as e:
                self._set_error(f'{self._pdf_path} cannot be open: {str(e)}')
                return False

        # load the only page
        self._page = self._doc.load_page(0)
        self._clear_error()
        return True

    def _get_pics_from_page(self):
        pix = self._page.get_pixmap(dpi=AnnotationMaker.DPI)

        # converting page into pillow format
        self._page_pillow_image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)

        # save page image for debug purposes
        self._page_pillow_image.save('images/img_original.png', format='PNG')

        # will be used to find empty space on the page
        self._page_opencv_image = np.asarray(self._page_pillow_image)

        # cropping the right part of the page image
        self._page_pillow_image_cropped = self._page_pillow_image.crop(
            (AnnotationMaker.CROP_X0, AnnotationMaker.CROP_Y0,
             AnnotationMaker.CROP_X1, AnnotationMaker.CROP_Y1))

        # converting the pillow image into nampy array
        self._cropped_page_opencv_image = np.asarray(self._page_pillow_image_cropped)
        return

    def _ocr_cropped_image(self):
        result = self._ocr.ocr(self._cropped_page_opencv_image, cls=True)

        # as there is only one page, the result contains only one element
        self._ocr_result_data = result[0]
        return

    # returns False if failed
    def _analyze_ocred_data(self) -> bool:
        assert self._ocr_result_data is not [], "cannot ocr empty data"

        fcs_rect: Points4 = list()
        node_text_rect: Points4 = list()

        # preparing to draw on the cropped image
        draw = ImageDraw.Draw(self._page_pillow_image_cropped)

        # checking every block of text
        for block in self._ocr_result_data:
            # draw a RED rectangle for ALL texts found
            try:
                draw.rectangle((tuple(block[0][0]), tuple(block[0][2])), width=2, outline='red')
            except Exception as e:
                self._append_msg_to_log(f'Exception while drawing a rectangle: {str(e)}')
            # saving coordinates for later
            coordinates: Points4 = block[0]
            # saving text for later
            text: str = block[1][0]

            # checking first five symbols for the desired text ('FCS07' in our case)
            if text[:5] in self.FCS_TEXT_TO_FIND:
                # saving coordinates of the desired text ('FCS07' in our case)
                fcs_rect = coordinates
                self._append_msg_to_log(f'{AnnotationMaker.FCS_TEXT_TO_FIND} was found in {fcs_rect}')

                # as we found the FCS text, there is no need to rotate the page and searching the text again
                self._tries_to_rotate = 0

                # noinspection PyTypeChecker
                self._fcs_top_left_cropped: tuple[float, float] = tuple(fcs_rect[0])
                # noinspection PyTypeChecker
                self._fcs_bottom_right_cropped: tuple[float, float] = tuple(fcs_rect[2])
                # forming a full text which replaces the old one
                self._what_to_replace = text
                what_to_add = text[5:]
                self._replaced_with = AnnotationMaker.FCS_TEXT_TO_REPLACE_WITH + what_to_add
                draw.rectangle((self._fcs_top_left_cropped, self._fcs_bottom_right_cropped), outline='blue', width=2)

            # checking if it is the 'NODE' text
            if text in AnnotationMaker.NODE_TEXTS:
                # saving the 'NODE' text coordinates for later
                node_text_rect = coordinates
                self._append_msg_to_log(f'NODE was found in {node_text_rect}')

                self._node_text_x0 = coordinates[0][0]
                # sometimes nn text is a bit more on the right, that the NODE text, so +15
                self._node_text_x2 = coordinates[2][0] + 15
                self._node_text_y2 = coordinates[2][1]
                # noinspection PyTypeChecker
                self._nn_top_left_cropped: tuple[float, float] = (*node_text_rect[0],)
                # noinspection PyTypeChecker
                self._nn_bottom_right_cropped: tuple[float, float] = tuple(node_text_rect[2])

            # checking the actual node number text, it makes sense only after the 'NODE' text has already been found
            if node_text_rect is not None and set(text).issubset('0123456789'):
                # checking if the coordinates of the digits are under the 'NODE' text
                text_x1, text_y1 = coordinates[1][0], coordinates[1][1]
                if self._node_text_x0 < text_x1 < self._node_text_x2 and text_y1 > self._node_text_y2:
                    # as there can be more than one node number (i.e. for Fieldbus),
                    # we need to have the list of rectangles
                    self._node_number_rects.append(coordinates)
                    # forming the new node number text
                    self._new_node_number_text = str(int(text) + 1)
                    self._append_msg_to_log(f'NODE number {str(int(text))} was found in {coordinates}')

        if not node_text_rect:
            self._append_msg_to_log(f'NODE was NOT found')

        # if the FCS text was not found, rotate the page and decrement the number of tries left
        if not fcs_rect:
            self._append_msg_to_log(f'{AnnotationMaker.FCS_TEXT_TO_FIND} was NOT found')
            self._page.set_rotation(self._page.rotation + 90)
            self._tries_to_rotate -= 1
            self._append_msg_to_log(f'Rotating the page, {self._tries_to_rotate} tries left...')
            # if no tries left - quit the script
            if self._tries_to_rotate == 0:
                self._set_error(f'No tries left, check the document')
                return False

        self._page_pillow_image_cropped.save('images/img_cropped.png', format='PNG')

        self._clear_error()
        return True

    # adding FCS annotations into pdf
    def _add_fcs_annotations(self):
        # calculating pdf coordinates of found FCS text
        fcs_top_left, fcs_bottom_right = self._get_points_from_cropped(self._fcs_top_left_cropped,
                                                                       self._fcs_bottom_right_cropped)
        # calculating pdf coordinates of new FCS text
        fcs_new_x0 = fcs_bottom_right[0] + 5
        fcs_new_y0 = fcs_top_left[1]
        fcs_new_x1 = fcs_new_x0 + (fcs_bottom_right[0] - fcs_top_left[0]) + 10
        fcs_new_y1 = fcs_new_y0 + (fcs_bottom_right[1] - fcs_top_left[1]) + 10

        # calculating pdf coordinates for FCS annotations
        fcs_new_text_rect = self._get_pdfed_rect(fcs_new_x0, fcs_new_y0,
                                                 fcs_new_x1, fcs_new_y1)
        self._fcs_found_text_rect = self._get_pdfed_rect(*fcs_top_left, *fcs_bottom_right)

        # drawing on the page image and saving it for debug purposes
        draw = ImageDraw.Draw(self._page_pillow_image)
        draw.rectangle((fcs_top_left, fcs_bottom_right), outline='blue', width=2)
        self._page_pillow_image.save('images/img_original_marked.png', format='PNG')

        self._page.add_line_annot((self._fcs_found_text_rect[0], self._fcs_found_text_rect[1]),
                                  (self._fcs_found_text_rect[2], self._fcs_found_text_rect[3]))
        self._page.add_freetext_annot(fcs_new_text_rect, self._replaced_with, text_color=(255, 0, 0),
                                      border_color=None, rotate=self._page.rotation, fontsize=8)
        return

    # adding NODE annotations into pdf
    def _add_node_annotations(self):
        for nn in self._node_number_rects:
            # calculating Node numbers coordinates
            # noinspection PyTypeChecker
            nn_top_left_cropped: tuple[float, float] = (*nn[0],)
            # noinspection PyTypeChecker
            nn_bottom_right_cropped: tuple[float, float] = tuple(nn[2])
            nn_top_left, nn_bottom_right = self._get_points_from_cropped(nn_top_left_cropped,
                                                                         nn_bottom_right_cropped)
            nn_new_x0: float = nn_bottom_right[0] + 5
            nn_new_y0: float = nn_top_left[1]
            nn_new_x1: float = nn_new_x0 + (nn_bottom_right[0] - nn_top_left[0]) + 10
            nn_new_y1: float = nn_new_y0 + (nn_bottom_right[1] - nn_top_left[1]) + 10
            nn_new_text_rect: fitz.Rect = self._get_pdfed_rect(nn_new_x0, nn_new_y0, nn_new_x1, nn_new_y1)
            node_number_text_rect: fitz.Rect = self._get_pdfed_rect(*nn_top_left, *nn_bottom_right)

            # adding Node numbers annotations into pdf
            self._page.add_line_annot((node_number_text_rect[0], node_number_text_rect[1]),
                                      (node_number_text_rect[2], node_number_text_rect[3]))
            self._page.add_freetext_annot(nn_new_text_rect, self._new_node_number_text, text_color=(255, 0, 0),
                                          border_color=None, rotate=self._page.rotation, fontsize=8)
        return

    def _add_stamp(self):
        # defining static coordinates for the stamp is a bad idea, because the stamp may overlap with useful info
        # stamp_rect = (1400, 1000, 1800, 1200)
        # instead, we find an empty space for the stamp!
        grayed_page_image = cv2.cvtColor(self._page_opencv_image, cv2.COLOR_BGR2GRAY)

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
        stamp_rect = self._get_pdfed_rect(*stamp_rect[0], *stamp_rect[1])

        # adding the stamp
        self._page.insert_image(stamp_rect, filename='images/RLMU_Stamp.png', keep_proportion=True,
                                overlay=True, rotate=self._page.rotation)
        return

        # returns True if success, otherwise False

    def make_redline(self, pdf_path: str, is_link: bool = False) -> bool:
        # path or link to a pdf file
        if pdf_path in ('', None):
            self._set_error(f'pdf path cannot be empty')
            return False
        else:
            self._pdf_path = pdf_path

        self._is_link = is_link

        if not self._open_doc():
            return False

        ocr_success = False
        while self._tries_to_rotate > 0:
            self._get_pics_from_page()
            self._ocr_cropped_image()
            ocr_success = self._analyze_ocred_data()

        if not ocr_success:
            return False

        self._add_fcs_annotations()
        self._add_node_annotations()
        self._add_stamp()

        self._append_msg_to_log(f'Saving the annotated pdf and closing the document...')
        self._doc.save(self._pdf_path_annotated)
        self._clear_error()
        return True

from paddleocr import PaddleOCR
from fitz import Rect, Page, Point, Document, TEXT_ALIGN_RIGHT
from PIL import Image, ImageDraw
import numpy as np
import cv2
import re


class NoDPIError(Exception):
    pass


class NoNeedToRedlineError(Exception):
    pass


class AnnotationMakerBase:
    _NODE_TEXTS = ('NODE', 'NCDE', 'N0DE')
    _FCS_TEXT_TO_FIND = ('FCS07', 'FCSO7', 'FSC07')
    _FCS_TEXT_TO_REPLACE_WITH = 'FCS14'

    def __init__(self):
        # pix.page.get_pixmap without specifying DPI or matrix returns image with dpi 72
        # so crop rectangtle coordinates (based on dpi==72) and zoom factor are recaculated every DPI set
        # default DPI for the class is 150        

        # crop rectangle coordinates for dpi 72 for new loop diagrams by default
        self._CROP_X0_72 = 730
        self._CROP_Y0_72 = 12
        self._CROP_X1_72 = 1176
        self._CROP_Y1_72 = 710
        self._is_dpi_set = False
        self._pdf_path_annotated: str = ''
        self._error_description: str = ''
        self._ocr_result_data = []
        self._pdf_path: str = ''
        self._replaced_with = ''
        self._page_pillow_image_cropped: Image = None
        self._page_pillow_image: Image = None
        self._page_opencv_image: np.ndarray | None = None
        self._cropped_page_opencv_image: np.ndarray | None = None
        self._doc: Document | None = None
        self._page: Page | None = None
        self._log: list[str] = []
        # need to run only once to download and load model into memory
        self._ocr: PaddleOCR.ocr = PaddleOCR(use_angle_cls=True, lang='en', show_log=False)

    def __del__(self):
        if self._doc is not None:
            self._doc.close()

    def _get_points_from_cropped(self, p1: tuple[float, float], p2: tuple[float, float]):
        if not self._is_dpi_set:
            raise NoDPIError("DPI must be set before working with images")
        return (p1[0] + self._CROP_X0, p1[1] + self._CROP_Y0), (p2[0] + self._CROP_X0, p2[1] + self._CROP_Y0)

    def _set_dpi(self, dpi: int) -> None:
        if isinstance(dpi, int) and 72 <= dpi <= 600:
            self._DPI = dpi
            self._PDF_ZOOM_FACTOR = self._DPI / 72
            self._CROP_X0 = self._CROP_X0_72 * self._PDF_ZOOM_FACTOR
            self._CROP_Y0 = self._CROP_Y0_72 * self._PDF_ZOOM_FACTOR
            self._CROP_X1 = self._CROP_X1_72 * self._PDF_ZOOM_FACTOR
            self._CROP_Y1 = self._CROP_Y1_72 * self._PDF_ZOOM_FACTOR
            self._is_dpi_set = True
        else:
            raise ValueError("DPI should be integer between 72 and 600")
        return

    def get_crop_rectangle(self) -> tuple[float: 4]:
        return self._CROP_X0_72, self._CROP_Y0_72, self._CROP_X1_72, self._CROP_Y1_72

    def set_crop_rectangle(self, x0, y0, x1, y1):
        self._CROP_X0_72 = x0
        self._CROP_Y0_72 = y0
        self._CROP_X1_72 = x1
        self._CROP_Y1_72 = y1
        self._is_dpi_set = False
        return

    def set_crop_rectangle_wh(self, x0, y0, w, h):
        self._CROP_X0_72 = x0
        self._CROP_Y0_72 = y0
        self._CROP_X1_72 = x0 + w
        self._CROP_Y1_72 = y0 + h
        self._is_dpi_set = False
        return

    def _get_rect_from_xywh(self, top_left_x: float, top_left_y: float,
                            rect_width: float, rect_height: float) -> Rect:
        tl_point = Point(top_left_x, top_left_y)
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
        br_point = Point(tl_point[0] + rect_width, tl_point[1] + rect_height)
        return Rect(tl_point, br_point)

    def _get_pdfed_rect(self, x0: float, y0: float, x1: float, y1: float) -> Rect:
        if not self._is_dpi_set:
            raise NoDPIError("DPI must be set before working with images")
        width = (x1 - x0) / self._PDF_ZOOM_FACTOR
        height = (y1 - y0) / self._PDF_ZOOM_FACTOR
        x = x0 / self._PDF_ZOOM_FACTOR
        y = y0 / self._PDF_ZOOM_FACTOR
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

    # opens the doc from file path, returns False if failed
    def _open_doc(self) -> bool:
        assert self._pdf_path != '', "pdf path cannot be empty"
        # add '_annotated' to the file name
        self._pdf_path_annotated = self._pdf_path[:-4] + '_annotated' + self._pdf_path[-4:]
        # open the pdf file
        self._append_msg_to_log(f'Opening {self._pdf_path}...')
        try:
            self._doc = Document(self._pdf_path)
        except Exception as e:
            self._set_error(f'{self._pdf_path} cannot be open: {str(e)}')
            return False

        # load the only page
        self._page = self._doc.load_page(0)
        self._clear_error()
        return True

    # to prevent bad things happening like a stamp outside of pages
    def _wrap_page_content(self) -> None:
        if self._page.is_wrapped:
            self._page.wrap_contents()
        return

    def _rebuild_page_content(self) -> None:
        assert 1 == 0, 'not implemented yet'
        # another and probably a better way of preventing bad things happening, but requires a new document:
        # https://github.com/pymupdf/PyMuPDF/discussions/2494
        #
        # doc = fitz.open()  # new output file
        # src = fitz.open("2.pdf")  # source file
        # imgfile = "nur-ruhig.png"
        # for src_page in src:  # iterate over input pages
        #     src_rect = src_page.rect  # source page rect
        #     w, h = src_rect.br  # save its width, height
        #     src_rot = src_page.rotation  # save source rotation
        #     src_page.set_rotation(0)  # set rotation to 0 temporarily
        #     page = doc.new_page(width=w, height=h)  # make output page
        #     page.show_pdf_page(  # insert source page
        #         page.rect,
        #         src,
        #         src_page.number,
        #         rotate=-src_rot,  # use reversed original rotation
        #     )
        #     page.insert_image((0, 0, 400, 200), filename=imgfile)
        #
        # doc.ez_save("output.pdf")

    def _get_pics_from_page(self, no_need_to_crop=False):
        if not self._is_dpi_set:
            raise NoDPIError("DPI must be set before working with images")

        pix = self._page.get_pixmap(dpi=self._DPI)

        # converting page into pillow format
        self._page_pillow_image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)

        # save page image for debug purposes
        self._page_pillow_image.save('images/img_original.png', format='PNG')

        # will be used to find empty space on the page
        self._page_opencv_image: np.ndarray = np.asarray(self._page_pillow_image)

        if no_need_to_crop:
            self._page_pillow_image_cropped = self._page_pillow_image
            self._CROP_X0, self._CROP_Y0 = 0, 0
            self._CROP_X1, self._CROP_Y1 = pix.width, pix.height
        else:
            # cropping the right part of the page image
            self._page_pillow_image_cropped = self._page_pillow_image.crop(
                (int(self._CROP_X0), int(self._CROP_Y0),
                 int(self._CROP_X1), int(self._CROP_Y1)))

        # converting the pillow image into nampy array
        self._cropped_page_opencv_image: np.ndarray = np.asarray(self._page_pillow_image_cropped)

        # *************** test of image preparation, may worsen the ocr result *******************
        # self._cropped_page_opencv_image = cv2.cvtColor(self._cropped_page_opencv_image, cv2.COLOR_BGR2GRAY)
        # cv2.imwrite(f'images/img_pre-processed_1_{self._DPI}.png', self._cropped_page_opencv_image)
        # threshold the image using Otsu's thresholding method
        # self._cropped_page_opencv_image = cv2.threshold(self._cropped_page_opencv_image, 0, 255, \
        #                                                 cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
        # cv2.imwrite(f'images/img_pre-processed_2_{self._DPI}.png', self._cropped_page_opencv_image)
        # kernel = np.ones((2, 2), np.uint8)
        # self._cropped_page_opencv_image = cv2.dilate(temp_image, kernel, iterations=1)
        # *************** test of image preparation, may worsen the ocr result *******************

        return

    def _ocr_cropped_image(self):
        result = self._ocr.ocr(self._cropped_page_opencv_image, cls=True)

        # as there is only one page, the result contains only one element
        self._ocr_result_data = result[0]
        return

    # returns False if failed

    def _add_stamp(self):
        # defining static coordinates for the stamp is a bad idea, because the stamp may overlap with useful info
        # stamp_rect = (1400, 1000, 1800, 1200)
        # instead, we find an empty space for the stamp!
        grayed_page_image = cv2.cvtColor(self._page_opencv_image, cv2.COLOR_BGR2GRAY)

        # create a grayscale image 200x400
        empty_template = np.zeros([int(200 * self._DPI / 150), int(400 * self._DPI / 150), 1],
                                  dtype=np.uint8)
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

    def _set_pdf_path(self, pdf_path) -> bool:
        # path to a pdf file
        if pdf_path in ('', None):
            self._set_error(f'pdf path cannot be empty')
            return False
        else:
            self._pdf_path = pdf_path
            return True


class AnnotationMakerOld(AnnotationMakerBase):
    def __init__(self):
        super().__init__()
        self._CROP_X0_72 = 989
        self._CROP_Y0_72 = 62
        self._CROP_X1_72 = 1152
        self._CROP_Y1_72 = 624
        self._tries_to_ocr: int = 4  # one initial try + 3 tries after rotation by 90 degrees
        self._node_number_rects = list()

    def _analyze_ocred_data(self) -> bool:
        assert self._ocr_result_data is not [], "cannot ocr empty data"

        fcs_rect = list()
        node_text_rect = list()

        # preparing to draw on the cropped image
        draw = ImageDraw.Draw(self._page_pillow_image_cropped)

        fcs_regex = re.compile(r"^FCS\d\d\d\d$")
        # checking every block of text
        for block in self._ocr_result_data:
            # draw a RED rectangle for ALL texts found
            try:
                draw.rectangle(tuple(block[0][0] + block[0][2]), width=2, outline='red')
            except Exception as e:
                self._append_msg_to_log(f'Exception while drawing a rectangle: {str(e)}')
            # saving coordinates for later
            coordinates: list[list[float: 2]: 4] = block[0]
            # saving text for later
            text: str = block[1][0]
            # print(f"{text=}")

            # checking first five symbols for the desired text ('FCS07' in our case)
            if text[:5] in self._FCS_TEXT_TO_FIND:
                matching_result = fcs_regex.match(text)
                if matching_result is not None:
                    # saving coordinates of the desired text ('FCS07' in our case)
                    fcs_rect: list[list[float: 2]: 4] = coordinates
                    self._append_msg_to_log(f'{text} was found in {fcs_rect}')

                    # as we found the FCS text, there is no need to rotate the page and searching the text again
                    self._tries_to_ocr = 0

                    self._fcs_top_left_cropped: tuple[float, float] = tuple(fcs_rect[0])
                    self._fcs_bottom_right_cropped: tuple[float, float] = tuple(fcs_rect[2])
                    # forming a full text which replaces the old one
                    what_to_add = text[5:]
                    self._replaced_with = self._FCS_TEXT_TO_REPLACE_WITH + what_to_add
                    draw.rectangle(tuple(self._fcs_top_left_cropped + self._fcs_bottom_right_cropped), outline='blue',
                                   width=2)

            # checking if it is the 'NODE' text
            if text in self._NODE_TEXTS:
                # saving the 'NODE' text coordinates for later
                node_text_rect = coordinates
                self._append_msg_to_log(f'NODE was found in {node_text_rect}')

                self._node_text_x0 = coordinates[0][0]
                # sometimes nn text is a bit more on the right, that the NODE text, so +15
                self._node_text_x2 = coordinates[2][0] + 15
                self._node_text_y2 = coordinates[2][1]

            # checking the actual node number text, it makes sense only after the 'NODE' text has already been found
            if len(node_text_rect) > 0 and set(text).issubset('0123456789'):
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

        self._page_pillow_image_cropped.save('images/img_cropped.png', format='PNG')

        # if the FCS text was not found, rotate the page and decrement the number of tries left
        if not fcs_rect:
            self._append_msg_to_log(f'{self._FCS_TEXT_TO_FIND} was NOT found')
            self._page.set_rotation(self._page.rotation + 90)
            self._tries_to_ocr -= 1
            self._append_msg_to_log(f'Rotating the page, {self._tries_to_ocr} tries left...')
            # if no tries left - quit the script
            if self._tries_to_ocr == 0:
                self._set_error(f'No tries left, check the document')
                return False

        self._clear_error()
        return True

    # adding FCS annotations into pdf
    def _add_fcs_annotations(self) -> None:
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
        draw.rectangle((self._CROP_X0, self._CROP_Y0, self._CROP_X1, self._CROP_Y1), outline='red', width=5)
        draw.rectangle(tuple(fcs_top_left + fcs_bottom_right), outline='blue', width=2)
        self._page_pillow_image.save('images/img_original_marked.png', format='PNG')

        self._page.add_line_annot((self._fcs_found_text_rect[0], self._fcs_found_text_rect[1]),
                                  (self._fcs_found_text_rect[2], self._fcs_found_text_rect[3]))
        self._page.add_freetext_annot(fcs_new_text_rect, self._replaced_with, text_color=(255, 0, 0),
                                      border_color=None, rotate=self._page.rotation, fontsize=8)
        return

    # adding NODE annotations into pdf
    def _add_node_annotations(self):
        draw = ImageDraw.Draw(self._page_pillow_image)
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
            nn_new_text_rect: Rect = self._get_pdfed_rect(nn_new_x0, nn_new_y0, nn_new_x1, nn_new_y1)
            node_number_text_rect: Rect = self._get_pdfed_rect(*nn_top_left, *nn_bottom_right)
            draw.rectangle(tuple(nn_top_left + nn_bottom_right), outline='orange', width=2)

            # adding Node numbers annotations into pdf
            self._page.add_line_annot((node_number_text_rect[0], node_number_text_rect[1]),
                                      (node_number_text_rect[2], node_number_text_rect[3]))
            self._page.add_freetext_annot(nn_new_text_rect, self._new_node_number_text, text_color=(255, 0, 0),
                                          border_color=None, rotate=self._page.rotation, fontsize=8)
        self._page_pillow_image.save('images/img_original_marked.png', format='PNG')
        return

    def make_redline(self, pdf_path: str, dpi=150, no_need_to_crop=False, tries_to_rotate=3) -> bool:
        assert 0 <= tries_to_rotate < 4, "tries_to_rotate must be 0, 1, 2, or 3"

        if not self._set_pdf_path(pdf_path):
            return False
        if not self._open_doc():
            return False

        self._set_dpi(dpi)
        ocr_success = False
        self._tries_to_ocr = tries_to_rotate + 1
        while self._tries_to_ocr > 0:
            self._get_pics_from_page(no_need_to_crop)
            self._ocr_cropped_image()
            ocr_success = self._analyze_ocred_data()

        if not ocr_success:
            return False
        self._wrap_page_content()
        self._add_fcs_annotations()
        self._add_node_annotations()
        self._add_stamp()

        self._append_msg_to_log(f'Saving the annotated pdf and closing the document...')
        try:
            self._doc.save(self._pdf_path_annotated)
        except Exception as e:
            self._append_msg_to_log(f'Error while saving the annotated pdf: {str(e)}')
            return False
        self._clear_error()
        # returns True if success, otherwise False
        return True


class AnnotationMakerNew(AnnotationMakerBase):
    def __init__(self):
        super().__init__()
        self._CROP_X0_72 = 730
        self._CROP_Y0_72 = 12
        self._CROP_X1_72 = 1176
        self._CROP_Y1_72 = 710
        self._fcs_new_texts: list[str] = list()
        self._fcs_rects: list[list[list[float: 2]: 4]] = list()
        self._node_rects: list[list[list[float: 2]: 4]] = list()
        self._node_text_lengths: list[int] = list()
        self._new_node_numbers: list[int] = list()

    def _analyze_ocred_data(self, need_fcs_check=True) -> bool:
        assert self._ocr_result_data is not [], "cannot ocr empty data"

        fcs_regex = re.compile(r"^(FCS|FSC)\d\d(\d\d)-?(\d\d)-?(\d\d).*$")
        node_regex = re.compile(r"^N[O0C]DE\s*(\d{1,2})\s*$")

        # preparing to draw on the cropped image
        draw = ImageDraw.Draw(self._page_pillow_image_cropped)

        # checking every block of text
        for block in self._ocr_result_data:
            # draw a RED rectangle for ALL texts found
            try:
                draw.rectangle(tuple(block[0][0] + block[0][2]), width=2, outline='red')
            except Exception as e:
                self._append_msg_to_log(f'Exception while drawing a rectangle: {str(e)}')
            # saving coordinates for later
            coordinates: list[list[float, float]:4] = block[0]
            # saving text for later
            text: str = block[1][0]
            # print(f"{text=}")

            if text[:5] == self._FCS_TEXT_TO_REPLACE_WITH and len(self._fcs_rects) == 0:
                raise NoNeedToRedlineError(f"The loop drawing already contains {self._FCS_TEXT_TO_REPLACE_WITH}, "
                                           f"no need to redline")
            if text[:5] in self._FCS_TEXT_TO_FIND and len(text) > 7:
                fcs_rect: list[list[float: 2]: 4] = coordinates
                matching_result = fcs_regex.match(text)
                if matching_result is not None:
                    node_number: int = int(matching_result.group(3))
                    new_node_number = node_number + 1
                    fcs_name = self._FCS_TEXT_TO_REPLACE_WITH + matching_result.group(2)
                    new_fcs_node_number = "{:02d}".format(int(new_node_number))
                    replaced_with = f"{fcs_name}-{new_fcs_node_number}-{matching_result.group(4)}"
                    self._fcs_new_texts.append(replaced_with)
                    self._fcs_rects.append(fcs_rect)
                    self._append_msg_to_log(f'{text} was found in {fcs_rect}')
                try:
                    draw.rectangle(tuple(fcs_rect[0] + fcs_rect[2]), outline='blue', width=2)
                except Exception as e:
                    self._append_msg_to_log(f'Exception while drawing a rectangle: {str(e)}')

            if text[:4] in self._NODE_TEXTS:
                node_rect: list[list[float: 2]: 4] = coordinates
                # Additional check if there is digits after the node text
                matching_result = node_regex.match(text)
                if matching_result is not None:
                    node_number: int = int(matching_result.group(1))
                    new_node_number = node_number + 1
                    self._node_rects.append(node_rect)
                    self._new_node_numbers.append(new_node_number)
                    self._node_text_lengths.append(len(text))
                    self._append_msg_to_log(f'{text} was found in {node_rect}, {node_number=}')
                    try:
                        draw.rectangle(tuple(node_rect[0] + node_rect[2]), outline='green', width=2)
                    except Exception as e:
                        self._append_msg_to_log(f'Exception while drawing a rectangle: {str(e)}')

        self._page_pillow_image_cropped.save('images/img_cropped.png', format='PNG')

        if len(self._fcs_rects) > 0:
            if len(self._fcs_rects) != len(self._node_rects):
                self._append_msg_to_log(f'WARNING: number of FCS texts found is not equal to numbers of NODE texts '
                                        f'with digits')

        if need_fcs_check:
            # if not FCS texts found, return False
            return len(self._fcs_rects) > 0
        else:
            # if no fcs on the drawing, but you still need to redline:
            return len(self._node_rects) > 0

    def _add_fcs_annotations(self) -> None:
        # preparing to draw on the page image for debug purposes
        draw = ImageDraw.Draw(self._page_pillow_image)
        draw.rectangle((self._CROP_X0, self._CROP_Y0, self._CROP_X1, self._CROP_Y1), outline='red', width=5)

        # for each found FCS rectangle and text
        for fcs_rect, fcs_text in zip(self._fcs_rects, self._fcs_new_texts):
            # calculating absolute page coordinates for a line annotation
            fcs_page_line_top_left, fcs_page_line_bottom_right = self._get_points_from_cropped(fcs_rect[0], fcs_rect[2])
            # drawing a blue rectangle on the page image for debug purposes
            draw.rectangle(tuple(fcs_page_line_top_left + fcs_page_line_bottom_right), outline='blue', width=2)
            # calculating page coordinates for a text annotation
            # x0_new = 2*x0-x1-5, y0, # x1_new = x0-5, y1
            fcs_text_page_top_left = (2 * fcs_page_line_top_left[0] - fcs_page_line_bottom_right[0] - 5,
                                      fcs_page_line_top_left[1] + 5)
            fcs_text_page_bottom_right = (fcs_page_line_top_left[0] - 5, fcs_page_line_bottom_right[1] + 5)
            # calculating pdf coordinates for a text annotation
            fcs_pdf_new_text_rect = self._get_pdfed_rect(*fcs_text_page_top_left, *fcs_text_page_bottom_right)
            # calculating pdf coordinates for a line annotation
            fcs_pdf_line_rect = self._get_pdfed_rect(*fcs_page_line_top_left, *fcs_page_line_bottom_right)
            # adding a line annotation into pdf
            try:
                self._page.add_line_annot((fcs_pdf_line_rect[0], fcs_pdf_line_rect[1]),
                                          (fcs_pdf_line_rect[2], fcs_pdf_line_rect[3]))
            except Exception as e:
                self._append_msg_to_log(f'WARNING: failed to add an FCS line annotation: {str(e)}')
            # adding a text annotation into pdf
            try:
                self._page.add_freetext_annot(fcs_pdf_new_text_rect, fcs_text, text_color=(255, 0, 0),
                                              border_color=None, rotate=self._page.rotation, fontsize=4)
            except Exception as e:
                self._append_msg_to_log(f'WARNING: failed to add an FCS text annotation: {str(e)}')

        # saving the image for debug purposes
        self._page_pillow_image.save('images/img_original_marked.png', format='PNG')
        return

    # adding NODE annotations into pdf
    def _add_node_annotations(self):
        # for each found NODE rectangle and new node number
        for node_rect, new_node_number, node_text_len in zip(self._node_rects, self._new_node_numbers,
                                                             self._node_text_lengths):
            node_page_rect_top_left, node_page_rect_bottom_right = self._get_points_from_cropped(node_rect[0],
                                                                                                 node_rect[2])
            node_page_line_top_left = (node_page_rect_top_left[0] - 5, node_page_rect_top_left[1])
            node_page_line_bottom_right = (node_page_rect_bottom_right[0] + 5, node_page_rect_bottom_right[1])
            node_pdf_new_text_rect = self._get_pdfed_rect(*node_page_line_top_left, *node_page_line_bottom_right)
            # adding a text annotation into pdf
            try:
                self._page.add_freetext_annot(node_pdf_new_text_rect, f'NODE {str(new_node_number)}',
                                              text_color=(255, 0, 0), border_color=None, rotate=self._page.rotation,
                                              fontsize=4, fill_color=(1, 1, 1))
            except Exception as e:
                self._append_msg_to_log(f'WARNING: failed to add a node number annotation: {str(e)}')
        return

    def make_redline(self, pdf_path: str, dpi=150, no_need_to_crop=False, need_fcs_check=True) -> bool:
        if not self._set_pdf_path(pdf_path):
            return False

        if not self._open_doc():
            return False

        ocr_success = False
        self._set_dpi(dpi)
        super()._get_pics_from_page(no_need_to_crop)
        super()._ocr_cropped_image()
        try:
            ocr_success = self._analyze_ocred_data(need_fcs_check)
        except NoNeedToRedlineError as e:
            self._set_error(str(e))
            return False

        if not ocr_success:
            self._set_error(f'No FCS text thats suits the template was found')
            return False

        self._wrap_page_content()
        self._add_fcs_annotations()
        self._add_node_annotations()
        self._add_stamp()

        self._append_msg_to_log(f'Saving the annotated pdf and closing the document...')
        try:
            self._doc.save(self._pdf_path_annotated)
        except Exception as e:
            self._append_msg_to_log(f'Error while saving the annotated pdf: {str(e)}')
            return False
        self._clear_error()

        return True

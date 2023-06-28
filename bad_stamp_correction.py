from fitz import Page, Document
import numpy as np
import cv2
import os

os.system('cls')

doc = Document("example_pdfs/LUNA_all_in_one.pdf")
dummy: Page = doc[0]

for page_nm, page in enumerate(doc.pages()):
    # print(page.rect)
    page_is_wrapped: bool = page.is_wrapped
    print(f"Processing page number {page_nm+1}...")

    if not page_is_wrapped:
        images = page.get_images(True)
        if len(images) < 2:
            print(f"NO STAMP ON PAGE {page_nm+1}!!!!")
            continue
        stamp_xref = images[1][0]
        stamp_name = images[1][7]
        # print(page.get_image_info(xrefs=True))
        # print(page.get_image_bbox(stamp_name, transform=False))
        print(f"wrapping the context...")
        page.wrap_contents()
        print(f"deleting the incorrect stamp...")
        page.delete_image(stamp_xref)
        print(f"inserting a new stamp...")
        x, y = 110, 530
        page.insert_image((x, y, x + 200, y + 100), filename='images/RLMU_Stamp.png', keep_proportion=True,
                          overlay=True, rotate=page.rotation)

print(f"Saving the document...")
doc.save("example_pdfs/all_in_one_stamps_rectified.pdf")
doc.close()
